# AniMouse

Blender tools for the [AniBody](https://github.com/janelia-anibody) mouse biomechanical model.

Built at [HHMI Janelia Research Campus](https://www.janelia.org), Johnson Lab.

## What This Does

AniMouse provides a Blender add-on and command-line scripts for working with the mouse musculoskeletal model:

- **Mesh catalog rendering** — render isolated thumbnails of every body part with tissue-type coloring and transparent backgrounds
- **Metadata extraction** — compute volume, surface area, bounding box, tissue type, and anatomical classification for all 583 meshes
- **Whole-body rendering** — multi-view renders of the complete model
- **Version compatibility** — works with Blender 4.1+ and 5.0+

## Quick Start

### As a Blender Add-on (recommended)

1. Open Blender
2. Go to **Edit > Preferences > Add-ons**
3. Click **Install from Disk** and select the `animouse/` folder
4. Enable "AniMouse" in the add-on list
5. In the 3D Viewport, press **N** to open the sidebar, find the **AniMouse** tab

### From the Scripting Tab

Open any script from `scripts/` in Blender's Scripting tab and run it with **Alt+P**.

### From the Command Line

```bash
# Render 8 test parts
blender --background model.blend --python scripts/batch_render.py

# Render all 583 meshes
blender --background model.blend --python scripts/batch_render.py -- --mode all

# Extract metadata
blender --background model.blend --python scripts/extract_catalog.py
```

## Requirements

- Blender 4.1+ or 5.0+
- No additional Python packages needed (uses Blender's bundled Python)

## Project Structure

```
animouse/           Blender add-on
  __init__.py       Add-on registration and UI panel
  compat.py         Blender version compatibility helpers
  tissue_types.py   Material-to-tissue mapping and color palette
  mesh_metadata.py  Geometric and anatomical metadata extraction
  render_catalog.py Isolated mesh rendering engine
scripts/            Standalone CLI scripts
  batch_render.py   Command-line batch rendering
  extract_catalog.py Command-line metadata extraction
data/               Shared data files
tests/              Validation scripts
```

## Related Projects

- [janelia-anibody](https://github.com/janelia-anibody) — AniBody project organization
- [janelia-anibody/fruitfly](https://github.com/janelia-anibody/fruitfly) — Virtual biomechanical fly
- [flybody](https://github.com/TuragaLab/flybody) — Whole-body fly simulation (Vaxenburg et al., Nature 2025)
- [mimic-mjx](https://mimic-mjx.talmolab.org/) — Imitation learning for biomechanical models
- [dm_control](https://github.com/google-deepmind/dm_control) — MuJoCo export pipeline

## License

BSD-3-Clause. See [LICENSE](LICENSE).
