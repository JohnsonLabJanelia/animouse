"""
Tissue type classification and color palette for the mouse biomechanical model.

Maps Blender material names to anatomical tissue types, and provides
a publication-quality color palette for rendering and visualization.
"""

# Material name -> tissue type mapping
# Based on the material names in claude_mouse.blend (Blender 4.1 format)
MATERIAL_TO_TISSUE = {
    # Bones
    "bone": "bone",
    "bone.001": "bone",
    "bone.003": "bone",
    "bone.005": "bone",
    # Cartilage
    "cartillage": "cartilage",  # note: typo in original model
    # Claws
    "claws": "claw",
    "claws.001": "claw",
    # Central nervous system
    "CNS": "central nervous system",
    # GI tract
    "gut": "gastrointestinal",
    # Kidneys
    "kidneys": "kidney",
    # Generic materials (identified by context)
    "Material": "vasculature",
    "Material.001": "cardiac",
    "Material.002": "connective tissue",
    "Material.004": "tongue",
    "Material.005": "connective tissue",
    # Muscles
    "muscle": "muscle",
    "MUSCLES": "muscle",
    "muscles 2.001": "muscle",
    "MUSCLES.001": "muscle",
    "38.001": "muscle",
    "38.002": "muscle",
    # Eyes
    "retina": "retina",
    "eye.001": "eye",
    # Tendons and ligaments
    "tendon2": "tendon/ligament",
    "tendon2.001": "tendon/ligament",
    "tendon2.002": "tendon/ligament",
    "tendon2.003": "tendon/ligament",
    "tendon2.004": "tendon/ligament",
    "tendon2.005": "tendon/ligament",
    "tendon2.006": "tendon/ligament",
    "tndon": "tendon/ligament",  # note: typo in original model
    # Urinary
    "urinary tract": "urinary",
    # Connective
    "Basic Surface": "connective tissue",
}

# Publication-quality color palette (RGBA, 0-1)
# Designed for clear tissue differentiation on both light and dark backgrounds
TISSUE_COLORS = {
    "bone":                   (0.92, 0.89, 0.82, 1.0),  # warm ivory
    "cartilage":              (0.65, 0.82, 0.92, 1.0),  # light blue
    "muscle":                 (0.75, 0.20, 0.20, 1.0),  # deep red
    "tendon/ligament":        (0.92, 0.82, 0.50, 1.0),  # gold
    "central nervous system": (0.72, 0.67, 0.82, 1.0),  # lavender
    "gastrointestinal":       (0.55, 0.72, 0.42, 1.0),  # olive green
    "kidney":                 (0.62, 0.28, 0.28, 1.0),  # dark red-brown
    "cardiac":                (0.82, 0.22, 0.32, 1.0),  # bright red
    "vasculature":            (0.52, 0.18, 0.22, 1.0),  # dark red
    "eye":                    (0.28, 0.28, 0.32, 1.0),  # dark gray
    "retina":                 (0.88, 0.72, 0.28, 1.0),  # amber
    "tongue":                 (0.82, 0.52, 0.52, 1.0),  # pink
    "urinary":                (0.82, 0.78, 0.48, 1.0),  # pale yellow
    "claw":                   (0.38, 0.32, 0.28, 1.0),  # dark brown
    "connective tissue":      (0.78, 0.72, 0.68, 1.0),  # warm gray
    "unknown":                (0.68, 0.68, 0.68, 1.0),  # neutral gray
}

# All known tissue types
TISSUE_TYPES = list(TISSUE_COLORS.keys())


def get_tissue_type(obj):
    """Determine tissue type from an object's material assignments.

    Args:
        obj: A Blender object (bpy.types.Object)

    Returns:
        str: tissue type name, or "unknown" if not classifiable
    """
    for slot in obj.material_slots:
        if slot.material and slot.material.name in MATERIAL_TO_TISSUE:
            return MATERIAL_TO_TISSUE[slot.material.name]
    return "unknown"


def get_tissue_color(tissue_type):
    """Get the RGBA color tuple for a tissue type.

    Args:
        tissue_type: str, one of TISSUE_TYPES

    Returns:
        tuple: (R, G, B, A) with values 0-1
    """
    return TISSUE_COLORS.get(tissue_type, TISSUE_COLORS["unknown"])


def get_laterality(obj_name):
    """Determine if an object is left, right, or midline from its name.

    Args:
        obj_name: str, the Blender object name

    Returns:
        str: "left", "right", or "midline"
    """
    name = obj_name.lower()
    if "_left" in name or " left" in name:
        return "left"
    if "_right" in name or " right" in name:
        return "right"
    return "midline"


def get_collection_path(obj):
    """Get the collection hierarchy path for an object.

    Args:
        obj: A Blender object

    Returns:
        str: collection path like "SKELETON > ARM > ARM BONES"
    """
    import bpy
    for col in bpy.data.collections:
        if obj.name in col.objects:
            chain = [col.name]
            for parent in bpy.data.collections:
                if col.name in [c.name for c in parent.children]:
                    chain.insert(0, parent.name)
                    for grandparent in bpy.data.collections:
                        if parent.name in [c.name for c in grandparent.children]:
                            chain.insert(0, grandparent.name)
            return " > ".join(chain)
    return "Scene"
