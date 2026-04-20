"""Sorbonne University — STEM scraper beyond IBPS.

Complements sorbonne_bio.py (biology via IBPS) by covering the biggest
research institutes under the other UFRs of the Faculté des Sciences et
Ingénierie:

- IMJ-PRG  (UFR de Mathématiques — Institut de Mathématiques de Jussieu)
- LJLL     (UFR de Mathématiques — Laboratoire Jacques-Louis Lions)
- IPCM     (UFR de Chimie — Institut Parisien de Chimie Moléculaire)
- LCT      (UFR de Chimie — Laboratoire de Chimie Théorique)
- LKB      (UFR de Physique — Laboratoire Kastler Brossel)

Each institute uses its own CMS, so parsing logic is per-site. All three
share one output file and go through the same ranked-only filter.

Ranked-faculty-only policy (French system):
- KEEP: Professeur (PR), Maître/Maîtresse de conférences (MCF), Directeur
  de recherche (DR) — CNRS/INSERM/INRIA, Chargé/Chargée de recherche (CR).
- DROP: ATER (temporary teacher), Ingénieur de recherche, post-doctorant,
  doctorant, personnel technique, administration.

Run with:
    python -m scrapers.sorbonne_stem
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from scrapers._http import get
from schema import Faculty, clean_text, slugify


# French rank labels that qualify as ranked PhD-supervising faculty.
# Matching is case- and gender-insensitive ("Professeur", "Professeure",
# "Maître de conférences", "Maîtresse de conférences", etc.).
_RANKED_RE = re.compile(
    r"\b("
    r"professeur(?:e)?s?\s+des\s+universit[eé]s?"
    r"|professeur(?:e)?s?"
    r"|ma[iî]tre(?:sse)?s?\s+de\s+conf[eé]rences?"
    r"|direct(?:eur|rice)s?\s+de\s+recherche"
    r"|charg[ée](?:e)?s?\s+de\s+recherche"
    r")\b",
    re.I,
)


def _rank_english(french: str) -> str:
    """Map a French rank to an English title for the card."""
    low = french.lower()
    if "charg" in low and "recherche" in low:
        return "CNRS Researcher"
    if "direct" in low and "recherche" in low:
        return "CNRS Research Director"
    if "conf" in low:
        return "Associate Professor"
    if "professeur" in low:
        return "Full Professor"
    return french.strip()


# --------------------------------------------------------------------------- #
# IMJ-PRG — Institut de Mathématiques de Jussieu–Paris Rive Gauche
# --------------------------------------------------------------------------- #

IMJ_URL = "https://www.imj-prg.fr/enseignants-chercheur/"
IMJ_DEPT = "Institut de Mathématiques de Jussieu-Paris Rive Gauche (IMJ-PRG)"


def _scrape_imj() -> list[Faculty]:
    """IMJ-PRG ships a big <table> whose rows are:
    [Civilité, Nom, Équipe, Statut, Organisme, Site, Bureau, Téléphone].
    The Nom cell holds both a visible name and a hidden Bootstrap modal with
    a photo URL and a personal website URL. We use the table columns for the
    structured data and dip into the modal for the photo + lab URL."""
    html = get(IMJ_URL)
    soup = BeautifulSoup(html, "html.parser")
    rows = soup.select("table tr")
    out: list[Faculty] = []
    for r in rows[1:]:
        cells = r.find_all("td")
        if len(cells) < 5:
            continue
        name_cell = cells[1]
        name_btn = name_cell.find("button") or name_cell
        name_raw = clean_text(name_btn.get_text(" ", strip=True))
        # Index page shows "LASTNAME First Middle" — reorder to "First LASTNAME"
        # by uppercasing-contiguous letters as the surname-anchor.
        name = _imj_reformat_name(name_raw)

        team = clean_text(cells[2].get_text(" ", strip=True))
        status = clean_text(cells[3].get_text(" ", strip=True))
        org = clean_text(cells[4].get_text(" ", strip=True))
        if not _RANKED_RE.search(status):
            continue

        # Pull photo + personal URL from the modal body inside the Nom cell.
        photo = ""
        lab_url = ""
        modal_body = name_cell.find("div", class_="modal-body")
        if modal_body:
            img = modal_body.find("img")
            if img and img.get("src"):
                photo = img["src"].strip()
            a = modal_body.find("a", href=True)
            if a and a["href"].startswith("http"):
                lab_url = a["href"].strip()

        out.append({
            "id": slugify("sorbonne", "stem", name),
            "name": name,
            "institution": "Sorbonne",
            "department": f"{IMJ_DEPT} — {team}" if team else IMJ_DEPT,
            "title": _rank_english(status),
            "roles": [team] if team else [],
            "research_areas": _keywords_from(team),
            "summary": f"Research team: {team}. Institution: {org}." if team else "",
            "profile_url": lab_url or IMJ_URL,
            "lab_url": lab_url,
            "scholar_url": "",
            "orcid": "",
            "photo_url": photo,
        })
    print(f"[sorbonne_stem] IMJ-PRG: {len(out)} ranked faculty")
    return out


def _imj_reformat_name(raw: str) -> str:
    """'ACHAB Dehbia' -> 'Dehbia Achab'. The index uppercases the surname;
    uppercase-contiguous runs at the start identify it."""
    tokens = raw.split()
    if not tokens:
        return raw
    # Find the first token that is NOT ALL-UPPERCASE — that's the first name.
    split_idx = len(tokens)
    for i, t in enumerate(tokens):
        if t.upper() != t or not any(c.isalpha() for c in t):
            split_idx = i
            break
    surname = " ".join(tokens[:split_idx]).title()
    given = " ".join(tokens[split_idx:])
    if not given:
        return surname
    return f"{given} {surname}".strip()


# --------------------------------------------------------------------------- #
# LJLL — Laboratoire Jacques-Louis Lions
# --------------------------------------------------------------------------- #

LJLL_URL = "https://www.ljll.fr/liste-membres/"
LJLL_DEPT = "Laboratoire Jacques-Louis Lions (LJLL)"


def _scrape_ljll() -> list[Faculty]:
    """LJLL uses a JetEngine dynamic table. Each row has a named anchor to
    /membre/<slug>/ inside the Nom column; the rank sits in the
    fonctionstatut column; themes in `thmes` (sic), org in organisme."""
    html = get(LJLL_URL)
    soup = BeautifulSoup(html, "html.parser")
    rows = soup.select("table tr[data-item-object]")
    out: list[Faculty] = []
    for r in rows:
        cells = r.find_all("td")
        if len(cells) < 4:
            continue
        nom_cell = next(
            (c for c in cells if "jet-dynamic-table__col--nom" in " ".join(c.get("class", []))),
            None,
        ) or cells[0]
        status_cell = next(
            (c for c in cells if "fonctionstatut" in " ".join(c.get("class", []))),
            None,
        ) or cells[2] if len(cells) > 2 else None
        themes_cell = next(
            (c for c in cells if "thmes" in " ".join(c.get("class", []))),
            None,
        )
        org_cell = next(
            (c for c in cells if "organisme" in " ".join(c.get("class", []))),
            None,
        )
        site_cell = next(
            (c for c in cells if "siteweb" in " ".join(c.get("class", []))),
            None,
        )

        a = nom_cell.find("a", href=True)
        name_text = clean_text(a.get_text(" ", strip=True)) if a else clean_text(nom_cell.get_text(" ", strip=True))
        if not name_text:
            continue
        profile_url = a["href"].strip() if a else LJLL_URL

        status = clean_text(status_cell.get_text(" ", strip=True)) if status_cell else ""
        if not _RANKED_RE.search(status):
            continue

        themes = clean_text(themes_cell.get_text(" ", strip=True)) if themes_cell else ""
        org = clean_text(org_cell.get_text(" ", strip=True)) if org_cell else ""
        site = ""
        if site_cell:
            sa = site_cell.find("a", href=True)
            if sa and sa["href"].startswith("http"):
                site = sa["href"].strip()

        # Normalise LJLL's name form to "First Last". Their slug (achdou-yves)
        # gives us the correct family-first order after reversing.
        slug = profile_url.rstrip("/").split("/")[-1] if profile_url else ""
        name = _ljll_reformat_name(name_text, slug)

        out.append({
            "id": slugify("sorbonne", "stem", name),
            "name": name,
            "institution": "Sorbonne",
            "department": LJLL_DEPT,
            "title": _rank_english(status),
            "roles": [themes] if themes else [],
            "research_areas": _keywords_from(themes),
            "summary": (
                f"Research themes: {themes}. Institution: {org}."
                if themes or org else ""
            ),
            "profile_url": profile_url,
            "lab_url": site,
            "scholar_url": "",
            "orcid": "",
            "photo_url": "",
        })
    print(f"[sorbonne_stem] LJLL: {len(out)} ranked faculty")
    return out


def _ljll_reformat_name(visible: str, slug: str) -> str:
    """Visible column shows "Achdou Yves"; slug is "achdou-yves". We need
    "Yves Achdou". If the slug has 2+ parts, treat all-but-last as surname."""
    if slug and "-" in slug:
        parts = [p.replace("_", " ").title() for p in slug.split("-")]
        if len(parts) >= 2:
            # slug convention is lastname-firstname (lastname may be 1-word).
            return f"{parts[-1]} {' '.join(parts[:-1])}"
    # Fallback: reverse the visible text if it looks like "Last First".
    tokens = visible.split()
    if len(tokens) >= 2 and tokens[0] == tokens[0].title():
        return f"{' '.join(tokens[1:])} {tokens[0]}"
    return visible


# --------------------------------------------------------------------------- #
# IPCM — Institut Parisien de Chimie Moléculaire
# --------------------------------------------------------------------------- #

IPCM_URL = "https://ipcm.fr/linstitut/annuaires/"
IPCM_DEPT = "Institut Parisien de Chimie Moléculaire (IPCM)"

# Team labels that indicate administration / technical support — exclude the
# row. Real IPCM research teams are short acronyms (ECP, E-POM, CHEMBIO, …);
# service teams use functional names like these.
_IPCM_NON_FACULTY_TEAMS = {
    "administration",
    "logistique",
    "informatique",
    "bibliothèque",
    "bibliotheque",
    "analyses",
    "rmn",
    "drx",
    "atelier",
    "cartographie",
    "communication",
}


def _scrape_ipcm() -> list[Faculty]:
    """IPCM has a single long table: [Nom, Courriel, Equipe, Statut]. The
    page doesn't distinguish PR/MCF/DR/CR — everyone ranked has Statut
    'Permanent'. We keep Statut=Permanent rows and drop the Equipe==
    'Administration' ones.

    This is looser than the other two scrapers — some permanent engineers
    (ITA) may slip through. Acceptable for a v1 template; a per-person
    enrichment pass can tighten this later.
    """
    html = get(IPCM_URL)
    soup = BeautifulSoup(html, "html.parser")
    rows = soup.select("table tr")
    out: list[Faculty] = []
    seen_ids: set[str] = set()
    for r in rows[1:]:
        cells = r.find_all("td")
        if len(cells) < 4:
            continue
        name_raw = clean_text(cells[0].get_text(" ", strip=True))
        team = clean_text(cells[2].get_text(" ", strip=True))
        status = clean_text(cells[3].get_text(" ", strip=True))
        if not name_raw:
            continue
        if status.lower() != "permanent":
            continue
        if team.lower() in _IPCM_NON_FACULTY_TEAMS:
            continue
        name = _imj_reformat_name(name_raw)  # same "LASTNAME First" convention
        rec_id = slugify("sorbonne", "stem", name)
        if rec_id in seen_ids:
            continue
        seen_ids.add(rec_id)
        out.append({
            "id": rec_id,
            "name": name,
            "institution": "Sorbonne",
            "department": f"{IPCM_DEPT} — {team}" if team else IPCM_DEPT,
            "title": "Permanent Researcher",
            "roles": [team] if team else [],
            "research_areas": _keywords_from(team),
            "summary": f"Research team: {team}." if team else "",
            "profile_url": IPCM_URL,
            "lab_url": "",
            "scholar_url": "",
            "orcid": "",
            "photo_url": "",
        })
    print(f"[sorbonne_stem] IPCM: {len(out)} permanent researchers")
    return out


# --------------------------------------------------------------------------- #
# LKB — Laboratoire Kastler Brossel (Physics)
# --------------------------------------------------------------------------- #

LKB_URL = "https://www.lkb.fr/laboratoire/membres/chercheurs-et-enseignants-chercheurs/"
LKB_DEPT = "Laboratoire Kastler Brossel (LKB)"


def _scrape_lkb() -> list[Faculty]:
    """LKB lists its researchers and teaching-researchers as `<article>` cards
    on a single page. Each card carries the name (uppercase family surname),
    a photo, and a "Chercheur" / "Enseignant-Chercheur" category. Both count
    as ranked faculty in the French system; the finer PR/MCF/DR/CR split
    isn't surfaced here — we record the broader category as title."""
    html = get(LKB_URL)
    soup = BeautifulSoup(html, "html.parser")
    articles = soup.select("article.rebond_membres_article")
    out: list[Faculty] = []
    for art in articles:
        a = art.find("a", href=True)
        if not a:
            continue
        profile_url = a["href"].strip()
        h3 = art.find("h3", class_="rebond_membres_article_title")
        name_raw = clean_text(h3.get_text(" ", strip=True)) if h3 else ""
        subt = art.find("p", class_="header_subtitle")
        category = clean_text(subt.get_text(" ", strip=True)) if subt else ""
        if not name_raw:
            continue
        # Category guard — an excluded label here means someone's been added
        # to the /chercheurs-et-enseignants-chercheurs/ page in error.
        if category and not re.search(r"chercheur", category, re.I):
            continue
        name = _imj_reformat_name(name_raw)  # same "FIRST LASTNAME" form
        photo = ""
        img = art.find("img")
        if img and img.get("src"):
            photo = img["src"].strip()
        title = (
            "Teaching Researcher (Enseignant-Chercheur)"
            if "enseignant" in category.lower()
            else "CNRS/INSERM Researcher"
        )
        out.append({
            "id": slugify("sorbonne", "stem", name),
            "name": name,
            "institution": "Sorbonne",
            "department": LKB_DEPT,
            "title": title,
            "roles": [category] if category else [],
            "research_areas": [],  # team info isn't on the list page
            "summary": "Laboratoire Kastler Brossel — quantum physics.",
            "profile_url": profile_url,
            "lab_url": "",
            "scholar_url": "",
            "orcid": "",
            "photo_url": photo,
        })
    print(f"[sorbonne_stem] LKB: {len(out)} ranked faculty")
    return out


