"""Compose the armature overlay figure for F4.

Reads armature_skeleton_bg.png + armature_projections.json (both produced by
render_armature_overlay.py) and draws the armature on top of a dimmed
skeleton background. Bones are colored by anatomical region; the four IK
chains are rendered thicker and brighter; IK targets are marked.

Usage:
    python3 scripts/compose_armature_overlay.py \\
        --projections ~/anibodymouse/claude_mouse_unknown_muscles/figures/catalogue/armature/armature_projections.json \\
        --out         ~/anibodymouse/claude_mouse_unknown_muscles/figures/catalogue/armature/F4_armature_overlay.png
"""
from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.image as mpimg
from matplotlib.lines import Line2D
from matplotlib.patches import FancyBboxPatch
import numpy as np


# Region palette, tuned for good contrast against the gray skeleton.
REGION_COLORS = {
    "spine":    "#1f5fbd",   # deep blue
    "ribcage":  "#4fb3a9",   # teal
    "skull":    "#8856a7",   # purple
    "forelimb": "#d95f0e",   # orange
    "hindlimb": "#b1293b",   # deep red
    "shoulder": "#e6ab02",   # mustard
    "pelvis":   "#a65628",   # brown
    "other":    "#808080",   # gray (catch-all)
}

IK_CHAIN_COLOR   = "#111111"
IK_TARGET_COLOR  = "#f8e71c"


def load_bones(path: Path):
    with path.open() as f:
        data = json.load(f)
    return data


_SIDE_RE = re.compile(
    r"^(.+?)[\s_.\-]+(right|left|r|l)(\.\d+)?\s*$", re.IGNORECASE
)
_SIDE_FALSE_POS = {"lateralis", "lateral", "rectus"}


def bone_side(name: str) -> str:
    """Return 'left', 'right', or 'midline/unknown' from the bone name."""
    m = _SIDE_RE.match(name.strip())
    if not m:
        return "midline"
    base_last = m.group(1).split("_")[-1].split(".")[-1].lower()
    tok = m.group(2).lower()
    if base_last in _SIDE_FALSE_POS and tok in ("l", "r"):
        return "midline"
    return "right" if tok in ("right", "r") else "left"


def filter_visible(bones, res, drop_side: str = "left"):
    """Keep bones in front of camera; drop bones on `drop_side` (midline kept)."""
    out = []
    for b in bones:
        if b["head_depth"] <= 0 and b["tail_depth"] <= 0:
            continue
        if drop_side and bone_side(b["name"]) == drop_side:
            continue
        out.append(b)
    return out


