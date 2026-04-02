"""
Annotate whole-body renders with medical textbook-style leader lines and labels.

Layout algorithm:
  1. Find the 3D centroid of every labeled body part
  2. Sort all centroids by Z-axis (height along the mouse spine)
  3. Split into two groups by Y-axis (dorsal vs ventral) — left and right columns
  4. Each column's labels are in Z-order, so leader lines never cross
  5. Labels are evenly spaced vertically in their column

Usage:
    python3 scripts/annotate_figure.py
    python3 scripts/annotate_figure.py --view lateral --layers full
"""

import argparse
import json
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.image as mpimg
import numpy as np

SUPP_DIR = os.path.expanduser("~/anibodymouse/claude_mouse/supplementary/figures")

# Tissue type colors for label dots
TISSUE_LABEL_COLORS = {
    "bone":                   "#8A8068",
    "cartilage":              "#7AADCC",
    "muscle":                 "#C03333",
    "tendon/ligament":        "#CCAA44",
    "central nervous system": "#9988BB",
    "gastrointestinal":       "#6B9944",
    "kidney":                 "#9E4747",
    "cardiac":                "#D13852",
    "vasculature":            "#852E38",
    "eye":                    "#474752",
    "retina":                 "#CC9922",
    "tongue":                 "#CC7777",
    "urinary":                "#BBAA55",
    "connective tissue":      "#AA9988",
    "unknown":                "#888888",
}

# Structures to label per view
LABEL_SETS = {
    "lateral_skeleton": [
        ("Skull", "Skull"),
        ("Mandible_right", "Mandible"),
        ("Hyoid", "Hyoid"),
        ("C1", "Atlas (C1)"),
        ("C2", "Axis (C2)"),
        ("C7", "C7"),
        ("T1", "T1"),
        ("T7", "T7"),
        ("T13", "T13"),
        ("L1", "L1"),
        ("L6", "L6"),
        ("sacrum", "Sacrum"),
        ("CA1", "Caudal vert. 1"),
        ("CA15", "CA15"),
        ("CA30", "CA30"),
        ("scapula_right", "Scapula"),
        ("clavicle_right", "Clavicle"),
        ("humerus_right", "Humerus"),
        ("Radius_left", "Radius"),
        ("Ulna_left", "Ulna"),
        ("Rib_1a_right", "Rib 1"),
        ("Rib_7_right", "Rib 7"),
        ("Rib_13_right", "Rib 13"),
        ("Manubrium", "Manubrium"),
        ("Sternebrum_4", "Sternum"),
        ("Rib_1b_right", "Costal cartilage"),
        ("Ossa coxae", "Os coxae (pelvis)"),
        ("Femur_right", "Femur"),
        ("Patella_right", "Patella"),
        ("Tibia_and _Fibiula_right", "Tibia & Fibula"),
        ("Calcaneus_right", "Calcaneus"),
        ("Talus_right", "Talus"),
    ],
    "lateral_full": [
        # --- Head ---
        ("Skull", "Skull"),
        ("Mandible_right", "Mandible"),
        ("mouse_skull_P1a.1667", "Eye"),
        ("Tongue", "Tongue"),
        ("CNS", "Brain & Spinal cord"),
        # --- Spine landmarks ---
        ("C1", "Atlas (C1)"),
        ("T1", "T1"),
        ("L1", "L1"),
        ("sacrum", "Sacrum"),
        # --- Shoulder & arm ---
        ("scapula_right", "Scapula"),
        ("clavicle_right", "Clavicle"),
        ("humerus_right", "Humerus"),
        # --- Key muscles (largest/most visible) ---
        ("Acromiotrapezius_right", "Acromiotrapezius"),
        ("Spinotrapezius_right", "Spinotrapezius"),
        ("Pectoralis_major_superficial_right", "Pectoralis major"),
        ("Latissimus_dorsi", "Latissimus dorsi"),
        ("Cutaneous_maximus", "Cutaneous maximus"),
        ("Triceps_brachii_LH", "Triceps brachii"),
        ("Biceps_brachii", "Biceps brachii"),
        # --- Thorax ---
        ("Rib_1a_right", "Rib 1"),
        ("Rib_13_right", "Rib 13"),
        # --- Organs ---
        ("heart", "Heart"),
        ("kidney_right", "Kidney"),
        ("Lower_intestine", "Intestine"),
        ("bladder", "Bladder"),
        # --- Pelvis & hindlimb ---
        ("Ossa coxae", "Os coxae (pelvis)"),
        ("Gluteus medius", "Gluteus medius"),
        ("Biceps_femorus_A", "Biceps femoris"),
        ("Femur_right", "Femur"),
        ("Tibia_and _Fibiula_right", "Tibia & Fibula"),
        ("Gastrocnemius lateral head A", "Gastrocnemius"),
        ("Calcaneus_right", "Calcaneus"),
        # --- Tail ---
        ("CA1", "Caudal vert. 1"),
    ],
}

