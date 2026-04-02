"""
Render whole-body views with medical textbook-style anatomical labels.

Pipeline:
  1. Blender renders the full model with tissue-type materials
  2. Exports mesh centroid → 2D screen positions via camera projection
  3. Python/matplotlib overlays leader lines + labels

Usage:
    blender --background model.blend --python scripts/render_wholebody.py
    blender --background model.blend --python scripts/render_wholebody.py -- --view lateral
    blender --background model.blend --python scripts/render_wholebody.py -- --view all
    blender --background model.blend --python scripts/render_wholebody.py -- --layers skeleton
"""

import bpy
import json
import math
import mathutils
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from animouse.tissue_types import get_tissue_type, TISSUE_COLORS
from animouse.compat import eevee_engine_name

# --- Configuration ---

RENDER_WIDTH = 4000
RENDER_HEIGHT = 6000
SAMPLES = 128

# Camera presets: (location, rotation_euler in degrees, lens_mm)
# Model is roughly centered at origin, ~80mm long (nose to tail tip ~160mm in z)
# Model orientation: spine along Z-axis, head at Z≈+0.087, tail at Z≈-0.076
# Y-axis: dorsal (+Y) to ventral (-Y). X-axis: right (-X) to left (+X)
# Actual center from bounding box: (-0.001, -0.017, 0.006)
MODEL_CENTER = (-0.001, -0.017, 0.015)

CAMERA_PRESETS = {
    "lateral": {
        "location": (0.30, -0.017, 0.006),
        "target": MODEL_CENTER,
        "lens": 70,
        "description": "Right lateral view",
    },
    "dorsal": {
        "location": (-0.001, 0.30, 0.006),
        "target": MODEL_CENTER,
        "lens": 50,
        "description": "Dorsal (top-down) view",
    },
    "ventral": {
        "location": (-0.001, -0.30, 0.006),
        "target": MODEL_CENTER,
        "lens": 50,
        "description": "Ventral (bottom-up) view",
    },
    "three_quarter": {
        "location": (0.22, 0.18, 0.06),
        "target": MODEL_CENTER,
        "lens": 55,
        "description": "3/4 dorsolateral view",
    },
}

# Which collections to show for each layer mode
LAYER_MODES = {
    "full": None,  # show everything
    "skeleton": ["SKELETON"],
    "muscles": ["MUSCLES and TENDONS"],
    "skeleton_muscles": ["SKELETON", "MUSCLES and TENDONS"],
    "organs": ["ORGANS"],
}

# Structures to label per view (name -> display_label)
# We'll auto-generate this from the model, but here are the key ones to always include
KEY_STRUCTURES = {
    # Skull & head
    "Skull": "Skull",
    "Mandible_right": "Mandible",
    "Mandible_left": "Mandible",
    "Hyoid": "Hyoid",
    "Tongue": "Tongue",
    "CNS": "Brain & Spinal cord",
    # Spine
    "C1": "Atlas (C1)",
    "C7": "C7",
    "T1": "T1",
    "T13": "T13",
    "L1": "L1",
    "L6": "L6",
    "sacrum": "Sacrum",
    "CA1": "CA1",
    "CA30": "CA30",
    # Shoulder & arm
    "scapula_right": "Scapula",
    "clavicle_right": "Clavicle",
    "humerus_right": "Humerus",
    "Radius_left": "Radius",
    "Ulna_left": "Ulna (left)",
    # Leg
    "Femur_right": "Femur",
    "Tibia_and _Fibula_right": "Tibia & Fibula",
    "Patella_right": "Patella",
    "Calcaneus_right": "Calcaneus",
    # Ribcage
    "Rib_1a_right": "Rib 1",
    "Rib_7_right": "Rib 7",
    "Rib_13_right": "Rib 13",
    "Manubrium": "Manubrium",
    "Sternebrum_4": "Sternum",
    # Pelvis
    "Pelvis_left": "Pelvis",
    # Organs
    "heart": "Heart",
    "kidney_right": "Kidney",
    "Lower_intestine": "Intestine",
    "bladder": "Bladder",
    "vasculature": "Vasculature",
    # Key muscles (for muscle layer)
    "Pectoralis_major_superficial_right": "Pectoralis major",
    "Acromiotrapezius_right": "Acromiotrapezius",
    "Spinotrapezius_right": "Spinotrapezius",
    "Biceps_brachii": "Biceps brachii",
    "Gluteus medius": "Gluteus medius",
    "Biceps_femorus_A": "Biceps femoris",
    "Cutaneous_maximus": "Cutaneous maximus",
    "Gastrocnemius_lateral": "Gastrocnemius",
}


