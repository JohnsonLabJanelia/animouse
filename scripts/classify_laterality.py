"""Classify meshes and bones as midline vs. lateral, and deduplicate pairs.

For each row in the input inventory, add:
  anatomical_class     : 'midline' | 'lateral'
  canonical_name       : name stripped of _right/_left (for lateral) or raw name
  canonical_side       : 'midline' | 'right' | 'left'
  mirror_present       : 'true' if the mirror partner exists in the inventory
  is_representative    : 'true' if this row is the canonical dedup entry

Outputs three files next to the input CSV:
  <name>_anatomical.csv       — original rows with the added columns
  <name>_canonical.csv        — one row per anatomical structure (deduped)
  <name>_laterality_stats.txt — human-readable summary

Classification rules (in order):
  1. Name has explicit _right / _left / _r / _l suffix → lateral, side from suffix.
  2. Otherwise, |cx − midline_x| > POS_THRESHOLD_M → lateral, side from sign.
  3. Otherwise → midline.

Usage:
    python3 scripts/classify_laterality.py INVENTORY_CSV [--pos-col cx]
"""
from __future__ import annotations

import argparse
import csv
import re
import statistics as s
from collections import defaultdict
from pathlib import Path


# Position column in the mesh inventory is 'cx'. For the armature inventory
# there's no centroid — we'll rely on name-based classification there.
# Tissue-specific centroid thresholds (distance off the X=0 midline plane
# beyond which a mesh is classified lateral).
#
# For MUSCLES and TENDONS we use a strict 0.5 mm threshold: anatomically
# almost every skeletal muscle and tendon is paired, with true midline muscles
# limited to things like the diaphragm / intrinsic tongue / sphincters (none
# are segmented in this blend). Prior 3 mm threshold was too generous and
# wrongly flagged ~38 lateral muscles at cx ≈ ±2 mm as "midline".
#
# For BONES, CARTILAGE, and ORGANS we keep the 3 mm threshold: the spine
# vertebrae, skull, and abdominal organs have real midline members that sit
# exactly at cx ≈ 0, so a generous threshold does no harm there.
POS_THRESHOLD_M_DEFAULT = 0.003
# For muscles and tendons we treat any non-zero centroid offset as lateral:
# no true midline muscles or tendons are segmented in this atlas (diaphragm,
# tongue intrinsics, sphincters — all absent), and the limb/trunk muscles and
# tendons that creep near the midline are ALL lateral anatomically.
POS_THRESHOLD_M_BY_TISSUE = {
    "muscle": 0.0,
    "tendon/ligament": 0.0,
}

# In this blend: world -X is subject's anatomical right (verified empirically).
# So a mesh with cx < 0 (and |cx| > threshold) is on the subject's right.
RIGHT_IS_NEGATIVE_X = True


# Capture a trailing side marker. Allow: "_right", " right", ".right",
# "_R", "_L", etc., followed by optional ".001"-style Blender duplicate suffix.
SIDE_RE = re.compile(
    r"^(.+?)[\s_.\-]+(right|left|r|l)(\.\d+)?\s*$",
    re.IGNORECASE,
)

# A few tokens look like side markers but aren't:
SIDE_FALSE_POSITIVES = {"lateralis", "lateral", "rectus", "l1", "l2", "l3", "l4", "l5", "l6"}


def side_from_name(name: str):
    """Return (side, canonical_base) or (None, None)."""
    m = SIDE_RE.match(name.strip())
    if not m:
        return None, None
    base = m.group(1)
    side_tok = m.group(2).lower()
    # Guard against accidental matches where the "base" is a false positive
    # composite like "Rectus_lateral" ending in "_l".
    last_base_tok = base.split("_")[-1].split(".")[-1].lower()
    if last_base_tok in SIDE_FALSE_POSITIVES and side_tok in ("l", "r"):
        return None, None
    canonical_side = "right" if side_tok in ("right", "r") else "left"
    return canonical_side, base


def side_from_position(cx: float, midline_x: float, threshold: float):
    """Return 'right' / 'left' / None based on centroid offset from midline."""
    offset = cx - midline_x
    if abs(offset) <= threshold:
        return None
    if RIGHT_IS_NEGATIVE_X:
        return "right" if offset < 0 else "left"
    return "left" if offset < 0 else "right"


