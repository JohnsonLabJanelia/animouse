"""Emit publication-grade supplementary tables from the canonical catalogues.

Reads:
  mesh_inventory_flagged_canonical.csv   (473 anatomical structures)
  armature_inventory_canonical.csv       (166 rig structures, if present)

Writes to OUT/:
  s_table_mesh_catalogue.csv       — clean CSV, publication column order, units in headers
  s_table_mesh_catalogue.md        — markdown preview (first 40 rows + footer note)
  s_table_mesh_catalogue_summary.md — summary section for the paper: counts by tissue × region
  s_table_bone_catalogue.csv       — same for armature
  s_table_bone_catalogue.md
  regional_breakdown.csv           — counts & volumes by anatomical region (head/thorax/...)
  regional_breakdown.md

Usage:
    python3 scripts/build_catalogue_tables.py \\
        --mesh     ~/anibodymouse/claude_mouse_unknown_muscles/inspection/mesh_inventory_flagged_canonical.csv \\
        --armature ~/anibodymouse/claude_mouse_unknown_muscles/inspection/armature_inventory_canonical.csv \\
        --out      ~/anibodymouse/claude_mouse_unknown_muscles/figures/tables
"""
from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from pathlib import Path


# Map collection path prefix → region label for the regional breakdown.
# Matched in order; first prefix match wins.
REGION_RULES = [
    ("SKELETON > SKULL", "head (skull)"),
    ("SKELETON > spine", "spine"),
    ("SKELETON > ribcage", "thorax (ribcage)"),
    ("SKELETON > ARM", "forelimb"),
    ("SKELETON > shoulder", "shoulder"),
    ("SKELETON > leg", "hindlimb"),
    ("MUSCLES and TENDONS > muscles skull", "head (muscles)"),
    ("MUSCLES and TENDONS > muscles head", "head (muscles)"),
    ("MUSCLES and TENDONS > muscles spine", "spine (muscles)"),
    ("MUSCLES and TENDONS > muscles ribcage", "thorax (muscles)"),
    ("MUSCLES and TENDONS > muscles scapula+clavicle", "shoulder (muscles)"),
    ("MUSCLES and TENDONS > muscles humerus", "forelimb (muscles)"),
    ("MUSCLES and TENDONS > muscles radius+ulna", "forelimb (muscles)"),
    ("MUSCLES and TENDONS > muscles arm", "forelimb (muscles)"),
    ("MUSCLES and TENDONS > ARM TENDONS", "forelimb (tendons)"),
    ("MUSCLES and TENDONS > TENDONS SHOULDER", "shoulder (tendons)"),
    ("MUSCLES and TENDONS > muscles femur", "hindlimb (muscles)"),
    ("MUSCLES and TENDONS > muscles tibia", "hindlimb (muscles)"),
    ("MUSCLES and TENDONS > muscles foot", "hindlimb (muscles+tendons)"),
    ("ORGANS", "organs"),
    ("axis of rotation", "rigging refs"),
]


def region_for(collection: str) -> str:
    c = collection or ""
    for prefix, label in REGION_RULES:
        if prefix.lower() in c.lower():
            return label
    return "other"


def read_canonical(path: Path):
    rows = list(csv.DictReader(path.open()))
    return rows


def _num(row, key, default=0.0):
    try:
        return float(row.get(key, default) or 0.0)
    except ValueError:
        return default


def _int(row, key, default=0):
    try:
        return int(row.get(key, default) or 0)
    except ValueError:
        return default


# ---------------------------------------------------------------------------
# Mesh catalogue
# ---------------------------------------------------------------------------

MESH_COLUMNS = [
    ("display_name",      "Name"),
    ("tissue",             "Tissue"),
    ("anatomical_class",  "Class"),
    ("mirror_state",      "Symmetry"),
    ("region",            "Region"),
    ("laterality_note",   "Side in model"),
    ("volume_mm3",        "Volume (mm³)"),
    ("surface_area_mm2",  "SA (mm²)"),
    ("max_dim_mm",        "Max dim (mm)"),
    ("vertices",          "Vertices"),
    ("faces",             "Faces"),
]