def draw_overlay(data, out_path: Path, dim_bg: float = 0.55,
                 hide_utility: bool = True, drop_side: str = "left"):
    bg = mpimg.imread(data["image_path"])
    res_x, res_y = data["resolution"]
    bones = filter_visible(data["bones"], (res_x, res_y), drop_side=drop_side)

    # Figure aspect follows the image + a right-hand legend panel.
    img_aspect = res_x / res_y  # portrait if <1
    fig_h = 11.0  # landscape-long figure, tall portrait
    fig_w = fig_h * img_aspect + 3.5  # image column + legend column (3.5 in)
    fig = plt.figure(figsize=(fig_w, fig_h), dpi=200)
    fig.patch.set_facecolor("white")
    img_col_frac = (fig_h * img_aspect) / fig_w
    ax_main = fig.add_axes([0.01, 0.02, img_col_frac * 0.98, 0.96])
    ax_leg  = fig.add_axes([img_col_frac + 0.02, 0.02,
                             1 - img_col_frac - 0.03, 0.96])
    ax_leg.set_axis_off()

    # Dim the skeleton so the armature reads as foreground.
    faded = np.ones_like(bg)
    faded[..., :3] = bg[..., :3] * dim_bg + (1.0 - dim_bg)
    if bg.shape[2] == 4:
        faded[..., 3] = bg[..., 3]
    ax_main.imshow(faded, extent=(0, res_x, res_y, 0))
    ax_main.set_xlim(0, res_x)
    ax_main.set_ylim(res_y, 0)  # image-coordinate Y (top-down)
    ax_main.set_axis_off()

    # Split bones into three render passes so styling stacks cleanly:
    #   1. Utility (dashed, very faded) at the bottom
    #   2. Regular anatomical bones (solid, colored by region)
    #   3. IK chains + IK targets (thick, high-contrast, on top)
    utility_bones   = [b for b in bones if b.get("is_utility")]
    anatomical      = [b for b in bones if not b.get("is_utility") and not b.get("in_ik_chain")]
    ik_chain_bones  = [b for b in bones if b.get("in_ik_chain") and not b.get("is_utility")]

    def _line(b, **kw):
        x0, y0 = b["head_px"]; x1, y1 = b["tail_px"]
        ax_main.add_line(Line2D([x0, x1], [y0, y1], **kw))

    if not hide_utility:
        for b in utility_bones:
            _line(b, color="#aaaaaa", linewidth=0.4, linestyle=(0, (2, 3)), alpha=0.5, zorder=2)
    for b in anatomical:
        color = REGION_COLORS.get(b["region"], REGION_COLORS["other"])
        _line(b, color=color, linewidth=1.3, alpha=0.92, zorder=3,
              solid_capstyle="round")
    for b in ik_chain_bones:
        color = REGION_COLORS.get(b["region"], IK_CHAIN_COLOR)
        # Draw a black halo beneath, then the colored core on top.
        _line(b, color="#000000", linewidth=3.6, alpha=0.6, zorder=4,
              solid_capstyle="round")
        _line(b, color=color, linewidth=2.4, alpha=1.0, zorder=5,
              solid_capstyle="round")

    # IK targets: find the bones with an IK constraint and mark their TIP
    # (tail position) — that's what the IK chain is trying to reach.
    for b in bones:
        if not b.get("has_ik"):
            continue
        x, y = b["tail_px"]
        ax_main.scatter([x], [y], s=120, facecolor=IK_TARGET_COLOR,
                        edgecolor="black", linewidths=1.4, zorder=7, marker="o")
        ax_main.annotate(
            f"IK ({b['ik_chain_count']})",
            (x, y), xytext=(12, 0), textcoords="offset points",
            fontsize=7.5, color="#111", fontweight="bold",
            va="center", zorder=8,
        )

    # ------------------ Legend panel ------------------
    # Count bones per region (drawing-layer partition: anatomical + IK) so the
    # legend reflects what is VISIBLE, not the raw armature count.
    visible_counts = Counter()
    for b in anatomical + ik_chain_bones:
        visible_counts[b["region"]] += 1
    utility_count = len(utility_bones)
    ik_bones_total = len(ik_chain_bones)
    y = 0.97
    ax_leg.set_xlim(0, 1); ax_leg.set_ylim(0, 1)

    ax_leg.text(0.02, y, "Armature overlay",
                fontsize=11, weight="bold", color="#111")
    y -= 0.035
    ax_leg.text(0.02, y, "3/4 ventral-right view", fontsize=8.5, color="#555", style="italic")
    y -= 0.025
    side_note = "midline + right-side only" if drop_side == "left" else "midline + left-side only"
    ax_leg.text(0.02, y, side_note, fontsize=8.5, color="#555", style="italic")
    y -= 0.03
    ax_leg.text(0.02, y, f"{sum(visible_counts.values()) + utility_count} rig bones shown",
                fontsize=8, color="#555")
    y -= 0.05

    ax_leg.text(0.02, y, "Region", fontsize=9, weight="bold", color="#333")
    y -= 0.035
    for region in ("spine", "ribcage", "skull", "shoulder", "pelvis",
                   "forelimb", "hindlimb", "other"):
        n = visible_counts.get(region, 0)
        if n == 0 and region not in ("spine", "forelimb", "hindlimb"):
            continue
        c = REGION_COLORS[region]
        ax_leg.add_line(Line2D([0.02, 0.12], [y, y], color=c, linewidth=2.4,
                               transform=ax_leg.transAxes, solid_capstyle="round"))
        ax_leg.text(0.15, y, f"{region}  ({n})", fontsize=8, va="center", color="#333")
        y -= 0.033

    if utility_count:
        y -= 0.02
        style = "hidden" if hide_utility else "drawn"
        ax_leg.add_line(Line2D([0.02, 0.12], [y, y], color="#aaaaaa", linewidth=1.0,
                               linestyle=(0, (2, 3)), transform=ax_leg.transAxes,
                               alpha=0.4 if hide_utility else 1.0))
        ax_leg.text(0.15, y, f"utility / stretch-to  ({utility_count}, {style})",
                    fontsize=8, va="center", color="#555")
        y -= 0.033

    if ik_bones_total:
        y -= 0.03
        ax_leg.text(0.02, y, "IK chains", fontsize=9, weight="bold", color="#111")
        y -= 0.035
        # Represent IK chain with thick halo line
        ax_leg.add_line(Line2D([0.02, 0.12], [y, y], color="#000", linewidth=4.0,
                               transform=ax_leg.transAxes, alpha=0.6))
        ax_leg.add_line(Line2D([0.02, 0.12], [y, y], color=REGION_COLORS["forelimb"],
                               linewidth=2.4, transform=ax_leg.transAxes))
        ax_leg.text(0.15, y, f"IK-driven bone  ({ik_bones_total})",
                    fontsize=8, va="center", color="#333")
        y -= 0.04
        ax_leg.scatter([0.07], [y], s=80, facecolor=IK_TARGET_COLOR,
                       edgecolor="black", linewidths=1.0,
                       transform=ax_leg.transAxes, zorder=3)
        ax_leg.text(0.15, y, "IK chain tip (end-effector)", fontsize=8, va="center", color="#333")
        y -= 0.04
        # List the chains.
        y -= 0.02
        ax_leg.text(0.02, y, "4 chains in this rig:", fontsize=8, color="#555", style="italic")
        y -= 0.03
        chain_list = [b for b in bones if b.get("has_ik")]
        chain_list.sort(key=lambda b: b["name"])
        for b in chain_list:
            ax_leg.text(0.04, y,
                        f"• {b['name']}  (n={b['ik_chain_count']})",
                        fontsize=7, color="#444")
            y -= 0.028

    fig.savefig(out_path, dpi=220, facecolor="white", bbox_inches="tight")
    plt.close(fig)
    print(f"  → {out_path}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--projections", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--dim", type=float, default=0.55,
                    help="Skeleton background dim factor (0.0 = white, 1.0 = full)")
    ap.add_argument("--show-utility", action="store_true",
                    help="Draw stretch-to utility bones (default: hide)")
    ap.add_argument("--drop-side", choices=("left", "right", "none"), default="left",
                    help="Which side's bones to hide (default: left — keep midline + right only)")
    args = ap.parse_args()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    data = load_bones(args.projections)
    drop = None if args.drop_side == "none" else args.drop_side
    draw_overlay(data, args.out, dim_bg=args.dim,
                 hide_utility=not args.show_utility, drop_side=drop)


if __name__ == "__main__":
    main()
