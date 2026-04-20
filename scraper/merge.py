"""Combine per-source JSON into web/public/faculty.json for the Joint PhD Finder.

Tags every record with `partner_university` and `partnership_type` before
writing. Sources are either:

- The pre-filtered NTU snapshot carried over from SG Collab Finder
  (scraper/out/ntu_all.json).
- Per-partner biology scrapers (scraper/out/sorbonne_bio.json, etc.).

Dedup is keyed on normalized name AND partner_university — two different
"Giuseppe Rossi"s at different partner unis are kept; two records for the same
person at the same partner uni collapse to the richer one.
"""

from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT_DIR = ROOT / "out"
TARGET = ROOT.parent / "web" / "public" / "faculty.json"
OVERRIDES = ROOT / "overrides.json"

# Each entry: (filename, partner_university short-code, partnership_type)
# partnership_type is None for NTU — NTU is the hosting side, not a partner.
SOURCES = [
    ("ntu_all.json", "NTU", None),
    ("sorbonne_bio.json", "Sorbonne", "Degree"),
    ("sorbonne_stem.json", "Sorbonne", "Degree"),
    ("sorbonne_curated.json", "Sorbonne", "Degree"),
    ("tum_bio.json", "TUM", "Supervision"),
    ("tum_nat_cit.json", "TUM", "Supervision"),
    ("turin_depts.json", "Turin", "Supervision"),
]


def _norm_name(name: str) -> str:
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    s = re.sub(r"\([^)]*\)", " ", s)
    s = re.sub(r"[^a-zA-Z\s]", " ", s).lower()
    tokens = [t for t in s.split() if t]
    return " ".join(sorted(tokens))


_SECONDARY_RE = re.compile(r"\b(Joint|Adjunct|Visiting|Affiliated|Honorary)\b", re.I)


def _is_primary(rec: dict) -> bool:
    return not _SECONDARY_RE.search(rec.get("title", "") or "")


def _priority(rec: dict) -> tuple:
    return (
        1 if _is_primary(rec) else 0,
        len(rec.get("summary", "") or ""),
        len(rec.get("research_areas", []) or []),
        1 if rec.get("photo_url") else 0,
    )


# Ranked-faculty allowlist: any record whose title contains one of these
# phrases (case-insensitive) is accepted. The check runs against title +
# roles together so NTU records whose `title` was misparsed as a role/
# institution (e.g. "Director", "Imperial College London") can be rescued
# when their `roles` field clearly names a professorial rank.
_RANKED_TITLE_RE = re.compile(
    r"\b(?:full\s+professor|associate\s+professor|assistant\s+professor|"
    r"nanyang\s+assistant\s+professor|president['’]?s\s+chair|"
    r"(?:distinguished|chair|lee\s+kuan\s+yew)\s+professor|"
    r"professor|prof\.\s*dr|"
    r"researcher|tenure[-\s]?track|"
    r"senior\s+researcher|staff\s+scientist|team\s+leader)\b",
    re.I,
)

# Titles that indicate a non-ranked / support / trainee position — drop
# the record if present, even if a ranked keyword also appears.
# "Flagship Pioneering" is the Cambridge MA biotech-VC firm; NTU profiles
# sometimes list it as a secondary title for affiliated faculty who aren't
# primary NTU supervisors.
_EXCLUDED_TITLE_RE = re.compile(
    r"\b(?:lecturer|senior\s+lecturer|instructor|"
    r"research\s+fellow|postdoctoral|post[-\s]?doc|"
    r"research\s+associate|research\s+engineer|research\s+assistant|"
    r"teaching\s+assistant|teaching\s+fellow|"
    r"adjunct|visiting|honorary|emeritus|affiliated|"
    r"flagship\s+pioneering|"
    r"graduate\s+student|phd\s+student|doctoral\s+student|intern)\b",
    re.I,
)


def _haystack_title_roles(rec: dict) -> str:
    title = rec.get("title", "") or ""
    roles = " ".join(rec.get("roles", []) or [])
    return f"{title} {roles}"


def _recover_title(rec: dict) -> str | None:
    """When a record's title is clearly garbage (an institution name, a bare
    admin role like 'Director', or empty) but its roles list contains a
    ranked professorial phrase, promote that phrase to the title so the UI
    and downstream filters show the right rank. Returns the new title or None
    if no recovery is possible."""
    roles = rec.get("roles", []) or []
    for r in roles:
        m = re.search(
            r"\b(Full Professor|Associate Professor|Assistant Professor|"
            r"Nanyang Assistant Professor|Distinguished Professor|Chair Professor|"
            r"Professor)\b",
            r or "",
            re.I,
        )
        if m:
            return m.group(1)
    return None


