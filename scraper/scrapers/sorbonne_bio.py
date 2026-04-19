"""Sorbonne University — biology faculty scraper.

Data source: Institut de Biologie Paris-Seine (IBPS), one of the main biology
research institutes at Sorbonne University's Faculty of Sciences. IBPS
organises its ~50 research teams under four UMR units (LCQB, Dev2A, NeuroSU,
LJP). Each team has a public page with a team-leader block linking to that
person's IBPS directory profile.

We extract one record per team leader. If a team has multiple leaders, each
becomes its own record sharing the team name as department.

Run with:
    python -m scrapers.sorbonne_bio
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from scrapers._http import get
from schema import Faculty, clean_text, slugify


BASE = "https://www.ibps.sorbonne-universite.fr"
INDEX = f"{BASE}/en/research"

# Paths under /en/research/ that are "unit" landing pages, not team pages.
# Each of these aggregates sub-team pages that we *do* want to scrape.
_UNIT_SLUGS = {
    "computational-quantitative-and-synthetic-biology",
    "neuroscience",
    "development-adaptations-and-aging",
    "umr-8237-ljp",
    "computational-and-quantitative-biology",
    "biological-adaptation-and-ageing",
    "developmental-biology-laboratory",
    "teaching",
    "teaching/bachelors-masters-degrees",
    "teaching/doctoral-schools",
}

# Map unit slug -> human-readable department label. Falls back to the slug if missing.
_UNIT_LABEL = {
    "computational-quantitative-and-synthetic-biology": "Computational, Quantitative and Synthetic Biology (LCQB)",
    "neuroscience": "Center for Neuroscience Sorbonne University (NeuroSU)",
    "development-adaptations-and-aging": "Development, Adaptations and Aging (Dev2A)",
    "umr-8237-ljp": "Laboratoire Jean Perrin (LJP)",
}


def list_team_pages() -> list[tuple[str, str]]:
    """Return (team_label, absolute_url) for every team page linked from /en/research."""
    html = get(INDEX)
    soup = BeautifulSoup(html, "html.parser")
    seen: set[str] = set()
    out: list[tuple[str, str]] = []
    for a in soup.find_all("a", href=True):
        href: str = a["href"]
        if "/en/research/" not in href:
            continue
        rel = href.split("/en/research/", 1)[1].strip("/")
        if not rel or rel in _UNIT_SLUGS or rel.startswith("teaching"):
            continue
        # Must be at least unit/team (two segments).
        if rel.count("/") < 1:
            continue
        url = urljoin(BASE, href)
        if url in seen:
            continue
        seen.add(url)
        label = clean_text(a.get_text(" ", strip=True)) or rel.split("/")[-1].replace("-", " ")
        out.append((label, url))
    return out


def _extract_team_leaders(soup: BeautifulSoup) -> list[dict]:
    """Return [{name, profile_url}] from the 'Team leader(s)' section."""
    leaders: list[dict] = []
    seen_names: set[str] = set()
    for h in soup.find_all(["h2", "h3", "h4"]):
        if "team leader" in h.get_text(" ", strip=True).lower():
            nxt = h.find_next_sibling()
            # Walk forward until the next header of the same level or below.
            while nxt is not None and nxt.name not in ("h2", "h3", "h4"):
                # Each leader block is a <div> containing an anchor to the directory profile.
                for a in nxt.find_all("a", href=True) if hasattr(nxt, "find_all") else []:
                    href: str = a["href"]
                    if "/ibps/directory/" not in href.lower() and "/annuaire/" not in href.lower():
                        continue
                    name = clean_text(a.get_text(" ", strip=True))
                    if not name or name.lower() in seen_names:
                        continue
                    seen_names.add(name.lower())
                    leaders.append({"name": name, "profile_url": urljoin(BASE, href)})
                nxt = nxt.find_next_sibling()
            break
    return leaders


def _team_title(soup: BeautifulSoup, fallback: str) -> str:
    """First non-noise h1/h2 on the page — the team's display name."""
    noise = {
        "more...", "highlights", "future directions", "collaborations",
        "team leader", "team leaders", "staff scientists", "graduate students",
        "scientific support staff", "post-doctoral fellows", "publications",
        "other (volunteers, sabbatical,alumni...)",
    }
    for h in soup.find_all(["h1", "h2", "h3"]):
        t = clean_text(h.get_text(" ", strip=True))
        low = t.lower()
        if not t or any(n in low for n in noise):
            continue
        # Ignore short/anchor headers.
        if len(t) < 3:
            continue
        return t
    return fallback


