"""Render isolated thumbnails for each canonical anatomical structure.

For each mesh listed in the canonical catalogue CSV, hide every other mesh,
auto-frame the camera on that single mesh, apply the tissue palette (with
white-bg overrides matching render_f3.py), and save a 512×512 PNG.

Intended to produce the per-card images for a Pokemon-style visual catalogue.

Usage:
    blender --background mouse2_20260419.blend \\
        --python scripts/render_mesh_cards.py -- \\
        --catalogue ~/anibodymouse/claude_mouse_unknown_muscles/inspection/mesh_inventory_flagged_canonical.csv \\
        --out       ~/anibodymouse/claude_mouse_unknown_muscles/figures/catalogue/thumbnails \\
        [--size 512] [--limit 10]
"""
from __future__ import annotations

import csv
import math
import os
import re
import sys
import time
from pathlib import Path

import bpy
import mathutils

ADDON_PARENT = "/Users/johnsonr/src/animouse"
if ADDON_PARENT not in sys.path:
    sys.path.insert(0, ADDON_PARENT)
from animouse.tissue_types import MATERIAL_TO_TISSUE, TISSUE_COLORS  # noqa: E402
from animouse.compat import eevee_engine_name  # noqa: E402


EXTRA_MATERIAL_MAP = {
    "Muscles to ID": "muscle",
    "incisors": "bone",
    "rot axis ref": "unknown",
    "Dots Stroke": "unknown",
}

PALETTE_OVERRIDES = {
    "bone":            (0.52, 0.52, 0.55, 1.0),
    "cartilage":       (0.55, 0.72, 0.86, 1.0),
    "tendon/ligament": (0.88, 0.76, 0.38, 1.0),
    "kidney":          (0.52, 0.58, 0.38, 1.0),
    "claw":            (0.32, 0.28, 0.24, 1.0),
}

CACHE_KEY = "_animouse_tissue"

SAFE_FS_RE = re.compile(r"[^A-Za-z0-9._-]+")


def safe_filename(name: str) -> str:
    return SAFE_FS_RE.sub("_", name).strip("_") or "unnamed"


def tissue_type_for(obj):
    cached = obj.get(CACHE_KEY)
    if cached:
        return cached
    for slot in obj.material_slots:
        if slot.material:
            n = slot.material.name
            if n in MATERIAL_TO_TISSUE:
                return MATERIAL_TO_TISSUE[n]
            if n in EXTRA_MATERIAL_MAP:
                return EXTRA_MATERIAL_MAP[n]
    return "unknown"


def cache_tissue_types():
    for obj in bpy.data.objects:
        if obj.type == "MESH":
            obj[CACHE_KEY] = tissue_type_for(obj)


def build_tissue_materials():
    mats = {}
    for tissue, rgba in TISSUE_COLORS.items():
        rgba = PALETTE_OVERRIDES.get(tissue, rgba)
        name = f"_animouse_card_{tissue}"
        mat = bpy.data.materials.get(name) or bpy.data.materials.new(name)
        mat.use_nodes = True
        nt = mat.node_tree
        nt.nodes.clear()
        bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
        bsdf.inputs["Base Color"].default_value = rgba
        bsdf.inputs["Roughness"].default_value = 0.55
        out = nt.nodes.new("ShaderNodeOutputMaterial")
        nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
        mat.diffuse_color = rgba
        mats[tissue] = mat
    return mats


def apply_tissue_palette(mats):
    for obj in bpy.data.objects:
        if obj.type != "MESH":
            continue
        t = obj.get(CACHE_KEY, "unknown")
        mat = mats.get(t, mats["unknown"])
        if obj.data.materials:
            obj.data.materials[0] = mat
        else:
            obj.data.materials.append(mat)


def setup_world():
    """Zero-emission world — we want the 3-point lighting to define the look,
    not bounce from a bright world. The film is rendered transparent so the
    PDF assembler can composite each card onto any background."""
    scene = bpy.context.scene
    world = bpy.data.worlds.new("_animouse_card_world")
    scene.world = world
    world.use_nodes = True
    nt = world.node_tree
    nt.nodes.clear()
    bg = nt.nodes.new("ShaderNodeBackground")
    bg.inputs["Color"].default_value = (0.0, 0.0, 0.0, 1.0)
    bg.inputs["Strength"].default_value = 0.0
    out = nt.nodes.new("ShaderNodeOutputWorld")
    nt.links.new(bg.outputs["Background"], out.inputs["Surface"])