def _filter_ranked_only(records: list[dict]) -> list[dict]:
    """Enforce the 'ranked-faculty only' rule and do a couple of label
    normalisations the scrapers can't cleanly emit at source.

    Rules:
    - If the title contains an excluded phrase (Lecturer, Research Fellow,
      Adjunct, Visiting, Emeritus, ...) → drop.
    - If the title matches a ranked phrase → keep as-is.
    - Else try to recover a ranked title from `roles`; if one exists → fix
      the title and keep.
    - Otherwise → drop.

    Sorbonne-specific: relabel "Staff Scientist — <team>" to "Senior
    Researcher — <team>" so the UI label can't be misread as a postdoc
    title. IBPS "Staff Scientists" are CNRS/INSERM permanent ranked staff
    (Chargé / Directeur de recherche) equivalent to Assistant/Associate
    Professor in the English-speaking system.
    """
    kept: list[dict] = []
    dropped_count: dict[str, int] = {}

    for rec in records:
        pu = rec.get("partner_university", "") or ""
        haystack = _haystack_title_roles(rec)
        title = rec.get("title", "") or ""

        if _EXCLUDED_TITLE_RE.search(haystack):
            # Don't drop if a ranked phrase ALSO appears — this catches e.g.
            # "Associate Professor (Adjunct)" where the adjunct is a
            # secondary flag, not the primary rank. Check title only (not
            # roles) for that carve-out: primary rank lives in title.
            if _RANKED_TITLE_RE.search(title) and not _EXCLUDED_TITLE_RE.search(title):
                pass  # title is clean, roles just note a secondary affiliation
            else:
                dropped_count[pu] = dropped_count.get(pu, 0) + 1
                continue

        if not _RANKED_TITLE_RE.search(title):
            recovered = _recover_title(rec)
            if recovered:
                rec["title"] = recovered
            else:
                dropped_count[pu] = dropped_count.get(pu, 0) + 1
                continue

        # Sorbonne relabel: keep the team suffix, replace the leading role.
        if pu == "Sorbonne" and rec.get("title", "").startswith("Staff Scientist"):
            rec["title"] = rec["title"].replace("Staff Scientist", "Senior Researcher", 1)

        kept.append(rec)

    if dropped_count:
        print(
            "  ranked-only filter dropped: "
            + ", ".join(f"{pu}={n}" for pu, n in sorted(dropped_count.items()))
        )
    return kept


def _dedup_within_partner(records: list[dict]) -> list[dict]:
    """Dedup by (partner_university, normalized name). Preserves cross-partner duplicates."""
    groups: dict[tuple[str, str], list[dict]] = {}
    for r in records:
        key = (r.get("partner_university", ""), _norm_name(r.get("name", "")))
        groups.setdefault(key, []).append(r)
    kept = []
    for group in groups.values():
        if len(group) == 1:
            kept.append(group[0])
            continue
        group.sort(key=_priority, reverse=True)
        kept.append(group[0])
    return kept


def main() -> None:
    all_records: list[dict] = []
    for src, partner, ptype in SOURCES:
        p = OUT_DIR / src
        if not p.exists():
            print(f"  missing {src} — skipping (run its scraper first)")
            continue
        records = json.loads(p.read_text(encoding="utf-8"))
        for r in records:
            # Force the tagging even if the scraper already set it, so
            # merge.py is the single source of truth for partnership metadata.
            r["partner_university"] = partner
            r["partnership_type"] = ptype
        print(f"  {src}: {len(records)} records -> {partner} ({ptype or '—'})")
        all_records.extend(records)

    if OVERRIDES.exists():
        patches = json.loads(OVERRIDES.read_text(encoding="utf-8"))
        applied = 0
        for rec in all_records:
            patch = patches.get(rec.get("id"))
            if patch:
                rec.update(patch)
                applied += 1
        if applied:
            print(f"  applied {applied}/{len(patches)} overrides from overrides.json")

    # Rank-gate: drop anyone whose title indicates a non-ranked or
    # non-research-track position, since only ranked faculty can main-supervise
    # PhDs. Also runs a few cross-partner label normalizations.
    all_records = _filter_ranked_only(all_records)

    all_records = _dedup_within_partner(all_records)

    # Stable sort: NTU first, then partners alphabetically; within each, by name.
    partner_order = {"NTU": 0, "Sorbonne": 1, "TUM": 2, "Turin": 3}
    all_records.sort(
        key=lambda r: (
            partner_order.get(r.get("partner_university", ""), 99),
            r.get("name", ""),
        )
    )

    # Strip faculty emails before publishing; profile_url stays.
    for r in all_records:
        r.pop("email", None)

    TARGET.parent.mkdir(parents=True, exist_ok=True)
    TARGET.write_text(
        json.dumps(all_records, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"wrote {len(all_records)} -> {TARGET}")


if __name__ == "__main__":
    main()