LABEL_SETS["dorsal_skeleton"] = LABEL_SETS["lateral_skeleton"]
LABEL_SETS["dorsal_full"] = LABEL_SETS["lateral_full"]
LABEL_SETS["ventral_full"] = LABEL_SETS["lateral_full"]
LABEL_SETS["three_quarter_full"] = LABEL_SETS["lateral_full"]


def load_render(view, layers):
    basename = f"wholebody_{view}_{layers}"
    img_path = os.path.join(SUPP_DIR, f"{basename}.png")
    centroid_path = os.path.join(SUPP_DIR, f"{basename}_centroids.json")
    img = mpimg.imread(img_path)
    with open(centroid_path) as f:
        centroids = json.load(f)
    return img, centroids, basename


# Manual 3D centroid overrides for structures where automatic COM is off
# (e.g. eye: vertex distribution is non-uniform, visual center differs from COM)
CENTROID_3D_OVERRIDES = {
    # Left eye — use geometric center of bounding box for visual accuracy
    "mouse_skull_P1a.001": (0.004, -0.0172, 0.0847),
}


def split_and_sort_labels(labels_with_3d, centroids):
    """Split labels into left/right columns to avoid line crossings.

    Algorithm:
      1. Sort all labels by Z-axis (spine height: high Z = head, low Z = tail)
      2. Split by 2D X position: structures projecting left of the mouse
         midline → left column; right of midline → right column
      3. Each column is sorted by Z so labels descend head-to-tail,
         matching the top-to-bottom label order → no line crossings
      4. Balance the two columns to be equal (±1)

    Returns:
        (left_labels, right_labels) — each sorted by Z descending (head first)
    """
    # Find median 2D X position to split left vs right
    x_values = [item[2] for item in labels_with_3d]  # 2D pixel X
    median_x = np.median(x_values)

    left_group = []   # structures projecting left of center
    right_group = []  # structures projecting right of center

    for item in labels_with_3d:
        name, display, px, py, tissue, y3d, z3d = item
        if px <= median_x:
            left_group.append(item)
        else:
            right_group.append(item)

    # Balance: move items closest to the median X from larger to smaller group
    while abs(len(left_group) - len(right_group)) > 1:
        if len(left_group) > len(right_group):
            left_group.sort(key=lambda x: -x[2])  # sort by X desc, pick rightmost
            right_group.append(left_group.pop(0))
        else:
            right_group.sort(key=lambda x: x[2])   # sort by X asc, pick leftmost
            left_group.append(right_group.pop(0))

    # Sort each group by 2D Y position (screen top to bottom)
    # This is critical: label order must match dot order on screen to prevent crossings
    left_group.sort(key=lambda x: x[3])   # sort by py (2D screen Y, top=0)
    right_group.sort(key=lambda x: x[3])  # sort by py

    return left_group, right_group


