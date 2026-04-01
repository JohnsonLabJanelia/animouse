"""
Isolated mesh rendering for supplementary catalog figures.

Renders each mesh object individually with tissue-type coloring,
transparent background, and studio lighting. Creates a temporary
Blender scene so the user's scene is never modified.

Usage:
    # As operator from add-on panel
    bpy.ops.animouse.render_catalog()

    # As CLI script
    blender --background model.blend --python scripts/batch_render.py
"""

import bpy
import math
import mathutils
import os

from .tissue_types import get_tissue_type, get_tissue_color
from .compat import eevee_engine_name


# ============================================================================
# Configuration defaults (can be overridden by callers)
# ============================================================================

DEFAULT_CONFIG = {
    "render_size": 512,
    "focal_length": 85,
    "camera_distance_mult": 5.0,
    "orbit_h_deg": 35,
    "orbit_v_deg": 25,
    "key_energy": 5.0,
    "fill_energy": 2.0,
    "rim_energy": 3.0,
    "key_rotation_deg": (50, 10, 30),
    "fill_rotation_deg": (60, -20, -45),
    "rim_rotation_deg": (30, 0, -150),
    "engine": "EEVEE",       # "EEVEE" or "CYCLES"
    "cycles_samples": 64,
    "skip_existing": True,
}


def create_render_material(tissue_type):
    """Create or reuse a Principled BSDF material for a tissue type."""
    mat_name = f"_animouse_render_{tissue_type}"
    mat = bpy.data.materials.get(mat_name)
    if mat:
        return mat

    mat = bpy.data.materials.new(name=mat_name)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    nodes.clear()

    bsdf = nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.inputs["Base Color"].default_value = get_tissue_color(tissue_type)
    bsdf.inputs["Roughness"].default_value = 0.45

    output = nodes.new("ShaderNodeOutputMaterial")
    mat.node_tree.links.new(bsdf.outputs["BSDF"], output.inputs["Surface"])

    return mat


def setup_render_scene(config=None):
    """Create a temporary scene with lighting and camera for isolated rendering.

    Returns:
        (scene, camera_obj) tuple
    """
    cfg = {**DEFAULT_CONFIG, **(config or {})}

    scene = bpy.data.scenes.new("_animouse_render")

    # Engine
    if cfg["engine"] == "CYCLES":
        scene.render.engine = "CYCLES"
        scene.cycles.samples = cfg["cycles_samples"]
        scene.cycles.use_denoising = True
    else:
        scene.render.engine = eevee_engine_name()

    scene.render.resolution_x = cfg["render_size"]
    scene.render.resolution_y = cfg["render_size"]
    scene.render.film_transparent = True
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"

    # World
    world = bpy.data.worlds.new("_animouse_world")
    world.use_nodes = True
    bg = world.node_tree.nodes["Background"]
    bg.inputs["Color"].default_value = (0.15, 0.15, 0.18, 1.0)
    bg.inputs["Strength"].default_value = 0.3
    scene.world = world

    # Studio lighting (3 sun lights)
    for name, rot_deg, energy in [
        ("Key",  cfg["key_rotation_deg"],  cfg["key_energy"]),
        ("Fill", cfg["fill_rotation_deg"], cfg["fill_energy"]),
        ("Rim",  cfg["rim_rotation_deg"],  cfg["rim_energy"]),
    ]:
        light_data = bpy.data.lights.new(f"_animouse_{name}", "SUN")
        light_data.energy = energy
        light_obj = bpy.data.objects.new(f"_animouse_{name}", light_data)
        scene.collection.objects.link(light_obj)
        light_obj.rotation_euler = tuple(math.radians(a) for a in rot_deg)

    # Camera
    cam_data = bpy.data.cameras.new("_animouse_cam")
    cam_data.lens = cfg["focal_length"]
    cam_data.clip_start = 0.001  # 1mm — critical for small objects
    cam_data.clip_end = 10.0
    cam_obj = bpy.data.objects.new("_animouse_cam", cam_data)
    scene.collection.objects.link(cam_obj)
    scene.camera = cam_obj

    return scene, cam_obj


