"""Compose Figure 3 panels from rendered views.

Reads the PNGs emitted by render_f3.py and assembles publication plates:
  F3_hero.png                  — single 3/4 hero render with scale bar
  F3_orthographic_plate.png    — 4-up (dorsal, ventral, lateral-R, lateral-L)
  F3_layered_reveal.png        — 3-panel reveal (full, muscles+tendons, skeleton)
  F3_tissue_legend.png         — color-coded tissue legend with quantitative counts

Requires: matplotlib, pillow, pandas. No Blender.

Usage:
    python3 scripts/compose_f3_plate.py \\
        --renders  ~/anibodymouse/claude_mouse_unknown_muscles/figures/f3 \\
        --inventory ~/anibodymouse/claude_mouse_unknown_muscles/inspection/mesh_inventory_flagged.csv \\
        --out       ~/anibodymouse/claude_mouse_unknown_muscles/figures/f3/plates
"""
from __future__ import annotations

import argparse
import csv
import sys
from collections import Counter, defaultdict
from pathlib import Path

# Import the tissue_types submodule directly (the package __init__ imports bpy,
# which isn't available outside Blender).
import importlib.util
_spec = importlib.util.spec_from_file_location(
    "tissue_types_standalone",
    "/Users/johnsonr/src/animouse/animouse/tissue_types.py",
)
_tt = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_tt)
TISSUE_COLORS = dict(_tt.TISSUE_COLORS)
# Mirror the palette overrides used by render_f3.py so the legend swatches match
# what shows up in the renders.
TISSUE_COLORS.update({
    "bone":            (0.52, 0.52, 0.55, 1.0),
    "cartilage":       (0.55, 0.72, 0.86, 1.0),
    "tendon/ligament": (0.88, 0.76, 0.38, 1.0),
    "kidney":          (0.52, 0.58, 0.38, 1.0),
    "claw":            (0.32, 0.28, 0.24, 1.0),
})

import matplotlib.pyplot as plt
import matplotlib.image as mpimg
from matplotlib.patches import Rectangle


# Physical scene length along Z (head→tail) in mm — written into manifest by renderer.
DEFAULT_SCENE_LENGTH_MM = 160.7


def load_manifest(renders_dir: Path):
    import json
    p = renders_dir / "manifest.json"
    if not p.exists():
        return None
    return json.loads(p.read_text())


def load_inventory(path: Path):
    rows = list(csv.DictReader(path.open()))
    for r in rows:
        for k in ("vertices", "faces"):
            r[k] = int(r[k])
        for k in ("volume_mm3", "surface_area_mm2", "dim_x_mm", "dim_y_mm", "dim_z_mm"):
            r[k] = float(r[k])
        r["needs_identification"] = r.get("needs_identification", "false") == "true"
    return rows


def tissue_counts(rows):
    """Return (counts, volumes, named_muscle_count, unnamed_muscle_count)."""
    counts = Counter(r["tissue"] for r in rows)
    volumes = defaultdict(float)
    for r in rows:
        volumes[r["tissue"]] += r["volume_mm3"]
    named_muscle = sum(1 for r in rows if r["tissue"] == "muscle" and not r["needs_identification"])
    unnamed_muscle = sum(1 for r in rows if r["tissue"] == "muscle" and r["needs_identification"])
    return counts, volumes, named_muscle, unnamed_muscle


def add_scale_bar(ax, img_shape, scene_length_mm, view_axis_mm, bar_mm=10):
    """Draw a scale bar for `bar_mm` millimeters along the horizontal axis."""
    h, w = img_shape[:2]
    # Fraction of width that corresponds to view_axis_mm (the physical span captured in this view's long axis).
    px_per_mm = w / view_axis_mm
    bar_px = bar_mm * px_per_mm
    margin = 0.04 * w
    y = h - 0.06 * h
    ax.add_patch(Rectangle((margin, y - 0.012 * h), bar_px, 0.012 * h, color="black", zorder=5))
    ax.text(margin + bar_px / 2, y - 0.03 * h, f"{bar_mm} mm",
            ha="center", va="top", fontsize=9, zorder=5)


def save_hero(renders_dir: Path, out_dir: Path):
    src = renders_dir / "hero_three_quarter.png"
    if not src.exists():
        print(f"skip hero: {src} missing")
        return
    img = mpimg.imread(src)
    fig, ax = plt.subplots(figsize=(6, 6), dpi=300)
    ax.imshow(img)
    ax.set_axis_off()
    # Hero view diagonal — roughly full body length visible.
    add_scale_bar(ax, img.shape, DEFAULT_SCENE_LENGTH_MM, DEFAULT_SCENE_LENGTH_MM)
    fig.subplots_adjust(0, 0, 1, 1)
    out = out_dir / "F3_hero.png"
    fig.savefig(out, dpi=300, bbox_inches="tight", pad_inches=0.02)
    plt.close(fig)
    print(f"  → {out}")