def _mirror_state(row):
    if row["anatomical_class"] == "midline":
        return "midline"
    mp = row.get("mirror_present", "")
    return "bilateral" if mp == "true" else "right-only"


def _laterality_note(row):
    if row["anatomical_class"] == "midline":
        return "—"
    # Since we keep right-side representatives, canonical_side is always "right"
    # for lateral rows. Note it explicitly for clarity in the published table.
    return row.get("canonical_side", "right")


def build_mesh_rows(raw_rows):
    out = []
    for r in raw_rows:
        dims = [_num(r, k) for k in ("dim_x_mm", "dim_y_mm", "dim_z_mm")]
        out.append({
            "display_name":     r.get("display_name") or r.get("name"),
            "tissue":           r.get("tissue", ""),
            "anatomical_class": r.get("anatomical_class", ""),
            "mirror_state":     _mirror_state(r),
            "region":           region_for(r.get("collection", "")),
            "laterality_note":  _laterality_note(r),
            "volume_mm3":       _num(r, "volume_mm3"),
            "surface_area_mm2": _num(r, "surface_area_mm2"),
            "max_dim_mm":       max(dims) if dims else 0.0,
            "vertices":         _int(r, "vertices"),
            "faces":            _int(r, "faces"),
            "_sort_key":        (r.get("tissue", "zzz"), region_for(r.get("collection", "")),
                                 r.get("display_name") or r.get("name")),
        })
    out.sort(key=lambda r: r["_sort_key"])
    for r in out:
        del r["_sort_key"]
    return out


def write_csv(rows, columns, out_path: Path):
    with out_path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow([label for _, label in columns])
        for r in rows:
            vals = []
            for key, _ in columns:
                v = r.get(key, "")
                if isinstance(v, float):
                    v = f"{v:.2f}"
                vals.append(v)
            w.writerow(vals)


def write_markdown_preview(rows, columns, out_path: Path, title: str, total_rows: int, preview_n: int = 40):
    lines = [f"# {title}", "",
             f"**Catalogue size:** {total_rows} anatomical structures. "
             f"Showing the first {min(preview_n, total_rows)} rows sorted by tissue → region → name; "
             f"full listing in the companion CSV.", ""]
    header = "| " + " | ".join(label for _, label in columns) + " |"
    sep = "|" + "|".join(["---"] * len(columns)) + "|"
    lines += [header, sep]
    for r in rows[:preview_n]:
        cells = []
        for key, _ in columns:
            v = r.get(key, "")
            if isinstance(v, float):
                v = f"{v:,.2f}"
            cells.append(str(v))
        lines.append("| " + " | ".join(cells) + " |")
    lines.append("")
    lines.append("*Column glossary: Tissue — our classification from material; "
                 "Class — midline vs. lateral; Symmetry — bilateral if both L+R modeled, "
                 "right-only otherwise; Side in model — which side the representative mesh is on.*")
    out_path.write_text("\n".join(lines) + "\n")


# ---------------------------------------------------------------------------
# Summary by tissue × region
# ---------------------------------------------------------------------------

def build_tissue_region_summary(mesh_rows):
    """Counts and volumes grouped by tissue × region."""
    by_tr = defaultdict(lambda: {"n_midline": 0, "n_lateral_bilateral": 0,
                                   "n_lateral_right_only": 0, "total_vol_mm3": 0.0})
    for r in mesh_rows:
        bucket = by_tr[(r["tissue"], r["region"])]
        if r["anatomical_class"] == "midline":
            bucket["n_midline"] += 1
        elif r["mirror_state"] == "bilateral":
            bucket["n_lateral_bilateral"] += 1
        else:
            bucket["n_lateral_right_only"] += 1
        bucket["total_vol_mm3"] += r["volume_mm3"]
    return by_tr


