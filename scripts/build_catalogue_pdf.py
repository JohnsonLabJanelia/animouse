"""Assemble a Pokemon-card style PDF atlas from per-mesh thumbnails + catalogue CSV.

Each card shows a rendered thumbnail of one anatomical structure, with
compact metadata underneath (name, tissue, laterality, volume, dimensions).
Cards are grouped by anatomical region with section dividers.

Usage:
    python3 scripts/build_catalogue_pdf.py \\
        --catalogue ~/anibodymouse/.../inspection/mesh_inventory_flagged_canonical.csv \\
        --thumbnails ~/anibodymouse/.../figures/catalogue/thumbnails \\
        --out ~/anibodymouse/.../figures/catalogue/anatomical_catalogue.pdf \\
        [--cols 5] [--rows 4]
"""
from __future__ import annotations

import argparse
import csv
import re
import sys
from collections import OrderedDict, defaultdict
from pathlib import Path

# Import the tissue_types submodule directly (not through animouse.__init__
# which imports bpy).
import importlib.util
_spec = importlib.util.spec_from_file_location(
    "tissue_types_standalone",
    "/Users/johnsonr/src/animouse/animouse/tissue_types.py",
)
_tt = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_tt)

# Mirror render_f3 / render_mesh_cards palette overrides for matching tag colors.
TISSUE_COLORS = dict(_tt.TISSUE_COLORS)
TISSUE_COLORS.update({
    "bone":            (0.52, 0.52, 0.55, 1.0),
    "cartilage":       (0.55, 0.72, 0.86, 1.0),
    "tendon/ligament": (0.88, 0.76, 0.38, 1.0),
    "kidney":          (0.52, 0.58, 0.38, 1.0),
    "claw":            (0.32, 0.28, 0.24, 1.0),
})

# Region labeling — same rules as build_catalogue_tables.py.
REGION_RULES = [
    ("SKELETON > SKULL", "Head — skull"),
    ("SKELETON > spine", "Spine"),
    ("SKELETON > ribcage", "Thorax — ribcage"),
    ("SKELETON > ARM", "Forelimb — bones"),
    ("SKELETON > shoulder", "Shoulder — bones"),
    ("SKELETON > leg", "Hindlimb — bones"),
    ("MUSCLES and TENDONS > muscles skull", "Head — muscles"),
    ("MUSCLES and TENDONS > muscles head", "Head — muscles"),
    ("MUSCLES and TENDONS > muscles spine", "Spine — muscles"),
    ("MUSCLES and TENDONS > muscles ribcage", "Thorax — muscles"),
    ("MUSCLES and TENDONS > muscles scapula+clavicle", "Shoulder — muscles"),
    ("MUSCLES and TENDONS > muscles humerus", "Forelimb — muscles"),
    ("MUSCLES and TENDONS > muscles radius+ulna", "Forelimb — muscles"),
    ("MUSCLES and TENDONS > muscles arm", "Forelimb — muscles"),
    ("MUSCLES and TENDONS > ARM TENDONS", "Forelimb — tendons"),
    ("MUSCLES and TENDONS > TENDONS SHOULDER", "Shoulder — tendons"),
    ("MUSCLES and TENDONS > muscles femur", "Hindlimb — muscles"),
    ("MUSCLES and TENDONS > muscles tibia", "Hindlimb — muscles"),
    ("MUSCLES and TENDONS > muscles foot", "Hindlimb — foot"),
    ("ORGANS", "Organs"),
    ("axis of rotation", "Rigging references"),
]

REGION_ORDER = [
    "Head — skull", "Head — muscles",
    "Spine", "Spine — muscles",
    "Thorax — ribcage", "Thorax — muscles",
    "Shoulder — bones", "Shoulder — muscles", "Shoulder — tendons",
    "Forelimb — bones", "Forelimb — muscles", "Forelimb — tendons",
    "Hindlimb — bones", "Hindlimb — muscles", "Hindlimb — foot",
    "Organs", "Rigging references", "Other",
]


def region_for(collection: str) -> str:
    c = collection or ""
    for prefix, label in REGION_RULES:
        if prefix.lower() in c.lower():
            return label
    return "Other"


SAFE_FS_RE = re.compile(r"[^A-Za-z0-9._-]+")


def safe_filename(name: str) -> str:
    return SAFE_FS_RE.sub("_", name).strip("_") or "unnamed"


