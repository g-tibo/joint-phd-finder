"""TUM School of Life Sciences — faculty scraper.

Data source: the three department-level professor index pages under
https://www.ls.tum.de/en/ls/about-us/professors/, each a TYPO3 page that
lists its chair holders as `div.frame.c-card` blocks containing a
professorship name, a photo, and a link to the canonical TUM professor
profile on `professoren.tum.de`.

We scrape all three departments (Molecular Life Sciences, Life Science
Systems, Life Science Engineering) for the v1 Joint PhD template — biology in
the widest sense, so plant/environmental/ecology chairs are kept too.

Run with:
    python -m scrapers.tum_bio
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from scrapers._http import get
from schema import Faculty, clean_text, slugify


BASE = "https://www.ls.tum.de"

# Each index page corresponds to one research department. The label becomes
# the `department` field on every record from that page.
_INDEXES = [
    (
        f"{BASE}/en/ls/about-us/professors/professors-of-the-department-molecular-life-sciences/",
        "TUM School of Life Sciences — Molecular Life Sciences",
    ),
    (
        f"{BASE}/en/ls/about-us/professors/professors-of-the-department-life-science-systems/",
        "TUM School of Life Sciences — Life Science Systems",
    ),
    (
        f"{BASE}/en/ls/about-us/professors/professors-of-the-department-life-science-engineering/",
        "TUM School of Life Sciences — Life Science Engineering",
    ),
]


def _parse_block(block, dept: str) -> Faculty | None:
    """Parse one `div.frame.c-card` block into a Faculty record."""
    # Professorship name is the first h4 > a.
    chair_a = block.find("h4")
    chair_name = clean_text(chair_a.get_text(" ", strip=True)) if chair_a else ""
    chair_link = ""
    if chair_a:
        a = chair_a.find("a", href=True)
        if a:
            chair_link = a["href"].strip()

    # Person's name: first external-link inside a <p>, with a <strong> child.
    bodytext = block.find("div", class_="ce-bodytext")
    if not bodytext:
        return None
    person_a = bodytext.find("a", class_="external-link", href=True)
    name = ""
    profile_url = ""
    if person_a:
        # The strong child contains the name; fall back to link text.
        strong = person_a.find("strong")
        name = clean_text((strong or person_a).get_text(" ", strip=True))
        profile_url = person_a["href"].strip()
    if not name:
        return None

    # Title (rank) — the text before the link, e.g. "Prof. Dr." — is
    # noisy and often identical across all records, so don't dedupe it out.
    title = "Full Professor"
    # Refine if the block explicitly states a different rank.
    first_p = bodytext.find("p")
    if first_p:
        raw = clean_text(first_p.get_text(" ", strip=True))
        if "Jun.-Prof" in raw or "Junior Professor" in raw:
            title = "Junior Professor"
        elif "Prof. Dr." in raw or raw.startswith("Prof."):
            title = "Full Professor"

    # Photo — the image src is site-relative.
    photo = ""
    img = block.find("img")
    if img and img.get("src"):
        photo = urljoin(BASE, img["src"])

    # Derive research-area keywords from the chair name. TUM chair names are
    # already domain phrases like "Plant Developmental Biology" or "Nutrition
    # and Immunology", so we just split on conjunctions.
    parts = re.split(r"[,;/&]|\band\b|\bof\b|\(|\)", chair_name)
    areas = [clean_text(p) for p in parts if clean_text(p)]
    areas = [a for a in areas if 2 < len(a) < 60 and not re.fullmatch(r"[A-Z]{2,6}", a)]

    roles = [chair_name] if chair_name else []

    return {
        "id": slugify("tum", "bio", name),
        "name": name,
        "institution": "TUM",
        "department": dept,
        "title": title,
        "roles": roles,
        "research_areas": areas[:6],
        "summary": f"Chair: {chair_name}." if chair_name else "",
        "profile_url": profile_url,
        "lab_url": chair_link if chair_link and chair_link != profile_url else "",
        "scholar_url": "",
        "orcid": "",
        "photo_url": photo,
    }


def scrape() -> list[Faculty]:
    out: list[Faculty] = []
    seen_ids: set[str] = set()
    for url, dept in _INDEXES:
        html = get(url)
        soup = BeautifulSoup(html, "html.parser")
        # The professor cards are `<div class="frame ... c-card ...">` with an
        # id like `c3369`. Select them by class + id pattern.
        blocks = [
            d
            for d in soup.find_all("div", class_="frame")
            if "c-card" in " ".join(d.get("class", []))
            and re.fullmatch(r"c\d+", d.get("id", ""))
            and d.find("div", class_="ce-bodytext")  # skip the header/intro frame
        ]
        kept = 0
        for b in blocks:
            rec = _parse_block(b, dept)
            if not rec:
                continue
            if rec["id"] in seen_ids:
                # Same person may appear on multiple department pages (cross
                # appointment). Keep the first occurrence — usually matches
                # their "main" dept in the site's ordering.
                continue
            seen_ids.add(rec["id"])
            out.append(rec)
            kept += 1
        print(f"[tum_bio] {dept}: {kept} records")
    return out


def main() -> None:
    out_dir = Path(__file__).resolve().parents[1] / "out"
    out_dir.mkdir(exist_ok=True)
    records = scrape()
    (out_dir / "tum_bio.json").write_text(
        json.dumps(records, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"[tum_bio] wrote {len(records)} records total")


if __name__ == "__main__":
    main()