ORTHO_LAYOUT = [
    # (label, filename, subplot position (row, col), view_axis_mm)
    ("Dorsal",         "dorsal.png",         (0, 0), DEFAULT_SCENE_LENGTH_MM),
    ("Ventral",        "ventral.png",        (0, 1), DEFAULT_SCENE_LENGTH_MM),
    ("Lateral right",  "lateral_right.png",  (1, 0), DEFAULT_SCENE_LENGTH_MM),
    ("Lateral left",   "lateral_left.png",   (1, 1), DEFAULT_SCENE_LENGTH_MM),
]


def save_orthographic_plate(renders_dir: Path, out_dir: Path):
    fig, axes = plt.subplots(2, 2, figsize=(10, 8), dpi=300)
    any_ok = False
    for label, fname, (r, c), axis_mm in ORTHO_LAYOUT:
        ax = axes[r, c]
        p = renders_dir / fname
        if not p.exists():
            ax.set_axis_off()
            ax.set_title(f"{label} (missing)", fontsize=10)
            continue
        any_ok = True
        img = mpimg.imread(p)
        ax.imshow(img)
        ax.set_title(label, fontsize=11, pad=6)
        ax.set_xticks([]); ax.set_yticks([])
        for s in ax.spines.values():
            s.set_visible(False)
        add_scale_bar(ax, img.shape, DEFAULT_SCENE_LENGTH_MM, axis_mm)
    if not any_ok:
        plt.close(fig)
        print("  skip orthographic plate: no source renders")
        return
    fig.tight_layout()
    out = out_dir / "F3_orthographic_plate.png"
    fig.savefig(out, dpi=300, bbox_inches="tight")
    plt.close(fig)
    print(f"  → {out}")


REVEAL_LAYOUT = [
    ("All tissues",       "reveal_full.png"),
    ("Muscles + tendons", "reveal_muscles.png"),
    ("Skeleton only",     "reveal_skeleton.png"),
]


def save_layered_reveal(renders_dir: Path, out_dir: Path):
    fig, axes = plt.subplots(1, 3, figsize=(15, 5), dpi=300)
    any_ok = False
    for i, (label, fname) in enumerate(REVEAL_LAYOUT):
        ax = axes[i]
        p = renders_dir / fname
        if not p.exists():
            ax.set_axis_off()
            ax.set_title(f"{label} (missing)", fontsize=10)
            continue
        any_ok = True
        img = mpimg.imread(p)
        ax.imshow(img)
        ax.set_title(label, fontsize=11, pad=6)
        ax.set_xticks([]); ax.set_yticks([])
        for s in ax.spines.values():
            s.set_visible(False)
        add_scale_bar(ax, img.shape, DEFAULT_SCENE_LENGTH_MM, DEFAULT_SCENE_LENGTH_MM)
    if not any_ok:
        plt.close(fig)
        print("  skip layered reveal: no source renders")
        return
    fig.tight_layout()
    out = out_dir / "F3_layered_reveal.png"
    fig.savefig(out, dpi=300, bbox_inches="tight")
    plt.close(fig)
    print(f"  → {out}")


def save_tissue_legend(inventory_rows, out_dir: Path):
    counts, volumes, named_m, unnamed_m = tissue_counts(inventory_rows)
    # Display order: muscle-forward, bones, soft tissue.
    order = ["bone", "muscle", "tendon/ligament", "cartilage",
             "cardiac", "vasculature", "kidney", "urinary",
             "gastrointestinal", "central nervous system",
             "tongue", "eye", "retina", "claw", "connective tissue", "unknown"]
    order = [t for t in order if counts.get(t, 0)]
    fig, ax = plt.subplots(figsize=(6.5, 0.48 * len(order) + 1.0), dpi=300)
    for i, tissue in enumerate(order):
        y = len(order) - 1 - i
        rgba = TISSUE_COLORS.get(tissue, TISSUE_COLORS["unknown"])
        ax.add_patch(Rectangle((0, y - 0.35), 0.4, 0.7, color=rgba))
        label = tissue
        if tissue == "muscle":
            label = f"muscle  (named {named_m}, under review {unnamed_m}*)"
        ax.text(0.5, y, label, va="center", fontsize=10)
        ax.text(5.9, y, f"n = {counts[tissue]}", va="center", ha="right", fontsize=10)
        ax.text(7.9, y, f"{volumes[tissue]:,.0f} mm³", va="center", ha="right", fontsize=10)
    ax.set_xlim(-0.2, 8.0)
    ax.set_ylim(-0.5, len(order) - 0.5)
    ax.set_axis_off()
    ax.set_title("Tissue composition", fontsize=11, pad=8, loc="left")
    fig.tight_layout()
    out = out_dir / "F3_tissue_legend.png"
    fig.savefig(out, dpi=300, bbox_inches="tight")
    plt.close(fig)
    print(f"  → {out}")
    return counts, volumes, named_m, unnamed_m


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--renders", type=Path, required=True)
    ap.add_argument("--inventory", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    rows = load_inventory(args.inventory)
    save_hero(args.renders, args.out)
    save_orthographic_plate(args.renders, args.out)
    save_layered_reveal(args.renders, args.out)
    counts, volumes, nm, um = save_tissue_legend(rows, args.out)

    print(f"\nCounts: {dict(counts)}")
    print(f"Named muscles: {nm}    Under review (*): {um}")


if __name__ == "__main__":
    main()