def render_single_mesh(source_obj, render_scene, cam_obj, output_path, config=None):
    """Render one mesh in isolation.

    Copies the evaluated mesh into the render scene, frames camera, renders,
    then cleans up. Does not modify the source object.

    Args:
        source_obj: The Blender mesh object to render
        render_scene: The temporary render scene
        cam_obj: The camera object in the render scene
        output_path: Full path for the output PNG
        config: Optional config dict overriding DEFAULT_CONFIG

    Returns:
        True if rendered successfully, False if skipped (degenerate mesh)
    """
    cfg = {**DEFAULT_CONFIG, **(config or {})}
    tissue = get_tissue_type(source_obj)
    render_mat = create_render_material(tissue)

    # Evaluate mesh (applies subdivision, etc.)
    depsgraph = bpy.context.evaluated_depsgraph_get()
    obj_eval = source_obj.evaluated_get(depsgraph)
    temp_mesh = bpy.data.meshes.new_from_object(obj_eval)
    temp_obj = bpy.data.objects.new("_animouse_target", temp_mesh)
    temp_obj.matrix_world = source_obj.matrix_world.copy()

    # Assign tissue material
    temp_obj.data.materials.clear()
    temp_obj.data.materials.append(render_mat)

    render_scene.collection.objects.link(temp_obj)

    # Compute world-space bounding box from vertices
    verts_world = [temp_obj.matrix_world @ v.co for v in temp_mesh.vertices]
    if not verts_world:
        render_scene.collection.objects.unlink(temp_obj)
        bpy.data.objects.remove(temp_obj)
        bpy.data.meshes.remove(temp_mesh)
        return False

    xs = [v.x for v in verts_world]
    ys = [v.y for v in verts_world]
    zs = [v.z for v in verts_world]
    center = mathutils.Vector((
        (min(xs) + max(xs)) / 2,
        (min(ys) + max(ys)) / 2,
        (min(zs) + max(zs)) / 2,
    ))
    max_dim = max(max(xs) - min(xs), max(ys) - min(ys), max(zs) - min(zs))

    if max_dim < 1e-8:
        render_scene.collection.objects.unlink(temp_obj)
        bpy.data.objects.remove(temp_obj)
        bpy.data.meshes.remove(temp_mesh)
        return False

    # Frame camera
    cam_dist = max_dim * cfg["camera_distance_mult"]
    ah = math.radians(cfg["orbit_h_deg"])
    av = math.radians(cfg["orbit_v_deg"])
    cam_obj.location = center + mathutils.Vector((
        cam_dist * math.cos(av) * math.sin(ah),
        -cam_dist * math.cos(av) * math.cos(ah),
        cam_dist * math.sin(av),
    ))
    direction = center - cam_obj.location
    cam_obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()

    # Render
    render_scene.render.filepath = output_path
    orig_scene = bpy.context.window.scene
    bpy.context.window.scene = render_scene
    bpy.ops.render.render(write_still=True)
    bpy.context.window.scene = orig_scene

    # Cleanup temp object
    render_scene.collection.objects.unlink(temp_obj)
    bpy.data.objects.remove(temp_obj)
    bpy.data.meshes.remove(temp_mesh)

    return True


def cleanup_render_data():
    """Remove all temporary data created by the renderer."""
    scene = bpy.data.scenes.get("_animouse_render")
    if scene:
        for obj in list(scene.collection.objects):
            bpy.data.objects.remove(obj, do_unlink=True)
        bpy.data.scenes.remove(scene)

    for mat in list(bpy.data.materials):
        if mat.name.startswith("_animouse_render_"):
            bpy.data.materials.remove(mat)
    for w in list(bpy.data.worlds):
        if w.name.startswith("_animouse_"):
            bpy.data.worlds.remove(w)
    for light in list(bpy.data.lights):
        if light.name.startswith("_animouse_"):
            bpy.data.lights.remove(light)
    for cam in list(bpy.data.cameras):
        if cam.name.startswith("_animouse_"):
            bpy.data.cameras.remove(cam)


def render_catalog(target_names=None, output_dir=None, config=None,
                   progress_callback=None):
    """Render a catalog of mesh thumbnails.

    Args:
        target_names: list of object names to render, or None for all meshes
        output_dir: directory for output PNGs, or None for default
        config: optional config dict
        progress_callback: optional callable(index, total, name, status)

    Returns:
        dict with keys: rendered, skipped, failed
    """
    cfg = {**DEFAULT_CONFIG, **(config or {})}

    if output_dir is None:
        blend_dir = os.path.dirname(bpy.data.filepath) or os.getcwd()
        output_dir = os.path.join(blend_dir, "supplementary", "renders")
    os.makedirs(output_dir, exist_ok=True)

    if target_names is None:
        target_names = sorted([o.name for o in bpy.data.objects if o.type == "MESH"])

    # Enable all collections for evaluation
    def enable_all(lc):
        lc.exclude = False
        lc.hide_viewport = False
        for c in lc.children:
            enable_all(c)
    enable_all(bpy.context.view_layer.layer_collection)
    for o in bpy.data.objects:
        o.hide_viewport = False

    cleanup_render_data()
    render_scene, cam_obj = setup_render_scene(cfg)

    stats = {"rendered": 0, "skipped": 0, "failed": 0}

    for i, name in enumerate(target_names):
        obj = bpy.data.objects.get(name)
        if not obj or obj.type != "MESH":
            stats["failed"] += 1
            if progress_callback:
                progress_callback(i, len(target_names), name, "not found")
            continue

        out_path = os.path.join(output_dir, f"{name}.png")
        if cfg["skip_existing"] and os.path.exists(out_path):
            stats["skipped"] += 1
            if progress_callback:
                progress_callback(i, len(target_names), name, "exists")
            continue

        if progress_callback:
            progress_callback(i, len(target_names), name, "rendering")

        try:
            ok = render_single_mesh(obj, render_scene, cam_obj, out_path, cfg)
            if ok:
                stats["rendered"] += 1
            else:
                stats["failed"] += 1
        except Exception as e:
            stats["failed"] += 1
            print(f"  FAIL [{name}]: {e}")

    cleanup_render_data()
    return stats