def read_catalogue(path: Path):
    rows = list(csv.DictReader(path.open()))
    for r in rows:
        r["region"] = region_for(r.get("collection", ""))
        for k in ("volume_mm3", "surface_area_mm2",
                  "dim_x_mm", "dim_y_mm", "dim_z_mm", "cx", "cy", "cz"):
            try:
                r[k] = float(r.get(k, 0) or 0)
            except ValueError:
                r[k] = 0.0
    return rows


_NAT_RE = re.compile(r"(\d+)")


def _natural_key(s):
    """Sort so that 'CA2' < 'CA3' < ... < 'CA10' < 'CA20' (treats embedded
    digit runs as integers). Without this, string-only sort orders the caudal
    vertebrae CA1, CA10, CA11, ..., CA19, CA2, CA20, ..., CA29, CA3, CA30, ...
    which interleaves CA3 between CA29 and CA30 — confusing on the page."""
    parts = _NAT_RE.split(s or "")
    return [int(p) if p.isdigit() else p.lower() for p in parts]


def group_by_region(rows):
    groups = defaultdict(list)
    for r in rows:
        groups[r["region"]].append(r)

    def sort_key(r):
        return _natural_key(r.get("display_name") or r["name"])

    # Preserve the ordered region list; append unlisted regions at the end.
    ordered = OrderedDict()
    for region in REGION_ORDER:
        if region in groups:
            ordered[region] = sorted(groups[region], key=sort_key)
    for region, members in groups.items():
        if region not in ordered:
            ordered[region] = sorted(members, key=sort_key)
    return ordered


# -------------------------------------------------------------------------
# PDF rendering
# -------------------------------------------------------------------------

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.patches import FancyBboxPatch, Rectangle
import matplotlib.image as mpimg


def draw_card(fig, gs, row_data, thumb_dir, tissue_color, missing_thumb_msg=None):
    """Draw a single card into a GridSpec cell (`gs`)."""
    # Sub-grid: image on top (3 of 4 rows) + metadata below (1 of 4).
    sub = gs.subgridspec(4, 1, hspace=0.02)
    ax_img = fig.add_subplot(sub[0:3, 0])
    ax_txt = fig.add_subplot(sub[3, 0])

    # Card-like background for the whole cell.
    ax_txt.set_facecolor("#f8f8f8")
    for ax in (ax_img, ax_txt):
        ax.set_xticks([]); ax.set_yticks([])
        for s in ax.spines.values():
            s.set_linewidth(0.5)
            s.set_color("#dddddd")

    # --- Image ---
    thumb_path = thumb_dir / f"{safe_filename(row_data['name'])}.png"
    if thumb_path.exists():
        img = mpimg.imread(thumb_path)
        ax_img.imshow(img)
    else:
        ax_img.text(0.5, 0.5, missing_thumb_msg or "no render",
                    ha="center", va="center", color="#aaa", fontsize=7)
    ax_img.set_xlim(*ax_img.get_xlim())

    # --- Metadata block ---
    ax_txt.set_xlim(0, 1); ax_txt.set_ylim(0, 1)

    # Tissue pill (colored swatch + label) in top-left.
    tissue = row_data.get("tissue", "")
    ax_txt.add_patch(Rectangle((0.03, 0.72), 0.07, 0.22,
                                color=tissue_color, transform=ax_txt.transAxes))
    ax_txt.text(0.12, 0.83, tissue, fontsize=5.5, va="center", ha="left", color="#333")

    # Symmetry / side mark in top-right. ASCII/BMP-only glyphs so DejaVu can
    # render everything.
    mirror = row_data.get("mirror_present", "")
    if row_data.get("anatomical_class") == "midline":
        sym = "midline"
    elif mirror == "true":
        sym = "L+R"
    else:
        sym = "R only"
    ax_txt.text(0.97, 0.83, sym, fontsize=5, va="center", ha="right", color="#666")

    # Name (main line).
    display = row_data.get("display_name") or row_data["name"]
    # Truncate very long names.
    if len(display) > 28:
        display = display[:25] + "…"
    ax_txt.text(0.03, 0.60, display, fontsize=6.5, va="center", ha="left",
                weight="bold", color="#111")

    # Numeric data. Vol + SA on one line, Dim on the next.
    v = row_data["volume_mm3"]
    sa = row_data["surface_area_mm2"]
    dm = max(row_data["dim_x_mm"], row_data["dim_y_mm"], row_data["dim_z_mm"])
    ax_txt.text(0.03, 0.35, f"Vol {v:,.2f} mm³   SA {sa:,.2f} mm²",
                fontsize=5.5, va="center", ha="left", color="#444")
    ax_txt.text(0.03, 0.12, f"Dim {dm:,.2f} mm",
                fontsize=5.5, va="center", ha="left", color="#444")
    return ax_img, ax_txt