COLLECTION_SIDE_RE = re.compile(r"\b(right|left)\b", re.IGNORECASE)


def side_from_collection(collection_path: str):
    """The blend's collection hierarchy encodes laterality explicitly for many
    structures (e.g., 'ARM right', 'SYMMETRIZED muscles spine right'). When
    such a token appears in the path, it's authoritative."""
    if not collection_path:
        return None
    # Walk path segments last-to-first (deepest collection has strongest signal).
    for seg in reversed(collection_path.split(">")):
        m = COLLECTION_SIDE_RE.search(seg)
        if m:
            return m.group(1).lower()
    return None


def classify_row(row, midline_x, has_centroid: bool):
    name = row["name"]
    collection = row.get("collection", "")
    tissue = row.get("tissue", "")
    side_by_name, canon_base = side_from_name(name)
    side_by_coll = side_from_collection(collection)
    side_by_pos = None
    if has_centroid:
        try:
            cx = float(row["cx"])
            threshold = POS_THRESHOLD_M_BY_TISSUE.get(tissue, POS_THRESHOLD_M_DEFAULT)
            side_by_pos = side_from_position(cx, midline_x, threshold)
        except (KeyError, ValueError):
            pass

    # Priority: explicit name suffix > collection path > centroid.
    if side_by_name:
        side = side_by_name
        canon = canon_base or name
        anat = "lateral"
    elif side_by_coll:
        side = side_by_coll
        canon = name
        anat = "lateral"
    elif side_by_pos:
        side = side_by_pos
        canon = name
        anat = "lateral"
    else:
        side = "midline"
        canon = name
        anat = "midline"

    row["anatomical_class"] = anat
    row["canonical_name"] = canon.strip()
    row["canonical_side"] = side
    return row


def normalize_canonical_key(canon: str) -> str:
    """Used for grouping. Case-insensitive only — do NOT strip trailing
    ".005"-style suffixes, because in this blend those are segmentation IDs
    on the "Retopo_*" Muscles-to-ID meshes (e.g. "Retopo_10.005" is a
    distinct mesh, not a Blender duplicate of "Retopo_10")."""
    return canon.strip().lower()


def dedupe_and_summarize(rows):
    """Group lateral rows by canonical name. Keep the right-side representative.

    Per paper convention (2026-04-19): the catalogue includes midline and
    right-side structures only. Groups that exist only on the left are EXCLUDED
    from the catalogue — the small number of such meshes in this blend are
    almost all cases where a right-side partner exists but uses a different
    numeric ID in Paintera's naming scheme; they can be rematched later if
    needed.

    Returns (rows with is_representative / mirror_present filled in,
             canonical_catalog, stats dict).
    """
    groups = defaultdict(list)
    for r in rows:
        if r["anatomical_class"] == "lateral":
            key = normalize_canonical_key(r["canonical_name"])
            groups[key].append(r)

    n_lateral_paired = 0
    n_lateral_right_only = 0
    n_lateral_left_only_excluded = 0
    canonical_rows = []

    # Midline rows — all representatives.
    n_midline = 0
    for r in rows:
        r["mirror_present"] = ""
        r["is_representative"] = ""
        if r["anatomical_class"] == "midline":
            r["is_representative"] = "true"
            r["mirror_present"] = "n/a"
            canonical_rows.append(r)
            n_midline += 1

    # Lateral groups: keep only groups that have a right-side mesh.
    for key, members in groups.items():
        sides = {m["canonical_side"] for m in members}
        has_right = "right" in sides
        has_left = "left" in sides

        if not has_right:
            # Left-only — exclude from catalogue.
            for m in members:
                m["mirror_present"] = "false"
                m["is_representative"] = "false"
            n_lateral_left_only_excluded += 1
            continue

        rep = next(m for m in members if m["canonical_side"] == "right")
        for m in members:
            m["mirror_present"] = "true" if has_left else "false"
            m["is_representative"] = "true" if m is rep else "false"
        canonical_rows.append(rep)

        if has_left:
            n_lateral_paired += 1
        else:
            n_lateral_right_only += 1

    n_lateral = n_lateral_paired + n_lateral_right_only
    stats = {
        "n_midline": n_midline,
        "n_lateral": n_lateral,
        "n_lateral_bilateral": n_lateral_paired,
        "n_lateral_right_only": n_lateral_right_only,
        "n_left_only_excluded": n_lateral_left_only_excluded,
        "n_anatomical_structures": n_midline + n_lateral,
        "implied_complete_total": n_midline + 2 * n_lateral,
        "catalogue_rows": n_midline + n_lateral,
    }
    return rows, canonical_rows, stats


