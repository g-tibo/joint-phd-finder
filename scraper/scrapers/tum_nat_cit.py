"""TUM School of Natural Sciences + CIT Mathematics — faculty scraper.

Complements tum_bio.py (TUM School of Life Sciences, Weihenstephan) by
covering ranked-faculty departments at TUM's other science schools that
are relevant to a Joint-PhD template:

- NAT — Department of Bioscience
- NAT — Department of Chemistry
- NAT — Department of Physics
- CIT — Department of Mathematics

All four pages list chair holders + ranked faculty, but with two slightly
different widgets:

- NAT uses `<div class="c-tummemberlist__member">` with a TUMonline vCard
  link and photo.
- CIT Math uses `<div class="c-tummemberlist__gallery-item">` with a direct
  link to the professor's personal page inside math.cit.tum.de and photo.

For research information we resolve each professor's canonical page at
professoren.tum.de/en/<lastname-firstname>. That page exposes the chair
name and a research-focus paragraph. When the slug can't be resolved
(compound surnames, umlauts without a standard transcription, or simply
no canonical page) we still emit the record with the department listing's
profile URL, name, rank, and photo — so the person shows up in Browse.

Ranks captured: W3 full professors, W2 associates, W1 tenure-track /
junior professors. No postdocs, no academic staff below W1 — the index
pages we scrape only surface ranked professorships, so this is enforced
by the source.

Run with:
    python -m scrapers.tum_nat_cit
"""

from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from scrapers._http import get
from schema import Faculty, clean_text, slugify


PROFS_BASE = "https://www.professoren.tum.de/en"

# Each department: (index URL, base host for relative links, CSS selector for
# member blocks, display department label).
# - `.c-tummemberlist__member` is the NAT professor-list widget (bio/chem/phys).
# - `.c-tummemberlist__gallery-item` is the CIT Math professor-gallery widget.
_DEPARTMENTS: list[tuple[str, str, str, str]] = [
    (
        "https://www.nat.tum.de/en/nat/about/profs/profs-bio/",
        "https://www.nat.tum.de",
        ".c-tummemberlist__member",
        "TUM School of Natural Sciences — Department of Bioscience",
    ),
    (
        "https://www.nat.tum.de/en/nat/about/profs/profs-ch/",
        "https://www.nat.tum.de",
        ".c-tummemberlist__member",
        "TUM School of Natural Sciences — Department of Chemistry",
    ),
    (
        "https://www.nat.tum.de/en/nat/about/profs/professors-in-physics/",
        "https://www.nat.tum.de",
        ".c-tummemberlist__member",
        "TUM School of Natural Sciences — Department of Physics",
    ),
    (
        "https://www.math.cit.tum.de/en/math/people/professors/",
        "https://www.math.cit.tum.de",
        ".c-tummemberlist__gallery-item",
        "TUM School of Computation, Information and Technology — Department of Mathematics",
    ),
]


def _strip_accents(s: str) -> str:
    """Umlaut-safe accent stripper: ö->o, ü->u, ß->ss, etc."""
    s = s.replace("ß", "ss")
    return "".join(
        c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c)
    )


def _candidate_slugs(name: str) -> list[str]:
    """Produce professoren.tum.de URL slugs to try for a given full name.

    The site uses `<lastname>-<firstname>` (lowercase, ASCII). Multi-word
    surnames (e.g. 'Baer de Oliveira Mann') aren't deterministic — we try the
    last-word-as-surname form first, then 2-word and 3-word compounds. First
    URL that returns a real page wins.
    """
    clean = _strip_accents(clean_text(name)).lower()
    parts = re.split(r"\s+", clean)
    if len(parts) < 2:
        return []
    first = parts[0]
    slugs: list[str] = []
    for take in range(1, min(4, len(parts))):
        last = "-".join(parts[-take:])
        slugs.append(re.sub(r"[^a-z-]", "", f"{last}-{first}"))
    seen: set[str] = set()
    out: list[str] = []
    for s in slugs:
        if s and s not in seen:
            seen.add(s)
            out.append(s)
    return out