def compute_label_positions(group, img_height, img_width, side,
                            margin_frac, top_frac=0.02, bottom_frac=0.98):
    """Compute evenly spaced label Y positions for a column.

    Labels are spaced evenly between top_frac and bottom_frac of image height.
    This guarantees uniform spacing and no overlaps.

    Returns:
        list of (name, display, struct_x, struct_y, label_x, label_y, tissue)
    """
    n = len(group)
    if n == 0:
        return []

    label_x = margin_frac * img_width
    top_y = top_frac * img_height
    bottom_y = bottom_frac * img_height

    # Evenly space labels
    if n == 1:
        ys = [(top_y + bottom_y) / 2]
    else:
        ys = [top_y + i * (bottom_y - top_y) / (n - 1) for i in range(n)]

    arranged = []
    for i, item in enumerate(group):
        name, display, px, py, tissue, y3d, z3d = item
        arranged.append((name, display, px, py, label_x, ys[i], tissue))

    return arranged


def draw_annotations(img, left_arranged, right_arranged, output_path,
                     img_width, img_height):
    """Draw leader lines and labels in medical textbook style.

    Page layout: 8.5 x 11 portrait
    - Mouse centered
    - Left column: right-aligned text, lines go right to structure
    - Right column: left-aligned text, lines go left to structure
    """
    # 8.5 x 11 at 400 dpi for high-res output
    dpi = 400
    page_w = 8.5
    page_h = 11.0

    fig, ax = plt.subplots(1, 1, figsize=(page_w, page_h), dpi=dpi)

    # Compute image placement — fill page vertically, center horizontally
    img_top = 0.97
    img_bottom = 0.03
    img_display_h = img_top - img_bottom

    # Width from aspect ratio
    img_aspect = img_width / img_height  # width/height
    img_display_w = img_display_h * img_aspect * (page_h / page_w)
    img_center_x = 0.50
    img_left = img_center_x - img_display_w / 2
    img_right = img_center_x + img_display_w / 2

    # Composite RGBA onto white background
    if img.shape[2] == 4:
        alpha = img[:, :, 3:4]
        rgb = img[:, :, :3]
        white = np.ones_like(rgb)
        img_composited = rgb * alpha + white * (1 - alpha)
    else:
        img_composited = img

    ax.imshow(img_composited, extent=[img_left, img_right, img_bottom, img_top],
              aspect="auto", zorder=0)
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    fig.subplots_adjust(left=0, right=1, top=1, bottom=0)

    font_size = 7.5
    line_color = "#555555"
    line_width = 0.3
    dot_size = 2.5
    # Minimum label gap in figure coords — must be enough for font height
    # At 7.5pt on 11in page, each label is ~7.5/72/11 ≈ 0.0095 of fig height
    min_label_gap = 0.016

    def px_to_fig(px, py):
        """Convert pixel coords to figure coords."""
        fx = img_left + (px / img_width) * img_display_w
        fy = img_top - (py / img_height) * img_display_h
        return fx, fy

    # Anatomy textbook style: simple straight lines from dot to label.
    # Labels are positioned to roughly follow the dot distribution (not
    # uniformly spaced), so lines are nearly horizontal and don't overlap.
    # Both dots and labels sorted by screen Y → no crossings.

    right_text_x = 0.97  # push labels to page edge
    left_text_x = 0.03

    def compute_label_ys(arranged, n, top, bottom):
        """Position labels to minimize line angles while preventing overlap.

        Uses iterative relaxation:
        - Each label is attracted to its dot's Y (to keep lines horizontal)
        - Labels repel each other to maintain minimum spacing
        - Labels are bounded within [bottom, top]

        After relaxation, labels stay in the same order as dots (sorted by
        screen Y), which guarantees no line crossings.
        """
        if n == 0:
            return []

        min_gap = max(min_label_gap, (top - bottom) / (n * 1.1))

        # Ideal positions = dot Y values in figure coords
        ideal_ys = []
        for item in arranged:
            _, _, sx, sy, _, _, _ = item
            _, fy = px_to_fig(sx, sy)
            ideal_ys.append(fy)

        if n == 1:
            return [max(bottom, min(top, ideal_ys[0]))]

        # Initialize labels at ideal positions
        label_ys = list(ideal_ys)

        # Iterative relaxation (50 passes)
        for iteration in range(50):
            new_ys = list(label_ys)

            for i in range(n):
                # Attraction toward ideal position (dot Y)
                attract = 0.3 * (ideal_ys[i] - label_ys[i])

                # Repulsion from neighbors
                repel = 0.0
                if i > 0:
                    gap = label_ys[i-1] - label_ys[i]  # should be positive
                    if gap < min_gap:
                        repel -= 0.4 * (min_gap - gap)  # push down
                if i < n - 1:
                    gap = label_ys[i] - label_ys[i+1]  # should be positive
                    if gap < min_gap:
                        repel += 0.4 * (min_gap - gap)  # push up

                new_ys[i] = label_ys[i] + attract + repel

            label_ys = new_ys

        # Final hard enforcement of minimum spacing (top to bottom)
        for i in range(1, n):
            if label_ys[i] > label_ys[i-1] - min_gap:
                label_ys[i] = label_ys[i-1] - min_gap
        for i in range(n-2, -1, -1):
            if label_ys[i] < label_ys[i+1] + min_gap:
                label_ys[i] = label_ys[i+1] + min_gap

        # Clamp
        for i in range(n):
            label_ys[i] = max(bottom, min(top, label_ys[i]))

        return label_ys

    def segments_cross(ax1, ay1, bx1, by1, ax2, ay2, bx2, by2):
        """Test if line segment (a1→b1) crosses segment (a2→b2)."""
        def ccw(px, py, qx, qy, rx, ry):
            return (rx - px) * (qy - py) - (qx - px) * (ry - py)
        d1 = ccw(ax1, ay1, bx1, by1, ax2, ay2)
        d2 = ccw(ax1, ay1, bx1, by1, bx2, by2)
        d3 = ccw(ax2, ay2, bx2, by2, ax1, ay1)
        d4 = ccw(ax2, ay2, bx2, by2, bx1, by1)
        if ((d1 > 0 and d2 < 0) or (d1 < 0 and d2 > 0)) and \
           ((d3 > 0 and d4 < 0) or (d3 < 0 and d4 > 0)):
            return True
        return False

    def uncross_lines(arranged, label_ys, side):
        """Iteratively swap label positions to eliminate line crossings.

        For each pair of lines that cross, swapping their label Y positions
        uncrosses them (and can't create new crossings between that pair).
        Repeat until no crossings remain.
        """
        n = len(arranged)
        if n < 2:
            return label_ys

        text_x = right_text_x if side == "right" else left_text_x
        line_end_x = (text_x - 0.005) if side == "right" else (text_x + 0.005)

        label_ys = list(label_ys)
        max_iterations = n * n

        total_swaps = 0
        for iteration in range(max_iterations):
            swapped = False
            for i in range(n):
                for j in range(i + 1, n):
                    fx_i, fy_i = px_to_fig(arranged[i][2], arranged[i][3])
                    fx_j, fy_j = px_to_fig(arranged[j][2], arranged[j][3])

                    if segments_cross(fx_i, fy_i, line_end_x, label_ys[i],
                                      fx_j, fy_j, line_end_x, label_ys[j]):
                        label_ys[i], label_ys[j] = label_ys[j], label_ys[i]
                        arranged[i], arranged[j] = arranged[j], arranged[i]
                        swapped = True
                        total_swaps += 1
            if not swapped:
                break

        # Second pass: for any remaining crossings, try sorting labels by
        # the dot's X coordinate relative to the line_end_x. This ensures
        # labels whose dots are further from the margin get positions that
        # prevent crossings with closer dots.
        def count_crossings(arr, lys):
            count = 0
            for ii in range(len(arr)):
                for jj in range(ii + 1, len(arr)):
                    fxi, fyi = px_to_fig(arr[ii][2], arr[ii][3])
                    fxj, fyj = px_to_fig(arr[jj][2], arr[jj][3])
                    if segments_cross(fxi, fyi, line_end_x, lys[ii],
                                      fxj, fyj, line_end_x, lys[jj]):
                        count += 1
            return count

        # Try re-sorting by different criteria to minimize crossings
        best_crossings = count_crossings(arranged, label_ys)
        best_order = list(range(n))

        # Strategy: sort labels to match the dot Y order at the line_end_x
        # This is the key insight — if we assign label positions such that
        # the label order matches the order dots would be in at x=line_end_x,
        # lines can't cross.
        dot_figs = [px_to_fig(arranged[i][2], arranged[i][3]) for i in range(n)]

        # For each dot, compute where its line to line_end_x would be at x=line_end_x
        # That's just the label_y itself, but we want to sort by dot Y
        # Sort labels by dot Y (fig coords) — this should give zero crossings
        # if all lines go to the same X
        order_by_fy = sorted(range(n), key=lambda i: -dot_figs[i][1])
        sorted_label_ys = sorted(label_ys, reverse=True)

        test_arranged = [arranged[i] for i in order_by_fy]
        test_crossings = count_crossings(test_arranged, sorted_label_ys)

        if test_crossings < best_crossings:
            arranged[:] = test_arranged
            label_ys[:] = sorted_label_ys
            total_swaps += 1

        # Final verification
        remaining = 0
        for i in range(n):
            for j in range(i + 1, n):
                fx_i, fy_i = px_to_fig(arranged[i][2], arranged[i][3])
                fx_j, fy_j = px_to_fig(arranged[j][2], arranged[j][3])
                if segments_cross(fx_i, fy_i, line_end_x, label_ys[i],
                                  fx_j, fy_j, line_end_x, label_ys[j]):
                    remaining += 1

        print(f"    {side}: {total_swaps} swaps/nudges, {remaining} crossings remain")

        return label_ys

    def draw_column(arranged, n, side):
        """Draw straight lines from dots to labels with zero crossings.

        Label Y positions are assigned to match dot-Y sort order. Then
        iteratively swap any crossing pairs until resolved.
        """
        if n == 0:
            return
        text_x = right_text_x if side == "right" else left_text_x
        text_ha = "left" if side == "right" else "right"
        line_end_x = (text_x - 0.005) if side == "right" else (text_x + 0.005)

        label_ys = compute_label_ys(arranged, n,
                                     img_top - 0.005, img_bottom + 0.005)

        # Assign label Y positions to match dot-Y order
        dot_fys = [px_to_fig(arranged[i][2], arranged[i][3])[1] for i in range(n)]
        dot_order = sorted(range(n), key=lambda i: -dot_fys[i])
        label_sorted = sorted(label_ys, reverse=True)
        final_label_ys = [0.0] * n
        for rank, idx in enumerate(dot_order):
            final_label_ys[idx] = label_sorted[rank]

        # Iteratively swap any crossing pairs
        dot_figs = [px_to_fig(arranged[i][2], arranged[i][3]) for i in range(n)]
        for iteration in range(n * n):
            swapped = False
            for i in range(n):
                for j in range(i + 1, n):
                    if segments_cross(dot_figs[i][0], dot_figs[i][1],
                                      line_end_x, final_label_ys[i],
                                      dot_figs[j][0], dot_figs[j][1],
                                      line_end_x, final_label_ys[j]):
                        final_label_ys[i], final_label_ys[j] = \
                            final_label_ys[j], final_label_ys[i]
                        arranged[i], arranged[j] = arranged[j], arranged[i]
                        dot_figs[i], dot_figs[j] = dot_figs[j], dot_figs[i]
                        swapped = True
            if not swapped:
                break

        # For remaining crossings, find the involved lines and brute-force
        # the best permutation of their label positions
        def count_all_crossings():
            c = 0
            for ii in range(n):
                for jj in range(ii + 1, n):
                    if segments_cross(dot_figs[ii][0], dot_figs[ii][1],
                                      line_end_x, final_label_ys[ii],
                                      dot_figs[jj][0], dot_figs[jj][1],
                                      line_end_x, final_label_ys[jj]):
                        c += 1
            return c

        crossings = count_all_crossings()
        if crossings > 0:
            # Find indices involved in crossings
            involved = set()
            for i in range(n):
                for j in range(i + 1, n):
                    if segments_cross(dot_figs[i][0], dot_figs[i][1],
                                      line_end_x, final_label_ys[i],
                                      dot_figs[j][0], dot_figs[j][1],
                                      line_end_x, final_label_ys[j]):
                        involved.add(i)
                        involved.add(j)
            involved = sorted(involved)

            if len(involved) <= 8:  # brute-force permutations
                from itertools import permutations
                involved_ys = [final_label_ys[i] for i in involved]
                best_crossings = crossings
                best_perm = list(range(len(involved)))

                for perm in permutations(range(len(involved))):
                    for k, idx in enumerate(involved):
                        final_label_ys[idx] = involved_ys[perm[k]]
                    c = count_all_crossings()
                    if c < best_crossings:
                        best_crossings = c
                        best_perm = list(perm)
                    if c == 0:
                        break

                # Apply best permutation
                for k, idx in enumerate(involved):
                    final_label_ys[idx] = involved_ys[best_perm[k]]

                # Also swap arranged entries to match
                involved_items = [arranged[i] for i in involved]
                involved_dots = [dot_figs[i] for i in involved]
                for k, idx in enumerate(involved):
                    arranged[idx] = involved_items[best_perm[k]]
                    dot_figs[idx] = involved_dots[best_perm[k]]

                crossings = count_all_crossings()

        print(f"    {side}: {crossings} crossings")

        # Draw
        for i, (name, display, sx, sy, lx, ly, tissue) in enumerate(arranged):
            color = TISSUE_LABEL_COLORS.get(tissue, "#888888")
            fx, fy = dot_figs[i]
            label_y = final_label_ys[i]

            ax.plot(fx, fy, "o", color=color, markersize=dot_size,
                    markeredgecolor="#333", markeredgewidth=0.2, zorder=5)

            ax.plot([fx, line_end_x], [fy, label_y], "-",
                    color=line_color, linewidth=line_width, zorder=2)

            ax.text(text_x, label_y, display,
                    fontsize=font_size, fontfamily="serif", fontstyle="italic",
                    va="center", ha=text_ha, color="#222222", zorder=6)

    n_right = len(right_arranged)
    n_left = len(left_arranged)
    draw_column(right_arranged, n_right, "right")
    draw_column(left_arranged, n_left, "left")

    fig.savefig(output_path, dpi=dpi, bbox_inches="tight", pad_inches=0.1,
                facecolor="white")
    plt.close(fig)
    print(f"  Annotated: {output_path}")
    print(f"  Left labels: {n_left}, Right labels: {n_right}")