def setup_tissue_materials():
    """Create Principled BSDF materials for each tissue type."""
    materials = {}
    for tissue_name, rgba in TISSUE_COLORS.items():
        mat_name = f"_animouse_wb_{tissue_name}"
        mat = bpy.data.materials.get(mat_name)
        if not mat:
            mat = bpy.data.materials.new(name=mat_name)
            mat.use_nodes = True
            nodes = mat.node_tree.nodes
            nodes.clear()
            bsdf = nodes.new("ShaderNodeBsdfPrincipled")
            bsdf.inputs["Base Color"].default_value = rgba
            bsdf.inputs["Roughness"].default_value = 0.5
            output = nodes.new("ShaderNodeOutputMaterial")
            mat.node_tree.links.new(bsdf.outputs["BSDF"], output.inputs["Surface"])
        materials[tissue_name] = mat
    return materials


def assign_tissue_materials(materials):
    """Assign tissue-type materials to all mesh objects."""
    for obj in bpy.data.objects:
        if obj.type != "MESH":
            continue
        tissue = get_tissue_type(obj)
        mat = materials.get(tissue, materials.get("unknown"))
        if mat:
            if obj.data.materials:
                obj.data.materials[0] = mat
            else:
                obj.data.materials.append(mat)


def setup_scene(view_name, layer_mode="full"):
    """Set up camera, lighting, and visibility for a specific view."""
    scene = bpy.context.scene
    preset = CAMERA_PRESETS[view_name]

    # Engine
    scene.render.engine = eevee_engine_name()
    scene.render.resolution_x = RENDER_WIDTH
    scene.render.resolution_y = RENDER_HEIGHT
    scene.render.film_transparent = True
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"

    # World - white background
    if not scene.world:
        scene.world = bpy.data.worlds.new("_animouse_wb_world")
    scene.world.use_nodes = True
    bg = scene.world.node_tree.nodes["Background"]
    bg.inputs["Color"].default_value = (1.0, 1.0, 1.0, 1.0)
    bg.inputs["Strength"].default_value = 1.0

    # Camera
    cam = bpy.data.cameras.get("_animouse_wb_cam")
    if not cam:
        cam = bpy.data.cameras.new("_animouse_wb_cam")
    cam.lens = preset["lens"]
    cam.clip_start = 0.001
    cam.clip_end = 10.0

    cam_obj = bpy.data.objects.get("_animouse_wb_cam")
    if not cam_obj:
        cam_obj = bpy.data.objects.new("_animouse_wb_cam", cam)
        scene.collection.objects.link(cam_obj)
    cam_obj.data = cam

    cam_obj.location = mathutils.Vector(preset["location"])
    target = mathutils.Vector(preset["target"])
    direction = target - cam_obj.location
    cam_obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
    scene.camera = cam_obj

    # Lighting - 3-point studio
    for name, rot_deg, energy in [
        ("Key", (45, 10, 30), 3.0),
        ("Fill", (60, -20, -45), 1.5),
        ("Rim", (30, 0, -150), 2.0),
    ]:
        light_name = f"_animouse_wb_{name}"
        light_data = bpy.data.lights.get(light_name)
        if not light_data:
            light_data = bpy.data.lights.new(light_name, "SUN")
        light_data.energy = energy
        light_obj = bpy.data.objects.get(light_name)
        if not light_obj:
            light_obj = bpy.data.objects.new(light_name, light_data)
            scene.collection.objects.link(light_obj)
        light_obj.rotation_euler = tuple(math.radians(a) for a in rot_deg)

    # Enable all layer collections first
    def enable_all(lc):
        lc.exclude = False
        lc.hide_viewport = False
        for c in lc.children:
            enable_all(c)
    enable_all(bpy.context.view_layer.layer_collection)

    # Layer visibility
    allowed_collections = LAYER_MODES.get(layer_mode)
    if allowed_collections is not None:
        # First, collect names of objects in allowed collections
        visible_names = set()

        def collect_visible(col, matched):
            is_match = matched or col.name in allowed_collections
            if is_match:
                for obj in col.objects:  # direct objects only, not all_objects
                    if obj.type == "MESH":
                        visible_names.add(obj.name)
            for child in col.children:
                collect_visible(child, is_match)

        collect_visible(scene.collection, False)

        # Then set visibility (safe — no iteration during modification)
        for obj in bpy.data.objects:
            if obj.type == "MESH":
                obj.hide_render = obj.name not in visible_names
    else:
        for obj in bpy.data.objects:
            if obj.type == "MESH":
                obj.hide_render = False

    return cam_obj


