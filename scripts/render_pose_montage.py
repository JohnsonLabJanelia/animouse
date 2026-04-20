"""Render multiple skeletal poses and composite into a montage.

Produces individual pose PNGs and a combined montage. The rig is bone-parented
(not weight-painted), so only the skeleton moves under pose changes; soft
tissues are hidden. This is the intended F4 demonstration of "the rig works."

Usage:
    blender --background mouse2_20260419.blend \\
        --python scripts/render_pose_montage.py -- \\
        --out ~/anibodymouse/claude_mouse_unknown_muscles/figures/catalogue/poses \\
        [--size 1500]
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import bpy
import mathutils

ADDON_PARENT = "/Users/johnsonr/src/animouse"
if ADDON_PARENT not in sys.path:
    sys.path.insert(0, ADDON_PARENT)
from animouse.tissue_types import MATERIAL_TO_TISSUE, TISSUE_COLORS  # noqa: E402
from animouse.compat import eevee_engine_name  # noqa: E402


EXTRA_MATERIAL_MAP = {
    "Muscles to ID": "muscle", "incisors": "bone",
    "rot axis ref": "unknown", "Dots Stroke": "unknown",
}
# Darker palette than our default — isolated skeleton on white needs more
# saturation to read cleanly.
PALETTE_OVERRIDES = {
    "bone":            (0.28, 0.28, 0.32, 1.0),
    "cartilage":       (0.30, 0.52, 0.72, 1.0),
}
CACHE_KEY = "_animouse_tissue"


# -------------------------------------------------------------------------
# Pose library. Each pose = dict of:
#   ik_world_deltas:   {bone_name: world-space offset vec for IK target bone}
#   bone_rotations:    {bone_name: (x, y, z) euler in DEGREES}
#
# World frame: +Z rostral, −X subject's right, +Y dorsal.
# -------------------------------------------------------------------------
POSES = {
    "rest": {
        "label": "Rest pose",
        "ik_world_deltas": {},
        "bone_rotations": {},
    },
    "t_pose": {
        "label": "T-pose",
        "ik_world_deltas": {
            "Arm_IK_controller_right": (-0.055, 0.0, 0.005),
            "Arm_IK_controller_left":  (+0.055, 0.0, 0.005),
            "scapula_IK_right":        (-0.020, 0.0, 0.005),
            "scapula_IK_left":         (+0.020, 0.0, 0.005),
        },
        "bone_rotations": {
            "Femur_right": (-70, 0, 0),
            "Femur_left":  (+70, 0, 0),
        },
    },
    "reach_forward": {
        "label": "Reaching forward",
        "ik_world_deltas": {
            "Arm_IK_controller_right": (-0.015, -0.010, 0.055),
            "scapula_IK_right":        (-0.008, -0.005, 0.030),
        },
        "bone_rotations": {},
    },
    "arms_up": {
        "label": "Forelimbs raised",
        "ik_world_deltas": {
            "Arm_IK_controller_right": (-0.015, +0.025, 0.045),
            "Arm_IK_controller_left":  (+0.015, +0.025, 0.045),
            "scapula_IK_right":        (-0.005, +0.015, 0.025),
            "scapula_IK_left":         (+0.005, +0.015, 0.025),
        },
        "bone_rotations": {},
    },
}


# -------------------------------------------------------------------------
# Scene setup (same conventions as render_armature_overlay.py)
# -------------------------------------------------------------------------

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
        name = f"_animouse_pose_{tissue}"
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
    scene = bpy.context.scene
    world = bpy.data.worlds.new("_animouse_pose_world")
    scene.world = world
    world.use_nodes = True
    nt = world.node_tree
    nt.nodes.clear()
    bg = nt.nodes.new("ShaderNodeBackground")
    bg.inputs["Color"].default_value = (1.0, 1.0, 1.0, 1.0)
    bg.inputs["Strength"].default_value = 1.0
    out = nt.nodes.new("ShaderNodeOutputWorld")
    nt.links.new(bg.outputs["Background"], out.inputs["Surface"])


def setup_lighting():
    # Softer than the card/overlay renders — the darker bone palette reads
    # cleanly at moderate exposure; strong lights were blowing highlights.
    for name, rot, energy in [
        ("Key",  (math.radians(50), math.radians(10),  math.radians(30)),  2.0),
        ("Fill", (math.radians(60), math.radians(-20), math.radians(-45)), 0.9),
        ("Rim",  (math.radians(30), 0.0,               math.radians(-150)), 1.2),
    ]:
        key = f"_animouse_pose_{name}"
        ld = bpy.data.lights.get(key) or bpy.data.lights.new(key, "SUN")
        ld.energy = energy
        obj = bpy.data.objects.get(key)
        if obj is None:
            obj = bpy.data.objects.new(key, ld)
            bpy.context.scene.collection.objects.link(obj)
        obj.rotation_euler = rot


def setup_render(size, aspect):
    scene = bpy.context.scene
    scene.render.engine = eevee_engine_name()
    if aspect >= 1.0:
        scene.render.resolution_x = size
        scene.render.resolution_y = int(size / aspect)
    else:
        scene.render.resolution_y = size
        scene.render.resolution_x = int(size * aspect)
    scene.render.resolution_percentage = 100
    scene.render.film_transparent = False
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"
    try:
        scene.eevee.taa_render_samples = 128
    except AttributeError:
        pass
    for flag in ("use_gtao", "use_ambient_occlusion", "use_ssao"):
        try:
            setattr(scene.eevee, flag, True)
        except AttributeError:
            pass
    for attr, val in (("gtao_distance", 0.02), ("gtao_factor", 1.8)):
        try:
            setattr(scene.eevee, attr, val)
        except AttributeError:
            pass
    try:
        scene.view_settings.view_transform = "Standard"
    except Exception:
        pass


VENTRAL_DIR_VEC = mathutils.Vector((-0.707, -0.707, 0.0)).normalized()


def _is_tail_bone_mesh(name: str) -> bool:
    """Heuristic: caudal vertebrae are named CA1, CA2, … CA30."""
    if not name.startswith("CA"):
        return False
    tail_num = name[2:].split(".")[0]
    return tail_num.isdigit()


def visible_mesh_bounds(exclude_tail: bool = True):
    """Scene bbox over visible meshes. With `exclude_tail`, caudal vertebrae
    are omitted from the bounds so the framing hugs the body without the
    tail dragging Z_min down by ~8 cm."""
    mins = [float("inf")] * 3
    maxs = [float("-inf")] * 3
    for obj in bpy.data.objects:
        if obj.type != "MESH":
            continue
        if exclude_tail and _is_tail_bone_mesh(obj.name):
            continue
        for c in obj.bound_box:
            w = obj.matrix_world @ mathutils.Vector(c)
            for i in range(3):
                mins[i] = min(mins[i], w[i])
                maxs[i] = max(maxs[i], w[i])
    center = mathutils.Vector([(mins[i] + maxs[i]) / 2 for i in range(3)])
    extent = [maxs[i] - mins[i] for i in range(3)]
    return center, extent


def setup_camera(center, extent, aspect, pose_pad: float = 1.7):
    cam = bpy.data.cameras.get("_animouse_pose_cam") or bpy.data.cameras.new("_animouse_pose_cam")
    cam.type = "PERSP"; cam.lens = 120.0; cam.sensor_width = 36.0
    cam.sensor_fit = "HORIZONTAL"; cam.clip_start = 0.001; cam.clip_end = 100.0
    cam_obj = bpy.data.objects.get("_animouse_pose_cam")
    if cam_obj is None:
        cam_obj = bpy.data.objects.new("_animouse_pose_cam", cam)
        bpy.context.scene.collection.objects.link(cam_obj)
    cam_obj.data = cam
    bpy.context.scene.camera = cam_obj

    look_dir = -VENTRAL_DIR_VEC
    rot_quat = look_dir.to_track_quat("-Z", "Y")
    cam_right = rot_quat @ mathutils.Vector((1, 0, 0))
    cam_up    = rot_quat @ mathutils.Vector((0, 1, 0))

    ex, ey, ez = extent
    hx, hy, hz = ex/2, ey/2, ez/2
    corners = [mathutils.Vector((dx, dy, dz))
               for dx in (-hx, hx) for dy in (-hy, hy) for dz in (-hz, hz)]
    body_w_m = 2 * max(abs(c.dot(cam_right)) for c in corners) * pose_pad
    body_h_m = 2 * max(abs(c.dot(cam_up))    for c in corners) * pose_pad

    fov_w = 2 * math.atan((cam.sensor_width / 2) / cam.lens)
    fov_v = 2 * math.atan((cam.sensor_width / aspect / 2) / cam.lens)
    dist_w = body_w_m / (2 * math.tan(fov_w / 2))
    dist_h = body_h_m / (2 * math.tan(fov_v / 2))
    dist = max(dist_w, dist_h)

    loc = center + VENTRAL_DIR_VEC * dist
    cam_obj.location = loc
    direction = center - loc
    cam_obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()


def show_skeleton_only():
    for obj in bpy.data.objects:
        if obj.type != "MESH":
            continue
        t = obj.get(CACHE_KEY, "unknown")
        obj.hide_render = t not in ("bone", "cartilage")


def restore_rest_pose(arm):
    for pb in arm.pose.bones:
        pb.location = (0, 0, 0)
        pb.rotation_mode = "QUATERNION"
        pb.rotation_quaternion = (1, 0, 0, 0)
        pb.rotation_euler = (0, 0, 0)
        pb.scale = (1, 1, 1)


def apply_pose(arm, pose_spec):
    # IK target bones — location in bone-local frame derived from world delta.
    for name, world_delta in pose_spec.get("ik_world_deltas", {}).items():
        pb = arm.pose.bones.get(name)
        if pb is None:
            print(f"    [warn] IK target bone '{name}' not found")
            continue
        bone_rest = arm.data.bones[name].matrix_local.to_3x3()
        local_delta = bone_rest.inverted() @ mathutils.Vector(world_delta)
        pb.location = local_delta
    # Direct bone rotations.
    for name, (rx, ry, rz) in pose_spec.get("bone_rotations", {}).items():
        pb = arm.pose.bones.get(name)
        if pb is None:
            print(f"    [warn] pose bone '{name}' not found")
            continue
        pb.rotation_mode = "XYZ"
        pb.rotation_euler = (math.radians(rx), math.radians(ry), math.radians(rz))


def render_pose(arm, pose_key, pose_spec, out_dir: Path):
    print(f"\n--- Rendering pose: {pose_key} ({pose_spec['label']}) ---")
    restore_rest_pose(arm)
    apply_pose(arm, pose_spec)
    bpy.context.view_layer.update()
    path = out_dir / f"pose_{pose_key}.png"
    bpy.context.scene.render.filepath = str(path)
    bpy.ops.render.render(write_still=True)
    print(f"  → {path}")
    return path


def parse_argv():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    out = {"out": None, "size": 1500, "aspect": 0.8}
    i = 0
    while i < len(argv):
        if argv[i] == "--out" and i + 1 < len(argv):
            out["out"] = Path(argv[i + 1]); i += 2
        elif argv[i] == "--size" and i + 1 < len(argv):
            out["size"] = int(argv[i + 1]); i += 2
        elif argv[i] == "--aspect" and i + 1 < len(argv):
            out["aspect"] = float(argv[i + 1]); i += 2
        else:
            i += 1
    return out


def main():
    args = parse_argv()
    assert args["out"], "need --out"
    args["out"].mkdir(parents=True, exist_ok=True)

    cache_tissue_types()
    mats = build_tissue_materials()
    apply_tissue_palette(mats)
    setup_world()
    setup_lighting()
    setup_render(args["size"], args["aspect"])

    center, extent = visible_mesh_bounds()
    setup_camera(center, extent, args["aspect"])
    show_skeleton_only()

    arm = next(o for o in bpy.data.objects if o.type == "ARMATURE")
    for pose_key, pose_spec in POSES.items():
        render_pose(arm, pose_key, pose_spec, args["out"])


if __name__ == "__main__":
    main()
