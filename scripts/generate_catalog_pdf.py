"""
Generate a PDF catalog table of all 583 mesh parts.

Usage:
    python3 scripts/generate_catalog_pdf.py

Reads mesh_catalog.json and rigging_info.json, renders into supplementary dir,
and produces a multi-page PDF table with thumbnails.
"""

import io
import json
import os

from PIL import Image as PILImage
from reportlab.lib import colors
from reportlab.lib.pagesizes import landscape, letter
from reportlab.lib.units import inch
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT

SUPP_DIR = os.path.expanduser("~/anibodymouse/claude_mouse/supplementary")
RENDER_DIR = os.path.join(SUPP_DIR, "renders")
CATALOG_JSON = os.path.join(SUPP_DIR, "mesh_catalog.json")
RIGGING_JSON = os.path.join(SUPP_DIR, "rigging_info.json")
OUTPUT_PDF = os.path.join(SUPP_DIR, "mesh_catalog.pdf")

# Tissue type colors (used only in the Tissue column cell)
TISSUE_COLORS = {
    "bone":                    colors.Color(0.85, 0.85, 0.75),
    "muscle":                  colors.Color(0.90, 0.75, 0.75),
    "tendon/ligament":         colors.Color(0.85, 0.85, 0.70),
    "connective tissue":       colors.Color(0.78, 0.85, 0.78),
    "cartilage":               colors.Color(0.75, 0.85, 0.92),
    "eye":                     colors.Color(0.80, 0.80, 0.92),
    "kidney":                  colors.Color(0.88, 0.75, 0.82),
    "retina":                  colors.Color(0.82, 0.75, 0.90),
    "central nervous system":  colors.Color(0.92, 0.85, 0.75),
    "gastrointestinal":        colors.Color(0.75, 0.90, 0.75),
    "tongue":                  colors.Color(0.92, 0.78, 0.78),
    "urinary":                 colors.Color(0.78, 0.92, 0.82),
    "cardiac":                 colors.Color(0.92, 0.75, 0.78),
    "vasculature":             colors.Color(0.85, 0.75, 0.85),
}

TISSUE_COL_INDEX = 2  # column index for tissue type


def load_data():
    with open(CATALOG_JSON) as f:
        catalog = json.load(f)
    with open(RIGGING_JSON) as f:
        rigging = json.load(f)
    return catalog, rigging


def cropped_thumbnail(img_path, display_w, display_h, crop_frac=0.15):
    """Load a PNG, crop top/bottom by crop_frac, return a reportlab Image."""
    pil_img = PILImage.open(img_path)
    w, h = pil_img.size
    top = int(h * crop_frac)
    bottom = int(h * (1 - crop_frac))
    pil_img = pil_img.crop((0, top, w, bottom))
    buf = io.BytesIO()
    pil_img.save(buf, format="PNG")
    buf.seek(0)
    return Image(buf, width=display_w, height=display_h)


def fmt_xyz(xyz):
    return f"({xyz[0]:.1f}, {xyz[1]:.1f}, {xyz[2]:.1f})"


def fmt_vol(v):
    if v >= 100:
        return f"{v:.0f}"
    elif v >= 1:
        return f"{v:.1f}"
    else:
        return f"{v:.3f}"


def fmt_sa(v):
    if v >= 100:
        return f"{v:.0f}"
    elif v >= 1:
        return f"{v:.1f}"
    else:
        return f"{v:.2f}"


def get_rigging_summary(name, rig_info):
    info = rig_info.get(name, {})
    if not info.get("is_rigged"):
        return ""
    # Prefer the muscle_rig description (origin→insertion, skeletal chain, IK)
    if info.get("muscle_rig"):
        return info["muscle_rig"]
    parts = []
    if info.get("parent"):
        parts.append(f"parent: {info['parent']}")
    if info.get("armature_modifier"):
        parts.append(f"mod: {info['armature_modifier']}")
    if info.get("vertex_groups"):
        vg = info["vertex_groups"]
        if len(vg) <= 2:
            parts.append(f"vgroups: {', '.join(vg)}")
        else:
            parts.append(f"vgroups: {', '.join(vg[:2])}+{len(vg)-2}")
    return "; ".join(parts)