# --------------------------------------------------------------------------- #
# LCT — Laboratoire de Chimie Théorique (Chemistry)
# --------------------------------------------------------------------------- #

LCT_URL = "https://www.lct.jussieu.fr/?page_id=128"
LCT_DEPT = "Laboratoire de Chimie Théorique (LCT)"


def _scrape_lct() -> list[Faculty]:
    """LCT has a simple 4-column table: [identite, telephone, localisation,
    fonction]. The fonction column names the exact rank, so we can filter
    with the standard _RANKED_RE and exclude Ingénieur de recherche / ATER /
    other non-faculty roles."""
    html = get(LCT_URL)
    soup = BeautifulSoup(html, "html.parser")
    rows = soup.select("table tr")
    out: list[Faculty] = []
    for r in rows[1:]:
        cells = r.find_all(["th", "td"])
        if len(cells) < 4:
            continue
        name_raw = clean_text(cells[0].get_text(" ", strip=True))
        office = clean_text(cells[2].get_text(" ", strip=True))
        fonction = clean_text(cells[3].get_text(" ", strip=True))
        if not name_raw:
            continue
        # "Chair Professeur Junior" is W1-equivalent tenure-track — keep it;
        # the regex doesn't match it, so carve out explicitly.
        if not (_RANKED_RE.search(fonction) or "chair professeur" in fonction.lower()):
            continue
        name = _imj_reformat_name(name_raw)
        english = _rank_english(fonction)
        if "chair professeur" in fonction.lower():
            english = "Junior Chair Professor"
        out.append({
            "id": slugify("sorbonne", "stem", name),
            "name": name,
            "institution": "Sorbonne",
            "department": LCT_DEPT,
            "title": english,
            "roles": [fonction] if fonction else [],
            "research_areas": [],
            "summary": f"Office: {office}." if office else "",
            "profile_url": LCT_URL,
            "lab_url": "",
            "scholar_url": "",
            "orcid": "",
            "photo_url": "",
        })
    print(f"[sorbonne_stem] LCT: {len(out)} ranked faculty")
    return out


# --------------------------------------------------------------------------- #
# Shared helpers + entry point
# --------------------------------------------------------------------------- #

def _keywords_from(label: str) -> list[str]:
    """Split an institute-team label into short domain keywords. The French
    lab names already read like keyword lists once split on conjunctions."""
    if not label:
        return []
    parts = re.split(r"[,;/&]|\bet\b|\bde\b|\bdes\b|\bdu\b|\bla\b|\bles\b|\(|\)", label, flags=re.I)
    out: list[str] = []
    for p in parts:
        p = clean_text(p)
        if 2 < len(p) < 60 and not re.fullmatch(r"[A-Z]{2,6}", p):
            out.append(p)
    return out[:4]


def scrape() -> list[Faculty]:
    all_out: list[Faculty] = []
    seen_ids: set[str] = set()
    for fn in (_scrape_imj, _scrape_ljll, _scrape_ipcm, _scrape_lkb, _scrape_lct):
        try:
            recs = fn()
        except Exception as e:
            print(f"  [sorbonne_stem] {fn.__name__} failed: {e}")
            continue
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
    (out_dir / "sorbonne_stem.json").write_text(
        json.dumps(records, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"[sorbonne_stem] wrote {len(records)} records total")


if __name__ == "__main__":
    main()
