# AniMouse — Blender Tools for Mouse Biomechanical Modeling

## Project Overview
Blender add-on and CLI scripts for building, validating, and exporting the AniBody mouse
biomechanical model. The model is built from microCT imaging, segmented in Paintera, and
rigged in Blender for export to MuJoCo.

## Repository Structure
```
animouse/              # Blender add-on (install via Preferences > Add-ons)
  __init__.py          # Add-on registration, bl_info
  panels.py            # UI panels (N-panel sidebar under "AniMouse" tab)
  operators.py         # Blender operators
  render_catalog.py    # Isolated mesh rendering for supplementary figures
  mesh_metadata.py     # Mesh metadata extraction (volume, SA, tissue type, etc.)
  tissue_types.py      # Tissue classification, material->tissue mapping, color palette
  compat.py            # Blender version compatibility helpers (4.1+ and 5.0+)
scripts/               # Standalone CLI scripts (blender --background --python)
data/                  # Shared data files (color palettes, nomenclature)
tests/                 # Validation scripts
```

## Blender Version Compatibility
- Target: Blender 4.1+ (Igor's version) and 5.0+ (Rob's version)
- The .blend file is in 4.1 format — do NOT re-save in 5.0 format until Igor upgrades
- Use `from . import compat` for version-dependent API calls (EEVEE name, node inputs)
- Test scripts on both versions when possible

## Key Conventions
- All measurements in the model are in Blender internal units (meters)
- Convert to mm for display/export: multiply by 1000
- Camera clip_start must be set to 0.001 (1mm) for rendering small objects
- Tissue type is determined from material name -> TISSUE_MAP lookup in tissue_types.py
- The add-on prefix is "animouse" — all operators use `animouse.` prefix
- Temporary Blender data created by scripts uses `_animouse_` prefix for easy cleanup

## Running Scripts
```bash
# CLI (headless)
blender --background model.blend --python scripts/batch_render.py

# In Blender Scripting tab
# Open any script from scripts/ and press Alt+P

# Add-on installation
# Preferences > Add-ons > Install > select animouse/ folder
# Or symlink: ln -s /path/to/animouse/animouse ~/.config/blender/5.0/scripts/addons/animouse
```

## Build & Test
No build step. Python only. Requires Blender's bundled Python (bpy).
```bash
# Run validation
blender --background model.blend --python tests/test_mesh_integrity.py
```
