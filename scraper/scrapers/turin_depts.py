"""University of Turin (UniTO) — multi-department faculty scraper.

UniTO publishes each department's personnel at a per-subdomain campusnet
instance, all using the same `do/docenti.pl` widget. We iterate through a
configurable list of departments and collect their ranked faculty from the
"Suddivisi per ruolo" (grouped-by-role) view.

Roles kept — only ranked faculty who can main-supervise PhD students:

- Professori/Professoresse ordinari/e            → Full Professor
- Professori/Professoresse associati/e           → Associate Professor
- Ricercatori/Ricercatrici universitari/e        → Researcher (permanent)
- Ricercatori/Ricercatrici a tempo determinato di tipo B  → Assistant Professor
  (RTD-B is Italy's tenure-track rank, converts to Associate on successful
  evaluation)
- Ricercatori/Ricercatrici in tenure track       → Tenure-Track Researcher

Excluded: RTD-A (3-year non-tenure, effectively a postdoc with teaching),
Emeriti, Assegnisti (postdocs without teaching), PhD students, and all
support / admin staff.

Run with:
    python -m scrapers.turin_depts
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from scrapers._http import get
from schema import Faculty, clean_text, slugify


# Each entry: (department subdomain base URL, display label).
# The per-department personnel index is always at
# {base}/do/docenti.pl/Search?format=6;sort=U2;max=5000;sf=0;title=Suddivisi+per+ruolo
_DEPARTMENTS: list[tuple[str, str]] = [
    (
        "https://www.dbios.unito.it",
        "Department of Life Sciences and Systems Biology (DBIOS)",
    ),
    (
        "https://www.dbmss.unito.it",
        "Department of Molecular Biotechnology and Health Sciences (DBMSS)",
    ),
    (
        "https://www.chimica.unito.it",
        "Department of Chemistry",
    ),
    (
        "https://www.df.unito.it",
        "Department of Physics",
    ),
    (
        "https://www.dipmatematica.unito.it",
        'Department of Mathematics "Giuseppe Peano"',
    ),
]


# Italian role label -> (English title, keep?).
_ROLES: dict[str, tuple[str, bool]] = {
    "Professori/Professoresse ordinari/e": ("Full Professor", True),
    "Professori/Professoresse associati/e": ("Associate Professor", True),
    "Professori/Professoresse emeriti/e": ("Emeritus Professor", False),
    "Ricercatori/Ricercatrici universitari/e": ("Researcher", True),
    # RTD-A is a 3-year non-tenure post — effectively a postdoc with teaching.
    # Italian PhD regulations typically don't let RTD-As be main supervisors,
    # so we exclude them from the directory.
    "Ricercatori/Ricercatrici a tempo determinato di tipo A": (
        "Assistant Professor (RTD-A)",
        False,
    ),
    # RTD-B is tenure-track (converts to Associate after 3 years on successful
    # evaluation). Kept.
    "Ricercatori/Ricercatrici a tempo determinato di tipo B": (
        "Assistant Professor",
        True,
    ),
    "Ricercatori/Ricercatrici in tenure track": (
        "Tenure-Track Researcher",
        True,
    ),
}


def _reformat_name(s: str) -> str:
    """Fallback for the provisional name before we fetch the profile page:
    'Last First' -> 'First Last'. The profile h2 gives us the clean form
    directly — see _parse_profile."""
    parts = clean_text(s).split()
    if len(parts) < 2:
        return clean_text(s)
    last = parts[0]
    first = " ".join(parts[1:])
    return f"{first} {last}"


def _list_faculty(base: str) -> list[tuple[str, str, str]]:
    """Return [(role_label_en, name, profile_url)] for kept roles, in page
    order. `base` is the per-department subdomain root."""
    index = (
        f"{base}/do/docenti.pl/Search?"
        "format=6;sort=U2;max=5000;sf=0;title=Suddivisi+per+ruolo"
    )
    html = get(index)
    soup = BeautifulSoup(html, "html.parser")
    current_role_en: str | None = None
    current_kept = False
    out: list[tuple[str, str, str]] = []
    seen: set[str] = set()
    for node in soup.find_all(True):
        if node.name in ("h3", "h4", "h5"):
            label = clean_text(node.get_text(" ", strip=True))
            if label in _ROLES:
                title_en, keep = _ROLES[label]
                current_role_en = title_en if keep else None
                current_kept = keep
            else:
                current_role_en = None
                current_kept = False
        elif (
            node.name == "a"
            and current_kept
            and current_role_en
            and node.get("href", "").startswith("/do/docenti.pl/Show?_id=")
        ):
            name = clean_text(node.get_text(" ", strip=True))
            href = urljoin(base, node["href"])
            if not name or href in seen:
                continue
            seen.add(href)
            out.append((current_role_en, _reformat_name(name), href))
    return out


def _parse_profile(name: str, url: str, role_en: str, dept_label: str) -> Faculty:
    html = get(url)
    soup = BeautifulSoup(html, "html.parser")

    row = soup.find(
        "div", class_=lambda c: c and "row" in c and "mb-3" in c
    )
    row_text = row.get_text(" ", strip=True) if row else ""

    # Prefer the profile page's own h2 rendering of the name — compound
    # surnames like "Di Nardo" come out correctly ordered there.
    if row:
        name_el = row.find(["h1", "h2", "h3"])
        if name_el:
            clean = clean_text(name_el.get_text(" ", strip=True))
            if clean:
                name = clean

    photo = ""
    for img in soup.find_all("img"):
        src = img.get("src", "")
        if "campusnet.unito.it/docenti/att/" in src and ".fotografia." in src:
            photo = src
            break

    ssd_name = ""
    m = re.search(
        r"SSD:\s*([A-Z0-9\-/]+)\s*-\s*([^O]{3,80}?)\s*(?:ORCID:|$)", row_text
    )
    if m:
        ssd_name = clean_text(m.group(2))

    orcid = ""
    if row:
        orcid_a = row.find("a", href=lambda h: h and "orcid.org" in h)
        if orcid_a:
            orcid = orcid_a["href"].strip()

    group_name = ""
    group_url = ""
    for h in soup.find_all(["h2", "h3", "h4", "h5"]):
        if "Gruppi di ricerca" in h.get_text(strip=True):
            nxt = h.find_next()
            for _ in range(40):
                if nxt is None:
                    break
                if (
                    getattr(nxt, "name", None) == "a"
                    and "/do/gruppi.pl" in nxt.get("href", "")
                ):
                    group_name = clean_text(nxt.get_text(" ", strip=True))
                    group_url = nxt["href"].strip()
                    break
                nxt = nxt.find_next()
            break

    areas: list[str] = []
    if ssd_name:
        areas.append(ssd_name)
    if group_name and group_name.lower() not in {a.lower() for a in areas}:
        areas.append(group_name)

    summary_bits = []
    if ssd_name:
        summary_bits.append(f"Scientific discipline: {ssd_name}.")
    if group_name:
        summary_bits.append(f"Research group: {group_name}.")
    summary = " ".join(summary_bits)

    return {
        "id": slugify("turin", name),
        "name": name,
        "institution": "Turin",
        "department": dept_label,
        "title": role_en,
        "roles": [group_name] if group_name else [],
        "research_areas": areas[:4],
        "summary": summary,
        "profile_url": url,
        "lab_url": group_url if group_url else "",
        "scholar_url": "",
        "orcid": orcid,
        "photo_url": photo,
    }


def scrape() -> list[Faculty]:
    all_out: list[Faculty] = []
    seen_ids: set[str] = set()
    for base, label in _DEPARTMENTS:
        try:
            people = _list_faculty(base)
        except Exception as e:
            print(f"  [turin_depts] FAIL listing {label}: {e}")
            continue
        print(f"[turin_depts] {len(people):3} listed  |  {label}")
        kept = 0
        for role, name, url in people:
            try:
                rec = _parse_profile(name, url, role, label)
            except Exception as e:
                print(f"  [turin_depts] skip {name} @ {url}: {e}")
                continue
            # Cross-department dedupe: a prof appearing under multiple
            # campusnet sites keeps the first department we scraped.
            if rec["id"] in seen_ids:
                continue
            seen_ids.add(rec["id"])
            all_out.append(rec)
            kept += 1
        print(f"             kept {kept} unique records")
    return all_out


def main() -> None:
    out_dir = Path(__file__).resolve().parents[1] / "out"
    out_dir.mkdir(exist_ok=True)
    records = scrape()
    (out_dir / "turin_depts.json").write_text(
        json.dumps(records, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"[turin_depts] wrote {len(records)} records total")


if __name__ == "__main__":
    main()
