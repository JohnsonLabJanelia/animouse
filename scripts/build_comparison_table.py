"""Build Main Table 1: prior-work atlas comparison.

Reads our atlas numbers from the canonical catalogue CSV (which reflects the
midline + right-side deduplicated anatomical count), combines them with
hand-curated comparator data (from the literature-verification pass), and
emits:
  tables/main_table1_comparison.csv
  tables/main_table1_comparison.md
  tables/main_table1_comparison.tex

Usage:
    python3 scripts/build_comparison_table.py \\
        --catalogue ~/anibodymouse/claude_mouse_unknown_muscles/inspection/mesh_inventory_flagged_canonical.csv \\
        --out       ~/anibodymouse/claude_mouse_unknown_muscles/figures/tables
"""
from __future__ import annotations

import argparse
import csv
from pathlib import Path


# Comparator rows with values verified against the source papers
# (literature-verification pass 2026-04-19). Gaps marked "—" where the primary
# text did not itemise the quantity.
COMPARATORS = [
    {
        "work": "**This work (AniMouse)**",
        # Numeric fields are populated from the canonical catalogue at run
        # time by `load_ours`; defaults here are only used if the catalogue
        # isn't passed.
        "scope": "Whole body",
        "bones": "—",
        "muscles_named": "—",
        "muscles_flagged": "—",
        "tendons": "—",
        "organs": True,
        "imaging": "PTA-perfusion microCT",
        "resolution": "sub-fiber (4×)",
        "year": 2026,
        "source_released": "Stills + CSV + bones STL",
        "citation": "this study",
    },
    {
        "work": "Tata Ramalingasetty et al.",
        "scope": "Whole body",
        "bones": 108,
        "muscles_named": 59,          # 17 forelimb + 42 hindlimb
        "muscles_flagged": 0,
        "tendons": "Hill (embedded)",
        "organs": False,
        "imaging": "literature + MRI",
        "resolution": "n/a (no new imaging)",
        "year": 2021,
        "source_released": "Yes (MuJoCo, CC BY)",
        "citation": "IEEE Access, 2021",
    },
    {
        "work": "Charles et al.",
        "scope": "Hindlimb",
        "bones": "—",
        "muscles_named": 39,
        "muscles_flagged": 0,
        "tendons": "Hill (embedded)",
        "organs": False,
        "imaging": "I2KI-contrast microCT",
        "resolution": "12.96 µm iso.",
        "year": 2016,
        "source_released": "3D PDF only",
        "citation": "PLoS ONE, 2016",
    },
    {
        "work": "Gilmer et al.",
        "scope": "Proximal forelimb",
        "bones": 5,                    # humerus, radius, ulna, scapula, clavicle
        "muscles_named": 21,
        "muscles_flagged": 0,
        "tendons": "Rigid Hill",
        "organs": False,
        "imaging": "light-sheet (mesoSPIM)",
        "resolution": "8.23 µm XY / 5 µm Z",
        "year": 2024,
        "source_released": "Yes (SimTK, MIT)",
        "citation": "bioRxiv 2024 / J. Neurophysiol. 2025",
    },
    {
        "work": "DeWolf et al. (MausSpAun)",
        "scope": "Forelimb",
        "bones": "—",
        "muscles_named": 50,
        "muscles_flagged": 0,
        "tendons": "—",
        "organs": False,
        "imaging": "microCT (+MRI insertions)",
        "resolution": "—",
        "year": 2024,
        "source_released": "Partial / lab-branded",
        "citation": "bioRxiv 2024.09.11",
    },
    {
        "work": "DeLaurier et al.",
        "scope": "E14.5 limbs",
        "bones": "—",
        "muscles_named": ">60",       # aggregate across muscles+tendons+bones per side
        "muscles_flagged": 0,
        "tendons": "included",
        "organs": False,
        "imaging": "OPT + HREM",
        "resolution": "~13 µm iso.",
        "year": 2008,
        "source_released": "Interactive viewer only",
        "citation": "BMC Dev. Biol., 2008",
    },
    {
        "work": "Lobato-Rios et al. (NeuroMechFly)",
        "scope": "Whole body (fly)",
        "bones": "65 segments",
        "muscles_named": "42 DOF actuators",
        "muscles_flagged": 0,
        "tendons": "—",
        "organs": False,
        "imaging": "X-ray microCT",
        "resolution": "—",
        "year": 2022,
        "source_released": "Yes (GitHub)",
        "citation": "Nat. Methods, 2022",
    },
]


