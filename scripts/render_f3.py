"""Figure 3 renders — whole-body Blender atlas views.

Produces the panels for Figure 3 of the atlas preprint:
  - hero_three_quarter.png   (F3a, 3/4 dorsolateral)
  - lateral_right.png        (F3b, muscled side visible)
  - lateral_left.png         (F3b, bare-skeleton side visible)
  - dorsal.png               (F3b)
  - ventral.png              (F3b)
  - reveal_full.png          (F3c panel 1)
  - reveal_muscles.png       (F3c panel 2)
  - reveal_skeleton.png      (F3c panel 3)

Camera auto-fits to the scene bounding box so the script works on any blend
with the same orientation convention:
  +Z = rostral (head)     -Z = caudal (tail)
  +Y = dorsal             -Y = ventral
  +X = right (subject's)  -X = left

Usage:
    blender --background mouse2_20260419.blend \\
        --python scripts/render_f3.py -- [--quick] [--out DIR]

  --quick         Render at 1500 px (sanity check) instead of 4000 px.
  --out DIR       Override output directory.
  --views LIST    Comma-separated subset: hero,lateral_right,lateral_left,
                  dorsal,ventral,reveal_full,reveal_muscles,reveal_skeleton
"""
from __future__ import annotations

import json
import math
import os
import sys
from pathlib import Path

import bpy
import mathutils

# Make the animouse package importable.
ADDON_PARENT = "/Users/johnsonr/src/animouse"
if ADDON_PARENT not in sys.path:
    sys.path.insert(0, ADDON_PARENT)
from animouse.tissue_types import MATERIAL_TO_TISSUE, TISSUE_COLORS  # noqa: E402
from animouse.compat import eevee_engine_name  # noqa: E402


# Extend the tissue map to cover materials unique to mouse2_20260419.blend.
EXTRA_MATERIAL_MAP = {
    "Muscles to ID": "muscle",     # render as standard muscle red, flagged via "*" in tables
    "incisors": "bone",
    "rot axis ref": "unknown",
    "Dots Stroke": "unknown",
}

# Palette overrides for Figure 3: tuned against a white background, matching
# the look of Igor Siwanowicz's reference renders. Bones shift from ivory
# (invisible on white) to a neutral gray so the skeleton reveal panel reads.
PALETTE_OVERRIDES = {
    "bone":             (0.52, 0.52, 0.55, 1.0),
    "cartilage":        (0.55, 0.72, 0.86, 1.0),
    "tendon/ligament":  (0.88, 0.76, 0.38, 1.0),
    "kidney":           (0.52, 0.58, 0.38, 1.0),  # olive, matching Igor's organs
    "claw":             (0.32, 0.28, 0.24, 1.0),
}


# -------------------------------------------------------------------------
# Scene analysis
# -------------------------------------------------------------------------

def visible_mesh_bounds():
    """Return (center, extent) of the axis-aligned bbox over mesh objects."""
    mins = [float("inf")] * 3
    maxs = [float("-inf")] * 3
    for obj in bpy.data.objects:
        if obj.type != "MESH":
            continue
        for c in obj.bound_box:
            w = obj.matrix_world @ mathutils.Vector(c)
            for i in range(3):
                mins[i] = min(mins[i], w[i])
                maxs[i] = max(maxs[i], w[i])
    center = tuple((mins[i] + maxs[i]) / 2.0 for i in range(3))
    extent = tuple(maxs[i] - mins[i] for i in range(3))
    return center, extent


# -------------------------------------------------------------------------
# Material assignment (tissue palette)
# -------------------------------------------------------------------------

TISSUE_CACHE_KEY = "_animouse_tissue"


def tissue_type_for(obj):
    """Return the tissue type for an object, reading from a cached custom property
    if set (so layer filtering keeps working after we swap in the palette materials)."""
    cached = obj.get(TISSUE_CACHE_KEY)
    if cached:
        return cached
    for slot in obj.material_slots:
        if slot.material:
            name = slot.material.name
            if name in MATERIAL_TO_TISSUE:
                return MATERIAL_TO_TISSUE[name]
            if name in EXTRA_MATERIAL_MAP:
                return EXTRA_MATERIAL_MAP[name]
    return "unknown"


