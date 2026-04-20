"""Post-process mesh_inventory.csv to add named/unnamed flags and display names.

Reads `inspection/mesh_inventory.csv`, writes `inspection/mesh_inventory_flagged.csv`
with two added columns:

    needs_identification : bool  — mesh uses the 'Muscles to ID' material
    display_name         : str   — human-readable name with '*' suffix if needs_identification

The '*' convention is used in figure captions and supplementary tables so readers
can see which muscle meshes are anatomically assigned vs. still under review.

No Blender required — pure CSV.

Usage:
    python3 scripts/flag_mesh_inventory.py [INPUT_CSV]
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

DEFAULT_INPUT = Path(
    "/Users/johnsonr/anibodymouse/claude_mouse_unknown_muscles/inspection/mesh_inventory.csv"
)

UNNAMED_MATERIAL = "Muscles to ID"


def display_name(raw_name: str, needs_id: bool) -> str:
    """Strip _right/_left suffixes and trailing numeric suffixes (.001, etc.)
    for human-readable display; append '*' if needs anatomical identification."""
    name = raw_name
    # Drop trailing Blender duplicate suffixes like ".001".
    while "." in name and name.rsplit(".", 1)[-1].isdigit():
        name = name.rsplit(".", 1)[0]
    # Keep _right/_left explicit; they're biologically meaningful.
    return f"{name}*" if needs_id else name


def main(input_path: Path):
    rows = list(csv.DictReader(input_path.open()))
    if not rows:
        print("input is empty")
        return
    fieldnames = list(rows[0].keys()) + ["needs_identification", "display_name"]
    out_path = input_path.with_name(input_path.stem + "_flagged.csv")
    n_flagged = 0
    with out_path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            flagged = r.get("material", "") == UNNAMED_MATERIAL
            n_flagged += flagged
            r["needs_identification"] = "true" if flagged else "false"
            r["display_name"] = display_name(r["name"], flagged)
            # Promote to tissue="muscle" so quantitative counts include them.
            # They're already anatomically muscles — they just lack a named
            # assignment yet.
            if flagged and r.get("tissue", "") == "unknown":
                r["tissue"] = "muscle"
            # Promote incisors (which use a non-mapped "incisors" material)
            # into the bone tissue class so they get the gray-bone palette.
            if r.get("material", "") == "incisors" and r.get("tissue", "") == "unknown":
                r["tissue"] = "bone"
            w.writerow(r)
    print(f"wrote {out_path}  ({len(rows)} rows, {n_flagged} flagged *)")


if __name__ == "__main__":
    inp = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_INPUT
    main(inp)