def project_3d_to_2d(scene, cam_obj, point_3d):
    """Project a 3D world point to 2D pixel coordinates."""
    co_2d = bpy_extras_project(scene, cam_obj, point_3d)
    if co_2d:
        return (co_2d.x * RENDER_WIDTH, (1.0 - co_2d.y) * RENDER_HEIGHT)
    return None


def bpy_extras_project(scene, cam_obj, point_3d):
    """Use bpy_extras to project 3D to normalized 2D."""
    from bpy_extras.object_utils import world_to_camera_view
    return world_to_camera_view(scene, cam_obj, mathutils.Vector(point_3d))


def get_mesh_centroids(cam_obj, scene, layer_mode="full"):
    """Get 2D projected centroids for all visible meshes."""
    centroids = {}
    depsgraph = bpy.context.evaluated_depsgraph_get()

    for obj in bpy.data.objects:
        if obj.type != "MESH":
            continue
        if layer_mode != "full" and obj.hide_render:
            continue

        # Compute world-space centroid from evaluated mesh vertices (true COM)
        obj_eval = obj.evaluated_get(depsgraph)
        mesh_eval = obj_eval.to_mesh()
        if mesh_eval and mesh_eval.vertices:
            world_mat = obj.matrix_world
            center = sum((world_mat @ v.co for v in mesh_eval.vertices),
                         mathutils.Vector()) / len(mesh_eval.vertices)
            obj_eval.to_mesh_clear()
        else:
            if mesh_eval:
                obj_eval.to_mesh_clear()
            # Fallback to bounding box
            bbox_corners = [obj.matrix_world @ mathutils.Vector(c) for c in obj.bound_box]
            center = sum(bbox_corners, mathutils.Vector()) / 8

        # Project to 2D
        pos_2d = project_3d_to_2d(scene, cam_obj, center)
        if pos_2d is None:
            continue

        # Check if point is in front of camera and within frame
        from bpy_extras.object_utils import world_to_camera_view
        co = world_to_camera_view(scene, cam_obj, center)
        if co.z <= 0:  # behind camera
            continue
        if co.x < -0.1 or co.x > 1.1 or co.y < -0.1 or co.y > 1.1:
            continue

        tissue = get_tissue_type(obj)
        centroids[obj.name] = {
            "pos_2d": list(pos_2d),
            "pos_3d": [center.x, center.y, center.z],
            "depth": co.z,
            "tissue_type": tissue,
        }

    return centroids


def render_view(view_name, layer_mode="full", output_dir=None):
    """Render a single whole-body view and export centroid data."""
    if output_dir is None:
        blend_dir = os.path.dirname(bpy.data.filepath) or os.getcwd()
        output_dir = os.path.join(blend_dir, "supplementary", "figures")
    os.makedirs(output_dir, exist_ok=True)

    print(f"\n=== Rendering: {view_name} ({layer_mode}) ===")

    # Setup
    materials = setup_tissue_materials()
    assign_tissue_materials(materials)
    cam_obj = setup_scene(view_name, layer_mode)

    # Render
    basename = f"wholebody_{view_name}_{layer_mode}"
    render_path = os.path.join(output_dir, f"{basename}.png")
    bpy.context.scene.render.filepath = render_path
    bpy.ops.render.render(write_still=True)
    print(f"  Rendered: {render_path}")

    # Export centroids
    centroids = get_mesh_centroids(cam_obj, bpy.context.scene, layer_mode)
    centroid_path = os.path.join(output_dir, f"{basename}_centroids.json")
    with open(centroid_path, "w") as f:
        json.dump(centroids, f, indent=2)
    print(f"  Centroids: {centroid_path} ({len(centroids)} meshes)")

    return render_path, centroid_path


# --- CLI ---
if __name__ == "__main__":
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []

    def get_arg(flag, default=None):
        if flag in argv:
            idx = argv.index(flag)
            if idx + 1 < len(argv):
                return argv[idx + 1]
        return default

    view = get_arg("--view", "lateral")
    layer = get_arg("--layers", "full")

    if view == "all":
        for v in CAMERA_PRESETS:
            render_view(v, layer)
    else:
        render_view(view, layer)