def write_stats(stats, tissue_breakdown, out_path: Path, title: str):
    lines = [f"# Laterality classification — {title}", ""]
    lines.append("Catalogue convention: midline + right-side structures only.")
    lines.append(f"Left-only groups excluded from catalogue:  {stats['n_left_only_excluded']:>5d}")
    lines.append("")
    lines.append(f"Midline structures:                 {stats['n_midline']:>5d}")
    lines.append(f"Lateral structures (right-side rep): {stats['n_lateral']:>5d}")
    lines.append(f"  of which bilateral (L+R modeled):  {stats['n_lateral_bilateral']:>5d}")
    lines.append(f"  of which right-side only:          {stats['n_lateral_right_only']:>5d}")
    lines.append("")
    lines.append(f"Distinct anatomical structures (catalogue size): {stats['n_anatomical_structures']:>5d}")
    lines.append(f"Implied complete total (midline + 2 × lateral):  {stats['implied_complete_total']:>5d}")
    if tissue_breakdown:
        lines.append("")
        lines.append("Breakdown by tissue (catalogue representatives):")
        lines.append(f"  {'tissue':20s} {'midline':>8s} {'lateral':>8s} {'total_anat':>11s}")
        for tissue, counts in sorted(tissue_breakdown.items()):
            lines.append(
                f"  {tissue:20s} {counts['midline']:>8d} {counts['lateral']:>8d} "
                f"{counts['midline'] + counts['lateral']:>11d}"
            )
    out_path.write_text("\n".join(lines) + "\n")


def tissue_counts_from_canonical(canonical_rows):
    table = defaultdict(lambda: {"midline": 0, "lateral": 0})
    for r in canonical_rows:
        t = r.get("tissue", "unknown")
        table[t][r["anatomical_class"]] += 1
    return dict(table)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("inventory", type=Path)
    ap.add_argument("--title", default=None,
                    help="Label for the stats report (default: inventory filename)")
    ap.add_argument("--name-col", default="name",
                    help="Column holding the mesh/bone name (default: 'name')")
    args = ap.parse_args()

    rows = list(csv.DictReader(args.inventory.open()))
    if not rows:
        print("empty input")
        return

    # Normalize: our helpers expect a 'name' column. Alias if needed.
    if args.name_col != "name":
        for r in rows:
            r["name"] = r[args.name_col]

    has_centroid = "cx" in rows[0]
    # The model is authored with bilateral symmetry about X=0, so use 0 as the
    # midline reference. An earlier attempt to estimate it from the median of
    # "midline-by-name" meshes was polluted by off-midline Muscles-to-ID meshes
    # whose names lack a _right/_left suffix — it dragged the reference 3.5mm
    # off-center and flipped every spine vertebra into "lateral-left".
    midline_x = 0.0

    classified = [classify_row(r, midline_x, has_centroid) for r in rows]
    _, canonical_rows, stats = dedupe_and_summarize(classified)

    base = args.inventory.with_suffix("")
    # Full annotated
    full_out = Path(str(base) + "_anatomical.csv")
    with full_out.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(classified[0].keys()))
        w.writeheader()
        w.writerows(classified)
    # Canonical (one-per-structure)
    canon_out = Path(str(base) + "_canonical.csv")
    with canon_out.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(canonical_rows[0].keys()))
        w.writeheader()
        w.writerows(canonical_rows)
    # Stats
    stats_out = Path(str(base) + "_laterality_stats.txt")
    tissue_bd = tissue_counts_from_canonical(canonical_rows) if has_centroid else {}
    write_stats(stats, tissue_bd, stats_out, args.title or args.inventory.name)

    print(f"  → {full_out}")
    print(f"  → {canon_out}")
    print(f"  → {stats_out}")
    print()
    print(stats_out.read_text())


if __name__ == "__main__":
    main()