def _summary(soup: BeautifulSoup) -> str:
    """Concatenate the first few substantive paragraphs after the team title."""
    # The team description lives in a `<div class="section right">` immediately
    # after the h2 page title. Fall back to the first long <p> anywhere if the
    # layout differs.
    blocks: list[str] = []
    for div in soup.find_all("div"):
        classes = " ".join(div.get("class", []))
        if "section" in classes and "right" in classes:
            text = clean_text(div.get_text(" ", strip=True))
            if len(text) > 120:
                blocks.append(text)
                if len(blocks) >= 2:
                    break
    if not blocks:
        for p in soup.find_all("p"):
            text = clean_text(p.get_text(" ", strip=True))
            if len(text) > 150:
                blocks.append(text)
                if len(blocks) >= 2:
                    break
    return "\n\n".join(blocks)[:1800]


def _research_areas_from_title(title: str) -> list[str]:
    """Very light keyword-splitter for research areas derived from the team name.
    IBPS team names read like keyword lists already (e.g. "Telomere & Genome
    Stability"), so we just split on common separators."""
    parts = re.split(r"[,;/&]|\band\b|\bof\b|:|\(|\)", title)
    out: list[str] = []
    for p in parts:
        p = clean_text(p)
        if not p:
            continue
        # Drop obvious acronym-only tokens that are just unit codes.
        if re.fullmatch(r"[A-Z]{2,6}\d*", p):
            continue
        if len(p) <= 2:
            continue
        out.append(p)
    return out[:6]


def _unit_label(url: str) -> str:
    m = re.search(r"/en/research/([^/]+)/", url)
    if not m:
        return "Institut de Biologie Paris-Seine (IBPS)"
    slug = m.group(1)
    label = _UNIT_LABEL.get(slug, slug.replace("-", " ").title())
    return f"IBPS — {label}"


def scrape() -> list[Faculty]:
    teams = list_team_pages()
    print(f"[sorbonne_bio] {len(teams)} team pages found")
    out: list[Faculty] = []
    for team_label, url in teams:
        try:
            html = get(url)
            soup = BeautifulSoup(html, "html.parser")
            title = _team_title(soup, team_label)
            leaders = _extract_team_leaders(soup)
            summary = _summary(soup)
            dept = _unit_label(url)
            if not leaders:
                # No leader could mean the team block uses an uncommon layout —
                # emit a placeholder record keyed on the team so the team
                # still shows up rather than silently dropping it. We flag this
                # in the name so it's obvious in QA.
                print(f"  [sorbonne_bio] no team leader extracted: {title} @ {url}")
                continue
            for L in leaders:
                rec: Faculty = {
                    "id": slugify("sorbonne", "bio", L["name"]),
                    "name": L["name"],
                    "institution": "Sorbonne",
                    "department": dept,
                    "title": f"Team Leader — {title}",
                    "roles": [title],
                    "research_areas": _research_areas_from_title(title),
                    "summary": summary,
                    "profile_url": L["profile_url"],
                    "lab_url": url,
                    "scholar_url": "",
                    "orcid": "",
                    "photo_url": "",
                }
                out.append(rec)
        except Exception as e:
            print(f"  [sorbonne_bio] skip {team_label} @ {url}: {e}")
    return out


def main() -> None:
    out_dir = Path(__file__).resolve().parents[1] / "out"
    out_dir.mkdir(exist_ok=True)
    records = scrape()
    (out_dir / "sorbonne_bio.json").write_text(
        json.dumps(records, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"[sorbonne_bio] wrote {len(records)} records")


if __name__ == "__main__":
    main()
