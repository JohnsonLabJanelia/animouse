"""
Blender version compatibility layer.

Handles API differences between Blender 4.1+ and 5.0+.
Import this module and use its helpers instead of hard-coding version-specific values.
"""

import bpy

BLENDER_VERSION = bpy.app.version  # e.g. (5, 0, 1) or (4, 1, 0)


def eevee_engine_name():
    """Return the correct EEVEE engine identifier for this Blender version."""
    # In Blender 4.2+, EEVEE was renamed to BLENDER_EEVEE_NEXT during development,
    # then back to BLENDER_EEVEE in the final release. Check what's available.
    valid = bpy.types.RenderSettings.bl_rna.properties["engine"].enum_items.keys()
    if "BLENDER_EEVEE" in valid:
        return "BLENDER_EEVEE"
    if "BLENDER_EEVEE_NEXT" in valid:
        return "BLENDER_EEVEE_NEXT"
    return "BLENDER_EEVEE"


def principled_specular_input():
    """Return the correct Principled BSDF specular input name.

    Blender 4.0+ renamed 'Specular' to 'Specular IOR Level'.
    """
    if BLENDER_VERSION >= (4, 0, 0):
        return "Specular IOR Level"
    return "Specular"


def principled_subsurface_input():
    """Return the correct Principled BSDF subsurface input name.

    Blender 4.0+ renamed 'Subsurface' to 'Subsurface Weight'.
    """
    if BLENDER_VERSION >= (4, 0, 0):
        return "Subsurface Weight"
    return "Subsurface"


def check_min_version(major, minor, patch=0):
    """Return True if running Blender >= the specified version."""
    return BLENDER_VERSION >= (major, minor, patch)


def version_string():
    """Return Blender version as a readable string."""
    return f"{BLENDER_VERSION[0]}.{BLENDER_VERSION[1]}.{BLENDER_VERSION[2]}"