def draw_region_header_page(pdf, region, count):
    fig = plt.figure(figsize=(8.5, 11))
    fig.patch.set_facecolor("white")
    ax = fig.add_axes([0.05, 0.35, 0.9, 0.3])
    ax.set_axis_off()
    ax.text(0, 0.7, region, fontsize=28, weight="bold", color="#111")
    ax.text(0, 0.35, f"{count} anatomical structures", fontsize=12, color="#666")
    ax.text(0, 0.1, "Catalogue representatives (right-side for lateral structures, midline for unpaired)",
            fontsize=8, color="#999")
    pdf.savefig(fig)
    plt.close(fig)


def build_pdf(catalogue_rows, thumb_dir: Path, out_pdf: Path,
              cols: int, rows_per_page: int, page_size=(8.5, 11)):
    groups = group_by_region(catalogue_rows)
    cards_per_page = cols * rows_per_page
    total_rows = len(catalogue_rows)

    with PdfPages(out_pdf) as pdf:
        # Cover page.
        fig = plt.figure(figsize=page_size)
        fig.patch.set_facecolor("white")
        ax = fig.add_axes([0.08, 0.35, 0.84, 0.3])
        ax.set_axis_off()
        ax.text(0, 0.8, "AniMouse — Anatomical catalogue",
                fontsize=26, weight="bold", color="#111")
        ax.text(0, 0.55, f"{total_rows} distinct anatomical structures "
                         f"(midline + right-side representatives)",
                fontsize=12, color="#444")
        by_tis = defaultdict(int)
        for r in catalogue_rows:
            by_tis[r.get("tissue", "")] += 1
        summary = "  ·  ".join(f"{n} {t}" for t, n in sorted(by_tis.items(), key=lambda kv: -kv[1])[:5])
        ax.text(0, 0.38, summary, fontsize=9, color="#777")
        ax.text(0, 0.18, "* = muscle mesh still under anatomical identification",
                fontsize=8, color="#888", style="italic")
        pdf.savefig(fig)
        plt.close(fig)

        for region, members in groups.items():
            # No dedicated region-title page; the banner at the top of each
            # content page identifies the region. Saves ~18 pages across the
            # whole PDF and flows better.
            for page_start in range(0, len(members), cards_per_page):
                page_rows = members[page_start: page_start + cards_per_page]
                fig = plt.figure(figsize=page_size)
                fig.patch.set_facecolor("white")
                # Top banner with region + page info.
                banner = fig.add_axes([0.04, 0.94, 0.92, 0.04])
                banner.set_axis_off()
                banner.text(0, 0.2, region, fontsize=10, weight="bold", color="#111")
                banner.text(1, 0.2,
                            f"{page_start + 1}–{page_start + len(page_rows)} of {len(members)}",
                            fontsize=8, color="#888", ha="right")
                # Grid of cards.
                grid = fig.add_gridspec(rows_per_page, cols,
                                         left=0.04, right=0.96,
                                         top=0.92, bottom=0.04,
                                         wspace=0.10, hspace=0.18)
                for i, r in enumerate(page_rows):
                    row_i = i // cols; col_i = i % cols
                    cell_gs = grid[row_i, col_i]
                    tissue_color = TISSUE_COLORS.get(r.get("tissue", ""), (0.6, 0.6, 0.6, 1.0))
                    draw_card(fig, cell_gs, r, thumb_dir, tissue_color)
                pdf.savefig(fig, dpi=200)
                plt.close(fig)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--catalogue", type=Path, required=True)
    ap.add_argument("--thumbnails", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--cols", type=int, default=5)
    ap.add_argument("--rows", type=int, default=4)
    args = ap.parse_args()
    args.out.parent.mkdir(parents=True, exist_ok=True)

    rows = read_catalogue(args.catalogue)
    print(f"Building PDF for {len(rows)} catalogue rows ({args.cols}×{args.rows} = "
          f"{args.cols * args.rows} per page)")
    build_pdf(rows, args.thumbnails, args.out, args.cols, args.rows)
    print(f"  → {args.out}")


if __name__ == "__main__":
    main()