def annotate(view="lateral", layers="full"):
    """Main annotation pipeline."""
    img, centroids, basename = load_render(view, layers)
    img_height, img_width = img.shape[:2]

    label_key = f"{view}_{layers}"
    label_set = LABEL_SETS.get(label_key, LABEL_SETS.get(f"lateral_{layers}", []))

    # Match labels to centroids, keeping 3D coordinates for sorting
    labels_with_3d = []
    missing = []
    for mesh_name, display_label in label_set:
        if mesh_name in centroids:
            c = centroids[mesh_name]
            px, py = c["pos_2d"]
            tissue = c["tissue_type"]
            x3d, y3d, z3d = c["pos_3d"]
            labels_with_3d.append((mesh_name, display_label, px, py, tissue,
                                   y3d, z3d))
        else:
            missing.append(mesh_name)

    if missing:
        print(f"  Missing from view: {missing}")

    print(f"  Labeling {len(labels_with_3d)} structures")

    # Split by Y-axis (dorsal/ventral), sort by Z-axis (head-to-tail)
    left_group, right_group = split_and_sort_labels(labels_with_3d, centroids)

    # Compute pixel positions for labels (not used for final layout, but needed
    # for the arranged tuple format)
    left_arranged = compute_label_positions(left_group, img_height, img_width,
                                            "left", 0.10)
    right_arranged = compute_label_positions(right_group, img_height, img_width,
                                             "right", 0.60)

    # Draw on 8.5x11 page
    output_path = os.path.join(SUPP_DIR, f"{basename}_labeled.png")
    draw_annotations(img, left_arranged, right_arranged, output_path,
                     img_width, img_height)

    return output_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--view", default="lateral")
    parser.add_argument("--layers", default="full")
    args = parser.parse_args()

    annotate(args.view, args.layers)
