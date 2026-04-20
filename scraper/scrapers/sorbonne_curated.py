"""Sorbonne — curated additions for labs whose public directories aren't
scrape-able.

Several Sorbonne STEM research units either block automated access (INSP
returns HTTP 403 to non-interactive clients) or publish no structured
public faculty list (LRS shows personnel info only inside static prose on
theme pages). For now we fill these gaps with a hand-curated list of
senior faculty whose affiliations were verified against their published
paper affiliation strings (PubMed / HAL author records).

Policy: only ranked faculty (PR, MCF, DR, CR or equivalent) who can
main-supervise PhD students. Each entry includes at least
   name, institute, rank, profile_url (canonical authoritative page),
and a short summary sourced from the cited affiliation/bio.

Run with:
    python -m scrapers.sorbonne_curated
"""

from __future__ import annotations

import json
from pathlib import Path

from schema import Faculty, slugify


# (name, department, title, profile_url, summary, research_areas)
_CURATED: list[tuple[str, str, str, str, str, list[str]]] = [
    (
        "Souhir Boujday",
        "Laboratoire de Réactivité de Surface (LRS) — UMR 7197",
        "Full Professor — Chair, School of Chemistry",
        "https://lrs.sorbonne-universite.fr",
        "Chair of the School of Chemistry at Sorbonne Université. Research at "
        "LRS focuses on biointerfaces: functionalisation of nanoparticles and "
        "surfaces for biosensing and biomedical applications, surface "
        "spectroscopy, and protein–surface interactions.",
        ["Biointerfaces", "Biosensors", "Surface chemistry", "Nanoparticles", "Spectroscopy"],
    ),
    (
        "Mathieu Mivelle",
        "Institut des NanoSciences de Paris (INSP)",
        "CNRS Researcher",
        "https://www.insp.upmc.fr",
        "CNRS researcher at the Institut des NanoSciences de Paris (Sorbonne "
        "Université / CNRS). Research on nano-optics, plasmonic nanoantennas, "
        "magnetic light-matter interactions, and chiroptical effects at the "
        "nanoscale.",
        ["Nano-optics", "Plasmonics", "Nanoantennas", "Chirality", "Light-matter interaction"],
    ),
]


def scrape() -> list[Faculty]:
    out: list[Faculty] = []
    for name, dept, title, profile_url, summary, areas in _CURATED:
        out.append({
            "id": slugify("sorbonne", "stem", name),
            "name": name,
            "institution": "Sorbonne",
            "department": dept,
            "title": title,
            "roles": [],
            "research_areas": areas,
            "summary": summary,
            "profile_url": profile_url,
            "lab_url": "",
            "scholar_url": "",
            "orcid": "",
            "photo_url": "",
        })
    print(f"[sorbonne_curated] emitted {len(out)} curated records")
    return out


def main() -> None:
    out_dir = Path(__file__).resolve().parents[1] / "out"
    out_dir.mkdir(exist_ok=True)
    records = scrape()
    (out_dir / "sorbonne_curated.json").write_text(
        json.dumps(records, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"[sorbonne_curated] wrote {len(records)} records")


if __name__ == "__main__":
    main()