def cache_tissue_types():
    """Record the original-material tissue classification on every mesh object,
    before we overwrite materials with the palette."""
    for obj in bpy.data.objects:
        if obj.type != "MESH":
            continue
        obj[TISSUE_CACHE_KEY] = tissue_type_for(obj)


def build_tissue_materials():
    mats = {}
    for tissue, rgba in TISSUE_COLORS.items():
        rgba = PALETTE_OVERRIDES.get(tissue, rgba)
        name = f"_animouse_f3_{tissue}"
        mat = bpy.data.materials.get(name)
        if mat is None:
            mat = bpy.data.materials.new(name)
        mat.use_nodes = True
        nt = mat.node_tree
        nt.nodes.clear()
        bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
        bsdf.inputs["Base Color"].default_value = rgba
        bsdf.inputs["Roughness"].default_value = 0.55
        try:
            bsdf.inputs["Specular IOR Level"].default_value = 0.3
        except KeyError:
            pass
        out = nt.nodes.new("ShaderNodeOutputMaterial")
        nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
        mat.diffuse_color = rgba
        mats[tissue] = mat
    return mats


def apply_tissue_palette(mats):
    for obj in bpy.data.objects:
        if obj.type != "MESH":
            continue
        tissue = tissue_type_for(obj)
        mat = mats.get(tissue, mats["unknown"])
        if obj.data.materials:
            obj.data.materials[0] = mat
        else:
            obj.data.materials.append(mat)


# -------------------------------------------------------------------------
# Camera placement
# -------------------------------------------------------------------------

def setup_world_white():
    scene = bpy.context.scene
    # Always install a fresh world with a clean background graph to avoid any
    # leftover textures / output-link issues from the source file.
    fresh = bpy.data.worlds.new("_animouse_f3_world")
    scene.world = fresh
    fresh.use_nodes = True
    nt = fresh.node_tree
    nt.nodes.clear()
    bg = nt.nodes.new("ShaderNodeBackground")
    bg.inputs["Color"].default_value = (1.0, 1.0, 1.0, 1.0)
    bg.inputs["Strength"].default_value = 1.0
    out = nt.nodes.new("ShaderNodeOutputWorld")
    nt.links.new(bg.outputs["Background"], out.inputs["Surface"])


def setup_lighting():
    """Three-point studio lighting, stable across views."""
    presets = [
        ("Key",  (math.radians(45), math.radians(10),  math.radians(30)),  5.0),
        ("Fill", (math.radians(60), math.radians(-20), math.radians(-45)), 2.5),
        ("Rim",  (math.radians(30), 0.0,               math.radians(-150)), 3.0),
    ]
    for name, rot, energy in presets:
        key = f"_animouse_f3_{name}"
        ld = bpy.data.lights.get(key) or bpy.data.lights.new(key, "SUN")
        ld.energy = energy
        obj = bpy.data.objects.get(key)
        if obj is None:
            obj = bpy.data.objects.new(key, ld)
            bpy.context.scene.collection.objects.link(obj)
        obj.rotation_euler = rot