def build_pdf(catalog, rigging):
    pagesize = landscape(letter)
    doc = SimpleDocTemplate(
        OUTPUT_PDF,
        pagesize=pagesize,
        leftMargin=0.3 * inch,
        rightMargin=0.3 * inch,
        topMargin=0.3 * inch,
        bottomMargin=0.3 * inch,
    )

    styles = getSampleStyleSheet()
    tiny = ParagraphStyle("tiny", parent=styles["Normal"], fontSize=5.5,
                          leading=6.5, wordWrap="CJK")
    tiny_bold = ParagraphStyle("tiny_bold", parent=tiny, fontName="Helvetica-Bold")
    tiny_right = ParagraphStyle("tiny_right", parent=tiny, alignment=TA_RIGHT)
    tiny_center = ParagraphStyle("tiny_center", parent=tiny, alignment=TA_CENTER)
    title_style = ParagraphStyle("title", parent=styles["Title"], fontSize=14)
    subtitle_style = ParagraphStyle("subtitle", parent=styles["Normal"],
                                     fontSize=9, textColor=colors.grey)

    catalog.sort(key=lambda r: (r["tissue_type"], r["name"]))

    col_widths = [
        0.38 * inch,   # thumbnail
        1.6 * inch,    # name
        0.75 * inch,   # tissue
        0.5 * inch,    # laterality
        1.15 * inch,   # location (x,y,z)
        0.55 * inch,   # volume
        0.55 * inch,   # surface area
        0.45 * inch,   # verts
        0.45 * inch,   # rigged
        3.1 * inch,    # connections
    ]

    # Header row
    header_style = ParagraphStyle("hdr", parent=tiny, fontName="Helvetica-Bold",
                                   textColor=colors.Color(0.3, 0.3, 0.3))
    header_center = ParagraphStyle("hdr_c", parent=header_style, alignment=TA_CENTER)

    header = [
        Paragraph("<b>Img</b>", header_center),
        Paragraph("<b>Name</b>", header_style),
        Paragraph("<b>Tissue</b>", header_style),
        Paragraph("<b>Side</b>", header_style),
        Paragraph("<b>Location (mm)</b>", header_style),
        Paragraph("<b>Vol (mm³)</b>", header_style),
        Paragraph("<b>SA (mm²)</b>", header_style),
        Paragraph("<b>Verts</b>", header_style),
        Paragraph("<b>Rigged</b>", header_center),
        Paragraph("<b>Connections</b>", header_style),
    ]

    # Thumbnail display size (cropped 15% top/bottom → 70% of original height)
    thumb_display_w = 0.32 * inch
    thumb_display_h = 0.22 * inch  # shorter due to crop

    all_rows = [header]
    row_tissues = [None]

    print("Building table rows...")
    for i, rec in enumerate(catalog):
        name = rec["name"]
        rig_summary = get_rigging_summary(name, rigging)
        is_rigged = rigging.get(name, {}).get("is_rigged", False)

        # Cropped thumbnail
        img_path = os.path.join(RENDER_DIR, f"{name}.png")
        if os.path.exists(img_path):
            try:
                thumb = cropped_thumbnail(img_path, thumb_display_w, thumb_display_h)
            except Exception:
                thumb = Paragraph("-", tiny_center)
        else:
            thumb = Paragraph("-", tiny_center)

        row = [
            thumb,
            Paragraph(name, tiny),
            Paragraph(rec["tissue_type"], tiny),
            Paragraph(rec["laterality"], tiny_center),
            Paragraph(fmt_xyz(rec["location_mm"]), tiny),
            Paragraph(fmt_vol(rec["volume_mm3"]), tiny_right),
            Paragraph(fmt_sa(rec["surface_area_mm2"]), tiny_right),
            Paragraph(f"{rec['vertices']:,}", tiny_right),
            Paragraph("Y" if is_rigged else "", tiny_center),
            Paragraph(rig_summary, tiny),
        ]
        all_rows.append(row)
        row_tissues.append(rec["tissue_type"])

        if (i + 1) % 100 == 0:
            print(f"  {i+1}/{len(catalog)} rows built")

    ROW_HEIGHT = 0.3 * inch
    HEADER_HEIGHT = 0.22 * inch

    row_heights = [HEADER_HEIGHT] + [ROW_HEIGHT] * (len(all_rows) - 1)

    print("Building table...")
    table = Table(all_rows, colWidths=col_widths, rowHeights=row_heights,
                  repeatRows=1)

    # Style: white background everywhere, color only in tissue column
    style_commands = [
        # White background for everything
        ("BACKGROUND", (0, 0), (-1, -1), colors.white),
        # Header styling — white bg, dark text, bottom border
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.Color(0.3, 0.3, 0.3)),
        ("LINEBELOW", (0, 0), (-1, 0), 0.75, colors.Color(0.6, 0.6, 0.6)),
        # General
        ("FONTSIZE", (0, 0), (-1, -1), 6),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (0, 0), (0, -1), "CENTER"),
        # Light grid
        ("GRID", (0, 0), (-1, -1), 0.25, colors.Color(0.88, 0.88, 0.88)),
        # Tight padding
        ("TOPPADDING", (0, 0), (-1, -1), 1),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
        ("LEFTPADDING", (0, 0), (-1, -1), 2),
        ("RIGHTPADDING", (0, 0), (-1, -1), 2),
    ]

    # Color only the Tissue column cells by tissue type
    for i, tissue in enumerate(row_tissues):
        if tissue and tissue in TISSUE_COLORS:
            style_commands.append(
                ("BACKGROUND", (TISSUE_COL_INDEX, i), (TISSUE_COL_INDEX, i),
                 TISSUE_COLORS[tissue])
            )

    table.setStyle(TableStyle(style_commands))

    # Build document
    elements = [
        Paragraph("AniMouse Mesh Catalog", title_style),
        Spacer(1, 4),
        Paragraph(
            f"{len(catalog)} meshes | "
            f"{sum(r['vertices'] for r in catalog):,} vertices | "
            f"{sum(r['volume_mm3'] for r in catalog):,.0f} mm³ total volume | "
            f"{sum(1 for r in catalog if rigging.get(r['name'], {}).get('is_rigged'))} rigged",
            subtitle_style
        ),
        Spacer(1, 6),
        table,
    ]

    print("Rendering PDF...")
    doc.build(elements)

    # Count actual pages
    import fitz
    pdf_doc = fitz.open(OUTPUT_PDF)
    actual_pages = pdf_doc.page_count
    pdf_doc.close()

    sz = os.path.getsize(OUTPUT_PDF)
    print(f"PDF saved: {OUTPUT_PDF}")
    print(f"Pages: {actual_pages}, Size: {sz/1e6:.1f} MB")


if __name__ == "__main__":
    catalog, rigging = load_data()
    build_pdf(catalog, rigging)
