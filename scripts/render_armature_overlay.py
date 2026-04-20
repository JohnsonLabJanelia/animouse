"""Render the skeleton and project the armature into the same camera frame.

Produces two outputs in the same directory:
  armature_skeleton_bg.png    — skeleton-only render (hero 3/4 view)
  armature_projections.json   — every armature bone with head+tail pixel
                                coordinates, IK info, and region label

The second matplotlib script (compose_armature_overlay.py) reads both and
draws the armature overlay on top of the skeleton.

Usage:
    blender --background mouse2_20260419.blend \\
        --python scripts/render_armature_overlay.py -- \\
        --out ~/anibodymouse/claude_mouse_unknown_muscles/figures/catalogue/armature \\
        [--size 1800]
"""
from __future__ import annotations

import json
import math
import re
import sys
from pathlib import Path

import bpy
import mathutils
from bpy_extras.object_utils import world_to_camera_view

ADDON_PARENT = "/Users/johnsonr/src/animouse"
if ADDON_PARENT not in sys.path:
    sys.path.insert(0, ADDON_PARENT)
from animouse.tissue_types import MATERIAL_TO_TISSUE, TISSUE_COLORS  # noqa: E402
from animouse.compat import eevee_engine_name  # noqa: E402


EXTRA_MATERIAL_MAP = {
    "Muscles to ID": "muscle", "incisors": "bone",
    "rot axis ref": "unknown", "Dots Stroke": "unknown",
}
PALETTE_OVERRIDES = {
    "bone":            (0.52, 0.52, 0.55, 1.0),
    "cartilage":       (0.55, 0.72, 0.86, 1.0),
    "tendon/ligament": (0.88, 0.76, 0.38, 1.0),
    "kidney":          (0.52, 0.58, 0.38, 1.0),
    "claw":            (0.32, 0.28, 0.24, 1.0),
}
CACHE_KEY = "_animouse_tissue"


# ---------------------------------------------------------------------------
# Shared scene setup (minimal — matches render_f3 style)
# ---------------------------------------------------------------------------

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
        name = f"_animouse_arm_{tissue}"
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
    world = bpy.data.worlds.new("_animouse_arm_world")
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
    presets = [
        ("Key",  (math.radians(50), math.radians(10),  math.radians(30)),  3.0),
        ("Fill", (math.radians(60), math.radians(-20), math.radians(-45)), 1.2),
        ("Rim",  (math.radians(30), 0.0,               math.radians(-150)), 1.5),
    ]
    for name, rot, energy in presets:
        key = f"_animouse_arm_{name}"
        ld = bpy.data.lights.get(key) or bpy.data.lights.new(key, "SUN")
        ld.energy = energy
        obj = bpy.data.objects.get(key)
        if obj is None:
            obj = bpy.data.objects.new(key, ld)
            bpy.context.scene.collection.objects.link(obj)
        obj.rotation_euler = rot


