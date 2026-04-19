"""University of Turin (UniTO) — biology faculty scraper.

Data source: the DBIOS department — Dipartimento di Scienze della Vita e
Biologia dei Sistemi — which publishes its personnel index grouped by role at

    /do/docenti.pl/Search?format=6;sort=U2;max=5000;sf=0;title=Suddivisi+per+ruolo

Each person has a profile page at /do/docenti.pl/Show?_id=<username>. The
profile exposes their position, SSD (scientific discipline code), research
group, and ORCID in a structured `<div class="row mb-3">` block near the top.

We keep faculty-ranked records only (full professors, associate professors,
university researchers, tenure-track). PhD students, contract staff, and
emeriti are excluded.

Run with:
    python -m scrapers.turin_bio
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from scrapers._http import get
from schema import Faculty, clean_text, slugify


BASE = "https://www.dbios.unito.it"
INDEX = (
    f"{BASE}/do/docenti.pl/Search?"
    "format=6;sort=U2;max=5000;sf=0;title=Suddivisi+per+ruolo"
)

# Italian role label -> (English title, keep?). `keep=False` skips the role.
_ROLES: dict[str, tuple[str, bool]] = {
    "Professori/Professoresse ordinari/e": ("Full Professor", True),
    "Professori/Professoresse associati/e": ("Associate Professor", True),
    "Professori/Professoresse emeriti/e": ("Emeritus Professor", False),
    "Ricercatori/Ricercatrici universitari/e": ("Researcher", True),
    "Ricercatori/Ricercatrici a tempo determinato di tipo A": (
        "Assistant Professor (Type A)",
        True,
    ),
    "Ricercatori/Ricercatrici a tempo determinato di tipo B": (
        "Assistant Professor (Type B)",
        True,
    ),
    "Ricercatori/Ricercatrici in tenure track": (
        "Tenure-Track Researcher",
        True,
    ),
}

DEPARTMENT = "Department of Life Sciences and Systems Biology (DBIOS)"


def _reformat_name(s: str) -> str:
    """Turin lists names as 'Last First' (e.g. 'Maffei Massimo Emilio'). Reorder
    to 'First Last' for display consistency with the rest of the directory.
    Heuristic: treat the first token as the family name only if the whole
    string is >= 2 tokens; otherwise leave alone."""
    parts = clean_text(s).split()
    if len(parts) < 2:
        return clean_text(s)
    last = parts[0]
    first = " ".join(parts[1:])
    return f"{first} {last}"


def _list_faculty() -> list[tuple[str, str, str]]:
    """Return [(role_label_en, name, profile_url)] for kept roles, in page order."""
    html = get(INDEX)
    soup = BeautifulSoup(html, "html.parser")
    current_role_en: str | None = None
    current_kept = False
    out: list[tuple[str, str, str]] = []
    seen: set[str] = set()
    # Walk document order: switch the active role when we encounter a role
    # header, and collect docenti links while the active role is kept.
    for node in soup.find_all(True):
        if node.name in ("h3", "h4", "h5"):
            label = clean_text(node.get_text(" ", strip=True))
            if label in _ROLES:
                title_en, keep = _ROLES[label]
                current_role_en = title_en if keep else None
                current_kept = keep
            else:
                # Any other section header ends the previous role block.
                current_role_en = None
                current_kept = False
        elif (
            node.name == "a"
            and current_kept
            and current_role_en
            and node.get("href", "").startswith("/do/docenti.pl/Show?_id=")
        ):
            name = clean_text(node.get_text(" ", strip=True))
            href = urljoin(BASE, node["href"])
            if not name or href in seen:
                continue
            seen.add(href)
            out.append((current_role_en, _reformat_name(name), href))
    return out


def _parse_profile(name: str, url: str, role_en: str) -> Faculty:
    html = get(url)
    soup = BeautifulSoup(html, "html.parser")

    # Header row with position, SSD, ORCID.
    row = soup.find(
        "div", class_=lambda c: c and "row" in c and "mb-3" in c
    )
    row_text = row.get_text(" ", strip=True) if row else ""

    # The profile page renders the name correctly as "First Last" in an h2,
    # compound surnames intact ("Giovanna Di Nardo"). Prefer that over the
    # index-page "Last First" form which we only split with fragile heuristics.
    if row:
        name_el = row.find(["h1", "h2", "h3"])
        if name_el:
            clean = clean_text(name_el.get_text(" ", strip=True))
            if clean:
                name = clean

    # Photo — UniTO hosts each staff member's headshot at a predictable path
    # keyed on their campusnet _id: /docenti/att/<id>.fotografia.<ext>
    # The extension varies per record (png or jpg), so match on the stem.
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

    # Research group — first /do/gruppi.pl/Show link under the "Gruppi di ricerca" section.
    group_name = ""
    group_url = ""
    for h in soup.find_all(["h2", "h3", "h4", "h5"]):
        if "Gruppi di ricerca" in h.get_text(strip=True):
            nxt = h.find_next()
            # Scan the next 40 siblings/descendants for a gruppi link.
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

    # Research areas: derive from SSD name + research group label — both are
    # short domain phrases, so just stack them.
    areas: list[str] = []
    if ssd_name:
        areas.append(ssd_name)
    if group_name and group_name.lower() not in {a.lower() for a in areas}:
        areas.append(group_name)

    # Summary: join SSD + group into a readable sentence; profile pages don't
    # publish a free-text research abstract.
    summary_bits = []
    if ssd_name:
        summary_bits.append(f"Scientific discipline: {ssd_name}.")
    if group_name:
        summary_bits.append(f"Research group: {group_name}.")
    summary = " ".join(summary_bits)

    return {
        "id": slugify("turin", "bio", name),
        "name": name,
        "institution": "Turin",
        "department": DEPARTMENT,
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
    people = _list_faculty()
    print(f"[turin_bio] {len(people)} faculty listed")
    out: list[Faculty] = []
    for role, name, url in people:
        try:
            out.append(_parse_profile(name, url, role))
        except Exception as e:
            print(f"  [turin_bio] skip {name} @ {url}: {e}")
    return out


def main() -> None:
    out_dir = Path(__file__).resolve().parents[1] / "out"
    out_dir.mkdir(exist_ok=True)
    records = scrape()
    (out_dir / "turin_bio.json").write_text(
        json.dumps(records, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"[turin_bio] wrote {len(records)} records")


if __name__ == "__main__":
    main()