def fit_camera(view, center, extent, aspect):
    """Place a perspective camera framed on the body.

    All views use `up="Y"` which makes the camera's local Y-axis align with
    world +Z (Blender's global up). Since +Z is rostral in this model, HEAD
    reads UP in the image and the body appears VERTICAL in a portrait frame.
    body_w_m / body_h_m are the in-image horizontal and vertical physical
    extents respectively.
    """
    cx, cy, cz = center
    ex, ey, ez = extent
    pad = 1.08
    sensor_mm = 36.0

    # In this blend, subject's anatomical RIGHT = world -X (verified by muscle
    # centroid distribution). So to VIEW the right side, camera sits at -X.
    if view == "lateral_right":
        dir_vec = (-1.0, 0.0, 0.0); up = "Y"
        body_w_m, body_h_m = ey, ez
    elif view == "lateral_left":
        dir_vec = (1.0, 0.0, 0.0); up = "Y"
        body_w_m, body_h_m = ey, ez
    elif view == "dorsal":
        dir_vec = (0.0, 1.0, 0.0); up = "Y"
        body_w_m, body_h_m = ex, ez
    elif view == "ventral":
        dir_vec = (0.0, -1.0, 0.0); up = "Y"
        body_w_m, body_h_m = ex, ez
    elif view == "hero":
        dir_vec = (0.65, 0.45, 0.20); up = "Y"
        body_w_m = max(ex, ey, ez)
        body_h_m = max(ex, ey, ez)
    else:
        raise ValueError(f"unknown view: {view}")

    lens_mm = 120.0 if view != "hero" else 85.0
    fov_w = 2 * math.atan((sensor_mm / 2) / lens_mm)
    fov_v = 2 * math.atan((sensor_mm / aspect / 2) / lens_mm)
    dist_w = (body_w_m * pad) / (2 * math.tan(fov_w / 2))
    dist_h = (body_h_m * pad) / (2 * math.tan(fov_v / 2))
    dist = max(dist_w, dist_h)

    dv = mathutils.Vector(dir_vec).normalized()
    loc = (cx + dv.x * dist, cy + dv.y * dist, cz + dv.z * dist)

    cam = bpy.data.cameras.get("_animouse_f3_cam") or bpy.data.cameras.new("_animouse_f3_cam")
    cam.type = "PERSP"
    cam.lens = lens_mm
    cam.sensor_width = sensor_mm
    cam.sensor_fit = "HORIZONTAL"
    cam.clip_start = 0.001
    cam.clip_end = 100.0

    cam_obj = bpy.data.objects.get("_animouse_f3_cam")
    if cam_obj is None:
        cam_obj = bpy.data.objects.new("_animouse_f3_cam", cam)
        bpy.context.scene.collection.objects.link(cam_obj)
    cam_obj.data = cam
    cam_obj.location = mathutils.Vector(loc)
    direction = mathutils.Vector(center) - cam_obj.location
    cam_obj.rotation_euler = direction.to_track_quat("-Z", up).to_euler()
    bpy.context.scene.camera = cam_obj

    print(f"    cam[{view}]  loc={tuple(round(v, 3) for v in loc)}  "
          f"lens={lens_mm}mm  dist={dist:.3f}m  "
          f"body={body_w_m*1000:.0f}x{body_h_m*1000:.0f}mm  aspect={aspect}")
    return cam_obj


# -------------------------------------------------------------------------
# Layer (visibility) modes
# -------------------------------------------------------------------------

TISSUE_FAMILIES = {
    "full": None,
    "muscles": {"muscle", "tendon/ligament"},
    "skeleton": {"bone", "cartilage"},
}


def apply_layer_visibility(mode):
    allowed = TISSUE_FAMILIES[mode]
    for obj in bpy.data.objects:
        if obj.type != "MESH":
            continue
        if allowed is None:
            obj.hide_render = False
            continue
        obj.hide_render = tissue_type_for(obj) not in allowed


# -------------------------------------------------------------------------
# Render
# -------------------------------------------------------------------------