def setup_render(size: int, aspect: float):
    """`size` is the longer image dimension. aspect = width/height; <1 portrait."""
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
    scene.render.image_settings.compression = 15
    try:
        scene.eevee.taa_render_samples = 128
    except AttributeError:
        pass
    for flag in ("use_gtao", "use_ambient_occlusion", "use_ssao"):
        try:
            setattr(scene.eevee, flag, True)
        except AttributeError:
            pass
    try:
        scene.view_settings.view_transform = "Standard"
        scene.view_settings.look = "None"
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Camera — 3/4 ventral-right view. Starting from pure ventral (camera at
# world −Y looking +Y), rotate 45° around the vertical Z axis so that the
# subject's right side (world −X) is closer to the camera. Direction vector
# from subject to camera: (−sin45°, −cos45°, 0) = (−0.707, −0.707, 0).
# The body's projected silhouette is wider (needs both X and Y extents) so
# we use the projected-corners method to frame cleanly.
# ---------------------------------------------------------------------------

VENTRAL_DIR_VEC = mathutils.Vector((-0.707, -0.707, 0.0)).normalized()


def visible_mesh_bounds():
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
    center = mathutils.Vector([(mins[i] + maxs[i]) / 2.0 for i in range(3)])
    extent = [maxs[i] - mins[i] for i in range(3)]
    return center, extent


def setup_camera(center, extent, aspect):
    """3/4 ventral-right perspective camera with projected-bbox framing."""
    cam = bpy.data.cameras.get("_animouse_arm_cam") or bpy.data.cameras.new("_animouse_arm_cam")
    cam.type = "PERSP"
    cam.lens = 120.0
    cam.sensor_width = 36.0
    cam.sensor_fit = "HORIZONTAL"
    cam.clip_start = 0.001
    cam.clip_end = 100.0

    cam_obj = bpy.data.objects.get("_animouse_arm_cam")
    if cam_obj is None:
        cam_obj = bpy.data.objects.new("_animouse_arm_cam", cam)
        bpy.context.scene.collection.objects.link(cam_obj)
    cam_obj.data = cam
    bpy.context.scene.camera = cam_obj

    # Precompute camera's world-space right/up axes from the view direction.
    look_dir = -VENTRAL_DIR_VEC
    rot_quat = look_dir.to_track_quat("-Z", "Y")
    cam_right = rot_quat @ mathutils.Vector((1, 0, 0))
    cam_up    = rot_quat @ mathutils.Vector((0, 1, 0))

    # Project the scene bbox onto the camera's image-plane axes.
    ex, ey, ez = extent
    hx, hy, hz = ex / 2, ey / 2, ez / 2
    corners = [mathutils.Vector((dx, dy, dz))
               for dx in (-hx, hx) for dy in (-hy, hy) for dz in (-hz, hz)]
    pad = 1.10
    max_right = max(abs(c.dot(cam_right)) for c in corners)
    max_up    = max(abs(c.dot(cam_up))    for c in corners)
    body_w_m = 2 * max_right * pad
    body_h_m = 2 * max_up    * pad

    fov_w = 2 * math.atan((cam.sensor_width / 2) / cam.lens)
    fov_v = 2 * math.atan((cam.sensor_width / aspect / 2) / cam.lens)
    dist_w = body_w_m / (2 * math.tan(fov_w / 2))
    dist_h = body_h_m / (2 * math.tan(fov_v / 2))
    dist = max(dist_w, dist_h)

    loc = center + VENTRAL_DIR_VEC * dist
    cam_obj.location = loc
    direction = center - loc
    cam_obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
    return cam_obj


# ---------------------------------------------------------------------------
# Layer filter: skeleton only
# ---------------------------------------------------------------------------

def hide_nonskeleton():
    for obj in bpy.data.objects:
        if obj.type != "MESH":
            continue
        t = obj.get(CACHE_KEY, "unknown")
        obj.hide_render = t not in ("bone", "cartilage")


# ---------------------------------------------------------------------------
# Bone region classification (name-based)
# ---------------------------------------------------------------------------

REGION_PATTERNS = [
    # Keep order so first match wins. Spine before generic to catch L1 etc.
    ("spine",   re.compile(r"^(c|t|l|ca)\d+\b|sacrum|coccyx", re.IGNORECASE)),
    ("ribcage", re.compile(r"rib[_\.]|sternum|sternebrum|manubrium|xiphoid", re.IGNORECASE)),
    ("skull",   re.compile(r"skull|mandible|hyoid|incisor|cranio|maxilla|zygomatic|tongue|digastricus|mylohyoid", re.IGNORECASE)),
    # Forelimb: joints + muscles + bones explicitly in the forelimb
    ("forelimb",
     re.compile(r"humerus|radius|ulna|clavicle|scapula|metacarpal|phalanx_hand|"
                r"capitate|hamate|multangular|navicular|centrale|falsiformis|"
                r"sesamoid_hand|carpal|pectoral|supraspin|infraspin|subscap|teres|"
                r"deltoid|biceps_brach|triceps|coracobra|subclav|acromio|"
                r"spinodelt|rhomboid|latissimus|cutaneous|trapez|levator_scap|"
                r"anconeus|brachialis|brachioradialis|pronator|extensor_carp|"
                r"flexor_carp|extensor_dig|flexor_dig|abductor|adductor_poll|"
                r"splenius|anterior_serratus|serratus_anterior",
                re.IGNORECASE)),
    # Hindlimb
    ("hindlimb",
     re.compile(r"femur|tibia|fibula|patella|metatarsal|phalanx_foot|"
                r"tarsal|calcaneus|cuneiform|cuboid|astragalus|talus|sesamoid_foot|"
                r"gluteus|gastroc|soleus|quadric|rectus_fem|vastus|"
                r"biceps_fem|semitendi|semimemb|adductor|iliopsoas|piriformis|"
                r"tensor_fasc|tibialis|peroneus|plantaris|popliteus|"
                r"extensor_foot|flexor_foot|hindlimb",
                re.IGNORECASE)),
    ("shoulder", re.compile(r"shoulder", re.IGNORECASE)),
    ("pelvis",   re.compile(r"pelvis|ilium|ischium|pubis", re.IGNORECASE)),
]


def classify_bone_region(name: str) -> str:
    for region, pat in REGION_PATTERNS:
        if pat.search(name):
            return region
    return "other"


def is_utility(name: str) -> bool:
    n = name.lower()
    return ("stretch_to" in n or "bonexxx" in n or "xxx" in n
            or "_target" in n or "target_" in n)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def parse_argv():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    out = {"out": None, "size": 2000, "aspect": 0.22}
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
    cam_obj = setup_camera(center, extent, args["aspect"])

    # Hide everything except skeleton + cartilage.
    hide_nonskeleton()

    bg_path = args["out"] / "armature_skeleton_bg.png"
    bpy.context.scene.render.filepath = str(bg_path)
    bpy.ops.render.render(write_still=True)
    print(f"  → {bg_path}")

    # Project every armature bone. Use the armature's matrix_world to go from
    # bone-local head/tail to world coordinates, then bpy_extras to project.
    armatures = [o for o in bpy.data.objects if o.type == "ARMATURE"]
    if not armatures:
        print("NO ARMATURE FOUND")
        return
    arm_obj = armatures[0]

    scene = bpy.context.scene
    res_x = scene.render.resolution_x
    res_y = scene.render.resolution_y

    bone_records = []
    for bone in arm_obj.data.bones:
        world_head = arm_obj.matrix_world @ bone.head_local
        world_tail = arm_obj.matrix_world @ bone.tail_local
        h = world_to_camera_view(scene, cam_obj, world_head)
        t = world_to_camera_view(scene, cam_obj, world_tail)
        # h.z is depth in front of camera; negative means behind the camera.
        pb = arm_obj.pose.bones[bone.name]
        ik = next((c for c in pb.constraints if c.type == "IK"), None)
        bone_records.append({
            "name": bone.name,
            "parent": bone.parent.name if bone.parent else None,
            "head_px": (h.x * res_x, (1.0 - h.y) * res_y),
            "head_depth": h.z,
            "tail_px": (t.x * res_x, (1.0 - t.y) * res_y),
            "tail_depth": t.z,
            "length_mm": bone.length * 1000.0,
            "has_ik": ik is not None,
            "ik_chain_count": ik.chain_count if ik else 0,
            "ik_target_object": (ik.target.name if ik and ik.target else None),
            "ik_target_bone": (ik.subtarget if ik else ""),
            "region": classify_bone_region(bone.name),
            "is_utility": is_utility(bone.name),
            "use_deform": bool(bone.use_deform),
        })

    # Record which bones are MEMBERS of an IK chain (as opposed to having the
    # IK constraint themselves — IK constraint lives only on the tip bone).
    # For each bone with an IK constraint of chain_count N, walk up N parents.
    chain_members = set()
    by_name = {b["name"]: b for b in bone_records}
    for b in bone_records:
        if not b["has_ik"]:
            continue
        chain_members.add(b["name"])
        cur = b
        for _ in range(b["ik_chain_count"] - 1):
            p = cur["parent"]
            if p is None or p not in by_name:
                break
            chain_members.add(p)
            cur = by_name[p]
    for b in bone_records:
        b["in_ik_chain"] = b["name"] in chain_members

    # Depth-sort (back to front) so foreground bones draw on top.
    bone_records.sort(key=lambda b: -b["head_depth"])

    out_json = args["out"] / "armature_projections.json"
    with out_json.open("w") as f:
        json.dump({
            "image_path": str(bg_path),
            "resolution": [res_x, res_y],
            "armature_name": arm_obj.name,
            "bones": bone_records,
        }, f, indent=2)
    print(f"  → {out_json}  ({len(bone_records)} bones)")

    # Quick summary.
    from collections import Counter
    r = Counter(b["region"] for b in bone_records)
    print(f"  bones by region: {dict(r)}")
    ik_bones = [b for b in bone_records if b["has_ik"]]
    print(f"  {len(ik_bones)} bones with IK constraints")
    for b in ik_bones:
        print(f"    {b['name']}  chain_count={b['ik_chain_count']}  "
              f"target={b['ik_target_object']}/{b['ik_target_bone']}")


if __name__ == "__main__":
    main()