def write_summary_md(by_tr, out_path: Path):
    lines = ["# Tissue × region summary (catalogue representatives)", "",
             "Counts are ANATOMICAL structures (midline: 1 per; lateral: 1 per, "
             "with right-side representative). Implied complete mesh count per row "
             "= midline + 2 × lateral.", "",
             "| Tissue | Region | Midline | Bilateral | Right-only | Volume (mm³) |",
             "|---|---|---:|---:|---:|---:|"]
    for (tissue, region), b in sorted(by_tr.items()):
        lines.append(
            f"| {tissue} | {region} | {b['n_midline']} | "
            f"{b['n_lateral_bilateral']} | {b['n_lateral_right_only']} | "
            f"{b['total_vol_mm3']:,.1f} |"
        )
    out_path.write_text("\n".join(lines) + "\n")


def write_regional_breakdown(mesh_rows, out_path_csv: Path, out_path_md: Path):
    """Region × tissue-class rollup: total counts and volumes per anatomical region."""
    by_region = defaultdict(lambda: defaultdict(lambda: {"n": 0, "vol": 0.0}))
    for r in mesh_rows:
        by_region[r["region"]][r["tissue"]]["n"] += 1
        by_region[r["region"]][r["tissue"]]["vol"] += r["volume_mm3"]

    # Rows for CSV
    csv_rows = []
    for region in sorted(by_region.keys()):
        for tissue, counts in sorted(by_region[region].items()):
            csv_rows.append({
                "region": region,
                "tissue": tissue,
                "n_structures": counts["n"],
                "volume_mm3": round(counts["vol"], 2),
            })
    with out_path_csv.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["region", "tissue", "n_structures", "volume_mm3"])
        w.writeheader()
        w.writerows(csv_rows)

    # Compact region-only totals for Markdown
    md = ["# Regional breakdown — anatomical structures by region",
          "",
          "Counts are distinct anatomical structures (midline + right-side representatives). "
          "Use table above for tissue-level detail within each region.",
          "",
          "| Region | Bone | Muscle | Tendon/ligament | Other | Total | Volume (mm³) |",
          "|---|---:|---:|---:|---:|---:|---:|"]
    regions = sorted(by_region.keys())
    main_tissues = ("bone", "muscle", "tendon/ligament")
    for region in regions:
        counts = by_region[region]
        total_n = sum(c["n"] for c in counts.values())
        total_v = sum(c["vol"] for c in counts.values())
        main_vals = [counts.get(t, {"n": 0})["n"] for t in main_tissues]
        other_n = total_n - sum(main_vals)
        md.append(f"| {region} | {main_vals[0]} | {main_vals[1]} | {main_vals[2]} | {other_n} | "
                  f"{total_n} | {total_v:,.1f} |")
    # Global totals
    all_tissues = {t for by_t in by_region.values() for t in by_t.keys()}
    global_counts = {t: sum(by_region[r][t]["n"] for r in regions if t in by_region[r]) for t in all_tissues}
    global_total = sum(global_counts.values())
    global_vol = sum(by_region[r][t]["vol"] for r in regions for t in by_region[r])
    main_vals = [global_counts.get(t, 0) for t in main_tissues]
    other_n = global_total - sum(main_vals)
    md.append(f"| **Total** | **{main_vals[0]}** | **{main_vals[1]}** | **{main_vals[2]}** | "
              f"**{other_n}** | **{global_total}** | **{global_vol:,.1f}** |")
    out_path_md.write_text("\n".join(md) + "\n")


# ---------------------------------------------------------------------------
# Armature table
# ---------------------------------------------------------------------------

