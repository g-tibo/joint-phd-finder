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
    ("tum_bio.json", "TUM", "Supervision"),
    ("tum_nat_cit.json", "TUM", "Supervision"),
    ("turin_bio.json", "Turin", "Supervision"),
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