def setup_lighting():
    presets = [
        ("Key",  (math.radians(50), math.radians(10),  math.radians(30)),  3.0),
        ("Fill", (math.radians(60), math.radians(-20), math.radians(-45)), 1.2),
        ("Rim",  (math.radians(30), 0.0,               math.radians(-150)), 1.5),
    ]
    for name, rot, energy in presets:
        key = f"_animouse_card_{name}"
        ld = bpy.data.lights.get(key) or bpy.data.lights.new(key, "SUN")
        ld.energy = energy
        obj = bpy.data.objects.get(key)
        if obj is None:
            obj = bpy.data.objects.new(key, ld)
            bpy.context.scene.collection.objects.link(obj)
        obj.rotation_euler = rot


def setup_camera():
    cam = bpy.data.cameras.get("_animouse_card_cam") or bpy.data.cameras.new("_animouse_card_cam")
    cam.type = "PERSP"
    cam.lens = 85.0
    cam.sensor_width = 36.0
    cam.sensor_fit = "HORIZONTAL"
    cam.clip_start = 0.00001
    cam.clip_end = 100.0
    cam_obj = bpy.data.objects.get("_animouse_card_cam")
    if cam_obj is None:
        cam_obj = bpy.data.objects.new("_animouse_card_cam", cam)
        bpy.context.scene.collection.objects.link(cam_obj)
    cam_obj.data = cam
    bpy.context.scene.camera = cam_obj
    return cam_obj


def setup_render(size: int):
    scene = bpy.context.scene
    scene.render.engine = eevee_engine_name()
    scene.render.resolution_x = size
    scene.render.resolution_y = size
    scene.render.resolution_percentage = 100
    scene.render.film_transparent = True
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"
    scene.render.image_settings.compression = 15
    try:
        scene.eevee.taa_render_samples = 64
    except AttributeError:
        pass
    for flag in ("use_gtao", "use_ambient_occlusion", "use_ssao"):
        try:
            setattr(scene.eevee, flag, True)
        except AttributeError:
            pass
    for attr, val in (("gtao_distance", 0.01), ("gtao_factor", 1.2)):
        try:
            setattr(scene.eevee, attr, val)
        except AttributeError:
            pass
    try:
        scene.view_settings.view_transform = "Standard"
        scene.view_settings.look = "None"
        scene.view_settings.exposure = 0.0
        scene.view_settings.gamma = 1.0
    except Exception:
        pass


# Camera direction used for every card — 3/4 dorsolateral-right. Subject's
# right = world −X.
CARD_DIR_VEC = mathutils.Vector((-0.65, 0.45, 0.30)).normalized()
# Pre-compute the camera's world-space axes once (they're fixed by the
# direction + up-hint, independent of distance).
_LOOK_DIR = -CARD_DIR_VEC
_ROT_QUAT = _LOOK_DIR.to_track_quat("-Z", "Y")
CARD_CAM_RIGHT = _ROT_QUAT @ mathutils.Vector((1, 0, 0))
CARD_CAM_UP    = _ROT_QUAT @ mathutils.Vector((0, 1, 0))
CARD_CAM_BACK  = _ROT_QUAT @ mathutils.Vector((0, 0, 1))