def load_ours(catalogue_path: Path):
    """Pull our numbers from the canonical catalogue CSV.

    Counts one row per anatomical structure (midline + right-side
    representatives), so the numbers align with how comparator atlases
    report muscle / bone counts.
    """
    ours = dict(COMPARATORS[0])
    if not catalogue_path or not catalogue_path.exists():
        return ours
    rows = list(csv.DictReader(catalogue_path.open()))
    muscles = [r for r in rows if r["tissue"] == "muscle"]
    named = [r for r in muscles if r.get("needs_identification", "false") != "true"]
    flagged = [r for r in muscles if r.get("needs_identification", "false") == "true"]
    ours["bones"] = sum(1 for r in rows if r["tissue"] == "bone")
    ours["muscles_named"] = len(named)
    ours["muscles_flagged"] = len(flagged)
    ours["tendons"] = sum(1 for r in rows if r["tissue"] == "tendon/ligament")
    return ours


def render_markdown(rows):
    header = ("| Work | Scope | Bones | Muscles (named + flagged*) | Tendons / Ligaments | "
              "Organs | Imaging | Resolution | Year | Released | Citation |")
    sep = "|---" * 11 + "|"
    lines = [header, sep]
    for r in rows:
        m_str = f"{r['muscles_named']}"
        if r["muscles_flagged"]:
            m_str += f" (+{r['muscles_flagged']} *under review*)"
        organs = "✓" if r["organs"] else "—"
        lines.append("| " + " | ".join([
            str(r["work"]), str(r["scope"]), str(r["bones"]), m_str,
            str(r["tendons"]), organs, str(r["imaging"]),
            str(r["resolution"]), str(r["year"]),
            str(r["source_released"]), str(r["citation"]),
        ]) + " |")
    return "\n".join(lines) + "\n"


def render_latex(rows):
    out = [
        r"\begin{table}[t]",
        r"\caption{Comparison of published rodent musculoskeletal atlases. "
        r"* indicates muscle meshes segmented but still under anatomical "
        r"identification; final named counts will be updated on revision.}",
        r"\label{tab:atlas-comparison}",
        r"\small",
        r"\begin{tabular}{lllrrrlll}",
        r"\toprule",
        r"Work & Scope & Bones & Muscles & Tendons & Organs & Imaging & Year & Released \\",
        r"\midrule",
    ]
    for r in rows:
        m_str = str(r["muscles_named"])
        if r["muscles_flagged"]:
            m_str += f" (+{r['muscles_flagged']}*)"
        organs = r"$\checkmark$" if r["organs"] else "—"
        out.append(" & ".join([
            str(r["work"]).replace("**", ""),
            str(r["scope"]), str(r["bones"]), m_str, str(r["tendons"]),
            organs, str(r["imaging"]), str(r["year"]),
            str(r["source_released"]),
        ]) + r" \\")
    out += [r"\bottomrule", r"\end{tabular}", r"\end{table}"]
    return "\n".join(out) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--catalogue", type=Path, default=None,
                    help="Canonical catalogue CSV (mesh_inventory_flagged_canonical.csv). "
                         "Numbers for 'this work' are derived from it.")
    ap.add_argument("--summary", type=Path, default=None,
                    help="(Deprecated; kept for backward compat — use --catalogue.)")
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    rows = COMPARATORS.copy()
    rows[0] = load_ours(args.catalogue) if args.catalogue else rows[0]

    # CSV
    csv_path = args.out / "main_table1_comparison.csv"
    with csv_path.open("w", newline="") as f:
        fieldnames = list(rows[0].keys())
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)
    print(f"  → {csv_path}")

    # Markdown
    md_path = args.out / "main_table1_comparison.md"
    md_path.write_text(
        "# Main Table 1 — Atlas comparison\n\n"
        + render_markdown(rows)
        + "\n*Entries marked \"—\" need literature verification.*\n"
    )
    print(f"  → {md_path}")

    # LaTeX
    tex_path = args.out / "main_table1_comparison.tex"
    tex_path.write_text(render_latex(rows))
    print(f"  → {tex_path}")


if __name__ == "__main__":
    main()