def setup_render_settings(res_px, aspect):
    scene = bpy.context.scene
    scene.render.engine = eevee_engine_name()
    if aspect >= 1.0:
        scene.render.resolution_x = int(res_px)
        scene.render.resolution_y = int(res_px / aspect)
    else:
        scene.render.resolution_y = int(res_px)
        scene.render.resolution_x = int(res_px * aspect)
    scene.render.resolution_percentage = 100
    scene.render.film_transparent = False
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"
    scene.render.image_settings.compression = 15
    try:
        scene.eevee.taa_render_samples = 128
    except AttributeError:
        pass
    # Ambient occlusion for crevice/depth cues — critical for reading a skeleton
    # against a white background (ivory bone has almost no tonal separation from
    # white without AO).
    for flag in ("use_gtao", "use_ambient_occlusion", "use_ssao"):
        try:
            setattr(scene.eevee, flag, True)
        except AttributeError:
            pass
    for attr, val in (("gtao_distance", 0.02), ("gtao_factor", 1.5),
                      ("gtao_quality", 0.5)):
        try:
            setattr(scene.eevee, attr, val)
        except AttributeError:
            pass
    # Force Standard view transform so whites read as white.
    try:
        scene.view_settings.view_transform = "Standard"
        scene.view_settings.look = "None"
        scene.view_settings.exposure = 0.0
        scene.view_settings.gamma = 1.0
    except Exception as e:
        print(f"    (view-transform setup warning: {e})")


def render_view(label, camera_view, layer_mode, center, extent, out_dir, res_px, aspect):
    print(f"\n>>> {label}  (camera={camera_view}, layers={layer_mode})")
    apply_layer_visibility(layer_mode)
    fit_camera(camera_view, center, extent, aspect)
    setup_render_settings(res_px, aspect)
    path = out_dir / f"{label}.png"
    bpy.context.scene.render.filepath = str(path)
    bpy.ops.render.render(write_still=True)
    print(f"    → {path}")
    return path


# -------------------------------------------------------------------------
# Main
# -------------------------------------------------------------------------

# (label, camera_view, layer_mode, aspect)
# aspect = width/height. Body is vertical (head up), so portrait aspect.
VIEWS = [
    ("hero_three_quarter", "hero",          "full",     1.0),
    ("lateral_right",      "lateral_right", "full",     0.22),
    ("lateral_left",       "lateral_left",  "full",     0.22),
    ("dorsal",             "dorsal",        "full",     0.22),
    ("ventral",            "ventral",       "full",     0.22),
    ("reveal_full",        "lateral_right", "full",     0.22),
    ("reveal_muscles",     "lateral_right", "muscles",  0.22),
    ("reveal_skeleton",    "lateral_right", "skeleton", 0.22),
]


def parse_argv():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    quick = "--quick" in argv
    out_override = None
    views_filter = None
    i = 0
    while i < len(argv):
        if argv[i] == "--out" and i + 1 < len(argv):
            out_override = Path(argv[i + 1])
            i += 2
        elif argv[i] == "--views" and i + 1 < len(argv):
            views_filter = set(argv[i + 1].split(","))
            i += 2
        else:
            i += 1
    return quick, out_override, views_filter


def main():
    quick, out_override, views_filter = parse_argv()
    res_px = 1500 if quick else 4000

    blend_dir = Path(bpy.data.filepath).parent
    out_dir = out_override or (blend_dir / "figures" / "f3")
    out_dir.mkdir(parents=True, exist_ok=True)

    center, extent = visible_mesh_bounds()
    print(f"scene center: {center}")
    print(f"scene extent (mm): {tuple(round(e*1000, 1) for e in extent)}")

    cache_tissue_types()  # BEFORE material override so layer filtering still works
    mats = build_tissue_materials()
    apply_tissue_palette(mats)
    setup_world_white()
    setup_lighting()

    manifest = []
    for label, camera_view, layer_mode, aspect in VIEWS:
        if views_filter and label not in views_filter:
            continue
        path = render_view(label, camera_view, layer_mode, center, extent,
                           out_dir, res_px, aspect)
        manifest.append({
            "label": label, "camera": camera_view, "layers": layer_mode,
            "aspect": aspect, "resolution_px": res_px,
            "path": str(path),
        })
    (out_dir / "manifest.json").write_text(json.dumps({
        "scene_center": center,
        "scene_extent_m": extent,
        "quick_mode": quick,
        "renders": manifest,
    }, indent=2))
    print(f"\nmanifest: {out_dir / 'manifest.json'}")


if __name__ == "__main__":
    main()