def frame_camera_on(obj, cam_obj):
    """3/4 dorsolateral-right view, auto-distance to tightly fit the mesh's
    actual projected silhouette (not just its axis-aligned bbox max)."""
    corners = [obj.matrix_world @ mathutils.Vector(c) for c in obj.bound_box]
    center = mathutils.Vector((
        sum(c.x for c in corners) / 8,
        sum(c.y for c in corners) / 8,
        sum(c.z for c in corners) / 8,
    ))
    # Project each bbox corner onto the camera's image-plane axes.
    rel = [c - center for c in corners]
    max_right = max(abs(r.dot(CARD_CAM_RIGHT)) for r in rel)
    max_up    = max(abs(r.dot(CARD_CAM_UP))    for r in rel)
    # Depth extent toward the camera: ensures we don't place the camera
    # INSIDE the mesh for elongated shapes pointing at us.
    max_toward_camera = max((r.dot(CARD_CAM_BACK) for r in rel), default=0.0)
    max_toward_camera = max(max_toward_camera, 0.0)

    lens_mm = cam_obj.data.lens
    sensor_w = cam_obj.data.sensor_width
    fov = 2 * math.atan((sensor_w / 2) / lens_mm)
    pad = 1.15  # breathing room around the tight fit
    half_max = max(max_right, max_up) * pad
    half_max = max(half_max, 0.0003)  # floor for sub-mm meshes so framing isn't degenerate
    dist_for_frame = half_max / math.tan(fov / 2)
    # Ensure camera is in front of the nearest corner by a safety margin.
    dist = max(dist_for_frame, max_toward_camera + 0.003)

    loc = center + CARD_DIR_VEC * dist
    cam_obj.location = loc
    direction = center - loc
    cam_obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()


def parse_argv():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    out = {"catalogue": None, "out": None, "size": 512, "limit": None}
    i = 0
    while i < len(argv):
        if argv[i] == "--catalogue" and i + 1 < len(argv):
            out["catalogue"] = Path(argv[i + 1]); i += 2
        elif argv[i] == "--out" and i + 1 < len(argv):
            out["out"] = Path(argv[i + 1]); i += 2
        elif argv[i] == "--size" and i + 1 < len(argv):
            out["size"] = int(argv[i + 1]); i += 2
        elif argv[i] == "--limit" and i + 1 < len(argv):
            out["limit"] = int(argv[i + 1]); i += 2
        else:
            i += 1
    return out


def main():
    args = parse_argv()
    assert args["catalogue"] and args["out"], "need --catalogue and --out"
    args["out"].mkdir(parents=True, exist_ok=True)

    cache_tissue_types()
    mats = build_tissue_materials()
    apply_tissue_palette(mats)
    setup_world()
    setup_lighting()
    cam_obj = setup_camera()
    setup_render(args["size"])

    rows = list(csv.DictReader(args["catalogue"].open()))
    if args["limit"]:
        rows = rows[: args["limit"]]
    total = len(rows)
    print(f"Rendering {total} thumbnails at {args['size']}px → {args['out']}")

    # Build map of mesh objects for fast lookup.
    mesh_objs = {o.name: o for o in bpy.data.objects if o.type == "MESH"}

    # Hide all meshes by default; unhide per render.
    for o in mesh_objs.values():
        o.hide_render = True

    mapping_rows = []
    t0 = time.time()
    rendered = 0
    missing = 0
    for i, r in enumerate(rows):
        name = r["name"]
        obj = mesh_objs.get(name)
        if obj is None:
            missing += 1
            print(f"  [{i+1}/{total}] MISSING mesh: {name!r}")
            continue
        # Reveal just this mesh.
        obj.hide_render = False
        try:
            frame_camera_on(obj, cam_obj)
            safe = safe_filename(name)
            out_path = args["out"] / f"{safe}.png"
            bpy.context.scene.render.filepath = str(out_path)
            bpy.ops.render.render(write_still=True)
            rendered += 1
            mapping_rows.append({"name": name, "file": f"{safe}.png"})
            if (i + 1) % 25 == 0 or i == 0:
                elapsed = time.time() - t0
                rate = rendered / elapsed if elapsed > 0 else 0
                eta = (total - i - 1) / rate if rate > 0 else 0
                print(f"  [{i+1}/{total}] {safe}  ({rate:.2f}/s, ETA {eta/60:.1f} min)")
        finally:
            obj.hide_render = True

    # Write name→filename mapping for the PDF assembler.
    map_path = args["out"] / "manifest.csv"
    with map_path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["name", "file"])
        w.writeheader()
        w.writerows(mapping_rows)
    print(f"\nDone: {rendered}/{total} rendered, {missing} missing")
    print(f"Manifest: {map_path}")
    print(f"Elapsed: {(time.time()-t0)/60:.1f} min")


if __name__ == "__main__":
    main()