def _enrich_from_professoren(name: str) -> dict:
    """Try the canonical professor profile on professoren.tum.de and pull
    professorship + research summary if the page exists."""
    for slug in _candidate_slugs(name):
        url = f"{PROFS_BASE}/{slug}"
        try:
            html = get(url)
        except Exception:
            continue
        soup = BeautifulSoup(html, "html.parser")
        text = soup.get_text("\n", strip=True)
        if "Professorship" not in text:
            continue
        chair = ""
        m = re.search(r"Professorship\n([^\n]{3,200})", text)
        if m:
            chair = clean_text(m.group(1))
        summary = ""
        m = re.search(
            r"Academic Career and Research Areas\n(.+?)(?=\n(?:Courses|Awards|Key Publications|$))",
            text,
            re.S,
        )
        if m:
            block = re.sub(r"\s+", " ", m.group(1)).strip()
            summary = block[:1200]
        return {"profile_url": url, "chair": chair, "summary": summary}
    return {}


def _parse_member(block, base_host: str) -> dict:
    """Pull the base record (name, rank, photo, profile link) from either
    member widget — member-list or gallery-item. They differ in where the
    photo sits but share the `.c-tummemberlist__name` inner block."""
    name_div = block.find("div", class_="c-tummemberlist__name")
    if not name_div:
        return {}
    a = name_div.find("a", href=True)
    if not a:
        return {}
    title_span = a.find("span", class_="title")
    rank = clean_text(title_span.get_text(" ", strip=True)) if title_span else ""
    name_text = clean_text(a.get_text(" ", strip=True))
    if rank and name_text.startswith(rank):
        name = clean_text(name_text[len(rank):])
    else:
        name = name_text
    profile_href = a["href"].strip()
    profile_url = (
        urljoin(base_host, profile_href) if profile_href.startswith("/") else profile_href
    )

    photo = ""
    img = block.find("img", class_="portrait")
    if img and img.get("src"):
        photo = urljoin(base_host, img["src"])

    return {
        "name": name,
        "rank": rank or "Full Professor",
        "profile_url": profile_url,
        "photo_url": photo,
    }


def _dept_to_records(
    url: str, base_host: str, selector: str, dept_label: str
) -> list[Faculty]:
    html = get(url)
    soup = BeautifulSoup(html, "html.parser")
    members = soup.select(selector)
    print(f"[tum_nat_cit] {len(members):3} listed  |  {dept_label}")

    out: list[Faculty] = []
    enriched = 0
    for m in members:
        base = _parse_member(m, base_host)
        if not base:
            continue
        extra = _enrich_from_professoren(base["name"])
        if extra:
            enriched += 1
        chair = extra.get("chair", "")
        summary = extra.get("summary", "")
        profile_url = extra.get("profile_url") or base["profile_url"]

        areas: list[str] = []
        if chair:
            parts = re.split(r"[,;/&]|\band\b|\bof\b|\(|\)", chair)
            areas = [clean_text(p) for p in parts if clean_text(p)]
            areas = [
                a for a in areas
                if 2 < len(a) < 60 and not re.fullmatch(r"[A-Z]{2,6}", a)
            ]

        out.append({
            "id": slugify("tum", "nat", base["name"]),
            "name": base["name"],
            "institution": "TUM",
            "department": dept_label,
            "title": base["rank"] or "Full Professor",
            "roles": [chair] if chair else [],
            "research_areas": areas[:6],
            "summary": summary or (f"Chair: {chair}." if chair else ""),
            "profile_url": profile_url,
            "lab_url": "",
            "scholar_url": "",
            "orcid": "",
            "photo_url": base["photo_url"],
        })
    print(f"             enriched {enriched}/{len(out)} via professoren.tum.de")
    return out


def scrape() -> list[Faculty]:
    all_out: list[Faculty] = []
    seen_ids: set[str] = set()
    for url, base_host, selector, label in _DEPARTMENTS:
        try:
            recs = _dept_to_records(url, base_host, selector, label)
        except Exception as e:
            print(f"  [tum_nat_cit] FAIL {label}: {e}")
            continue
        # Dedupe cross-department appointments (e.g. a physics chemist).
        # First-seen wins — which will be the primary listing since we
        # iterate in dept order (Bio, Chem, Phys, Math).
        for r in recs:
            if r["id"] in seen_ids:
                continue
            seen_ids.add(r["id"])
            all_out.append(r)
    return all_out


def main() -> None:
    out_dir = Path(__file__).resolve().parents[1] / "out"
    out_dir.mkdir(exist_ok=True)
    records = scrape()
    (out_dir / "tum_nat_cit.json").write_text(
        json.dumps(records, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"[tum_nat_cit] wrote {len(records)} records total")


if __name__ == "__main__":
    main()
