"""Composite per-pose renders into a montage image.

Arranges them in a 2×2 grid (for 4 poses) with labels and a title. Matches
the visual style of our other figures.

Usage:
    python3 scripts/compose_pose_montage.py \\
        --renders ~/anibodymouse/claude_mouse_unknown_muscles/figures/catalogue/poses \\
        --out ~/anibodymouse/claude_mouse_unknown_muscles/figures/catalogue/poses/F4_pose_montage.png
"""
from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.image as mpimg


# Matches the POSES order in render_pose_montage.py. Edit both together if
# renaming poses or changing the montage content.
POSE_ORDER = [
    ("rest",          "Rest pose"),
    ("t_pose",        "T-pose"),
    ("reach_forward", "Reaching forward"),
    ("arms_up",       "Forelimbs raised"),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--renders", type=Path, required=True,
                    help="Directory containing pose_*.png files")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--cols", type=int, default=2)
    args = ap.parse_args()
    args.out.parent.mkdir(parents=True, exist_ok=True)

    rows = (len(POSE_ORDER) + args.cols - 1) // args.cols
    # Load first image to infer aspect.
    first = mpimg.imread(args.renders / f"pose_{POSE_ORDER[0][0]}.png")
    img_aspect = first.shape[1] / first.shape[0]
    # figsize: each cell is ~4 in wide by 4/aspect tall
    cell_w = 4.0
    cell_h = cell_w / img_aspect
    fig_w = cell_w * args.cols + 0.4
    fig_h = cell_h * rows + 0.8
    fig, axes = plt.subplots(rows, args.cols, figsize=(fig_w, fig_h), dpi=200)
    if rows == 1 and args.cols == 1:
        axes = [[axes]]
    elif rows == 1:
        axes = [axes]
    elif args.cols == 1:
        axes = [[a] for a in axes]

    for i, (key, label) in enumerate(POSE_ORDER):
        r, c = i // args.cols, i % args.cols
        ax = axes[r][c]
        path = args.renders / f"pose_{key}.png"
        if not path.exists():
            ax.text(0.5, 0.5, f"(missing: {path.name})", ha="center", va="center",
                    fontsize=9, color="#888")
            ax.set_axis_off()
            continue
        img = mpimg.imread(path)
        ax.imshow(img)
        ax.set_title(label, fontsize=11, weight="bold", color="#111", pad=6)
        ax.set_xticks([]); ax.set_yticks([])
        for s in ax.spines.values():
            s.set_linewidth(0.4); s.set_color("#dddddd")

    # Hide any unused cells.
    for i in range(len(POSE_ORDER), rows * args.cols):
        r, c = i // args.cols, i % args.cols
        axes[r][c].set_axis_off()

    fig.suptitle("F4 — Pose demonstration (skeletal rig, bone-parented)",
                 fontsize=13, weight="bold", y=0.995)
    fig.text(0.5, 0.005,
             "Soft tissues hidden — mesh weight-painting is ongoing. "
             "Bones follow the armature via rigid bone-parenting.",
             ha="center", fontsize=8, style="italic", color="#555")
    fig.tight_layout(rect=(0, 0.015, 1, 0.985))
    fig.savefig(args.out, dpi=200, facecolor="white", bbox_inches="tight")
    plt.close(fig)
    print(f"  → {args.out}")


if __name__ == "__main__":
    main()