BONE_COLUMNS = [
    ("bone_name",         "Bone"),
    ("anatomical_class",  "Class"),
    ("mirror_state",      "Symmetry"),
    ("parent",            "Parent bone"),
    ("length_mm",         "Length (mm)"),
    ("n_children",        "Children"),
    ("has_ik",            "IK"),
    ("ik_chain",          "IK chain"),
    ("ik_target",         "IK target"),
    ("constraint_count",  "Constraints"),
    ("utility_flag",      "Utility"),
]


def is_utility_bone(name: str) -> bool:
    n = name.lower()
    return ("stretch_to" in n or "_xxx" in n or "bonexxx" in n
            or "target" in n or "ik_" in n or "_ik" in n)


def build_bone_rows(raw_rows):
    out = []
    for r in raw_rows:
        name = r.get("name") or r.get("bone", "")
        out.append({
            "bone_name":       name,
            "anatomical_class": r.get("anatomical_class", ""),
            "mirror_state":    "bilateral" if r.get("mirror_present") == "true"
                                else ("midline" if r.get("anatomical_class") == "midline"
                                      else "right-only"),
            "parent":          r.get("parent", ""),
            "length_mm":       round(_num(r, "length_mm"), 2),
            "n_children":      _int(r, "n_children"),
            "has_ik":          "✓" if r.get("has_ik", "").lower() in ("true", "1", "yes") else "",
            "ik_chain":        _int(r, "ik_chain"),
            "ik_target":       r.get("ik_target", ""),
            "constraint_count": _int(r, "constraint_count"),
            "utility_flag":    "utility" if is_utility_bone(name) else "anatomical",
            "_sort":           (r.get("anatomical_class", "zzz"), name),
        })
    out.sort(key=lambda r: r["_sort"])
    for r in out:
        del r["_sort"]
    return out


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mesh", type=Path, required=True)
    ap.add_argument("--armature", type=Path, default=None)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    # Mesh
    mesh_raw = read_canonical(args.mesh)
    mesh_rows = build_mesh_rows(mesh_raw)
    write_csv(mesh_rows, MESH_COLUMNS, args.out / "s_table_mesh_catalogue.csv")
    write_markdown_preview(mesh_rows, MESH_COLUMNS,
                           args.out / "s_table_mesh_catalogue.md",
                           "S-Table — Mesh catalogue", len(mesh_rows))
    # Tissue × region summary
    by_tr = build_tissue_region_summary(mesh_rows)
    write_summary_md(by_tr, args.out / "s_table_mesh_catalogue_summary.md")
    # Regional breakdown
    write_regional_breakdown(mesh_rows,
                             args.out / "regional_breakdown.csv",
                             args.out / "regional_breakdown.md")

    print(f"  → {args.out / 's_table_mesh_catalogue.csv'}  ({len(mesh_rows)} rows)")
    print(f"  → {args.out / 's_table_mesh_catalogue.md'}")
    print(f"  → {args.out / 's_table_mesh_catalogue_summary.md'}")
    print(f"  → {args.out / 'regional_breakdown.csv'}")
    print(f"  → {args.out / 'regional_breakdown.md'}")

    # Armature
    if args.armature and args.armature.exists():
        bone_raw = read_canonical(args.armature)
        bone_rows = build_bone_rows(bone_raw)
        write_csv(bone_rows, BONE_COLUMNS, args.out / "s_table_bone_catalogue.csv")
        write_markdown_preview(bone_rows, BONE_COLUMNS,
                               args.out / "s_table_bone_catalogue.md",
                               "S-Table — Armature (bone) catalogue", len(bone_rows))
        # Quick utility vs anatomical breakdown
        n_util = sum(1 for r in bone_rows if r["utility_flag"] == "utility")
        n_anat = len(bone_rows) - n_util
        print(f"  → {args.out / 's_table_bone_catalogue.csv'}  "
              f"({len(bone_rows)} rows; {n_anat} anatomical, {n_util} utility)")


if __name__ == "__main__":
    main()
