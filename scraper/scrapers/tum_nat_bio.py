"""TUM School of Natural Sciences — Department of Bioscience faculty scraper.

Complements tum_bio.py (which covers TUM School of Life Sciences at
Weihenstephan). The Department of Bioscience under the NAT school lives at
https://www.nat.tum.de/en/nat/about/profs/profs-bio/ and lists its chair
holders as `<div class="c-tummemberlist__member">` blocks with name, rank,
and a TUMonline vCard URL + photo.

For research information, each chair has a canonical page on
professoren.tum.de at /en/<lastname-firstname> that exposes their chair
name and a research-focus paragraph. We resolve the slug from the name and
enrich the record if the page exists; otherwise the bare NAT listing is
still emitted so the person isn't dropped entirely.

Run with:
    python -m scrapers.tum_nat_bio
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


NAT_BASE = "https://www.nat.tum.de"
NAT_BIO_INDEX = f"{NAT_BASE}/en/nat/about/profs/profs-bio/"
PROFS_BASE = "https://www.professoren.tum.de/en"

DEPARTMENT = "TUM School of Natural Sciences — Department of Bioscience"


def _strip_accents(s: str) -> str:
    """Umlaut-safe accent stripper: ö->o, ü->u, ß->ss, etc."""
    s = s.replace("ß", "ss")
    return "".join(
        c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c)
    )


def _candidate_slugs(name: str) -> list[str]:
    """Produce professoren.tum.de URL slugs to try for a given full name.

    The site uses `<lastname>-<firstname>` (lowercase, ASCII). Multi-word
    surnames like 'Baer de Oliveira Mann' aren't deterministic — we try the
    last-word-as-surname form first, then the two-word-surname form, then the
    whole-tail form. First URL that returns 200 wins.
    """
    clean = _strip_accents(clean_text(name)).lower()
    parts = re.split(r"\s+", clean)
    if len(parts) < 2:
        return []
    first = parts[0]
    # Try: {last}-{first}, {last2 last}-{first}, {last_three last_two last}-{first}
    slugs = []
    for take in range(1, min(4, len(parts))):
        last = "-".join(parts[-take:])
        slugs.append(re.sub(r"[^a-z-]", "", f"{last}-{first}"))
    # Dedupe preserving order.
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
        # Reject the "professor not found" stub — real pages have a school row.
        text = soup.get_text("\n", strip=True)
        if "Professorship" not in text:
            continue
        # Professorship (chair) label: comes right after the word "Professorship".
        chair = ""
        m = re.search(r"Professorship\n([^\n]{3,200})", text)
        if m:
            chair = clean_text(m.group(1))
        # Research paragraph: after "Academic Career and Research Areas" header,
        # we want the first 1-3 sentences that describe the research focus.
        summary = ""
        m = re.search(
            r"Academic Career and Research Areas\n(.+?)(?=\n(?:Courses|Awards|Key Publications|$))",
            text,
            re.S,
        )
        if m:
            block = re.sub(r"\s+", " ", m.group(1)).strip()
            # Keep the first paragraph-ish segment — ideally the focus summary.
            summary = block[:1200]
        return {"profile_url": url, "chair": chair, "summary": summary}
    return {}


def _parse_member(block) -> dict:
    """Pull the base record (name, photo, vcard url) from a NAT member block."""
    name_div = block.find("div", class_="c-tummemberlist__name")
    if not name_div:
        return {}
    a = name_div.find("a", href=True)
    if not a:
        return {}
    # The <span class="title"> holds the academic rank ("Prof. Dr. rer. nat."),
    # which sits inside the link text alongside the name.
    title_span = a.find("span", class_="title")
    rank = clean_text(title_span.get_text(" ", strip=True)) if title_span else ""
    name_text = clean_text(a.get_text(" ", strip=True))
    if rank and name_text.startswith(rank):
        name = clean_text(name_text[len(rank):])
    else:
        name = name_text
    vcard_url = a["href"].strip()

    # Photo is a campus.tum.de visitenkarte image. Keep it even though it's
    # 50px-wide in the source HTML — the image URL returns a larger image.
    photo = ""
    img = block.find("img", class_="portrait")
    if img and img.get("src"):
        photo = urljoin(NAT_BASE, img["src"])

    return {
        "name": name,
        "rank": rank or "Full Professor",
        "vcard_url": vcard_url,
        "photo_url": photo,
    }


def scrape() -> list[Faculty]:
    html = get(NAT_BIO_INDEX)
    soup = BeautifulSoup(html, "html.parser")
    members = soup.select(".c-tummemberlist__member")
    print(f"[tum_nat_bio] {len(members)} professors listed on NAT Bioscience index")

    out: list[Faculty] = []
    enriched = 0
    for m in members:
        base = _parse_member(m)
        if not base:
            continue
        extra = _enrich_from_professoren(base["name"])
        if extra:
            enriched += 1
        chair = extra.get("chair", "")
        summary = extra.get("summary", "")
        # Prefer the canonical professoren.tum.de URL as profile_url when we
        # have it; fall back to the TUMonline vCard.
        profile_url = extra.get("profile_url") or base["vcard_url"]

        # Research areas: derive from chair name (like tum_bio.py), which is
        # TUM's own phrase for the professorship's scope.
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
            "department": DEPARTMENT,
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
    print(f"[tum_nat_bio] enriched {enriched}/{len(out)} from professoren.tum.de")
    return out


def main() -> None:
    out_dir = Path(__file__).resolve().parents[1] / "out"
    out_dir.mkdir(exist_ok=True)
    records = scrape()
    (out_dir / "tum_nat_bio.json").write_text(
        json.dumps(records, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"[tum_nat_bio] wrote {len(records)} records")


if __name__ == "__main__":
    main()
