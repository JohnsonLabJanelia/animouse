"""
AniMouse — Blender Add-on for Mouse Biomechanical Modeling

Provides tools for rendering, validating, and exporting the AniBody
mouse musculoskeletal model.

Install: Blender > Preferences > Add-ons > Install from Disk > select animouse/ folder
"""

bl_info = {
    "name": "AniMouse",
    "author": "Johnson Lab, HHMI Janelia Research Campus",
    "version": (0, 1, 0),
    "blender": (4, 1, 0),
    "location": "View3D > Sidebar > AniMouse",
    "description": "Tools for the AniBody mouse biomechanical model",
    "category": "Science",
}

import bpy
import os
from bpy.props import (
    StringProperty, IntProperty, FloatProperty,
    BoolProperty, EnumProperty,
)


# ============================================================================
# Operators
# ============================================================================

class ANIMOUSE_OT_extract_metadata(bpy.types.Operator):
    """Extract metadata (volume, surface area, tissue type, etc.) for all meshes"""
    bl_idname = "animouse.extract_metadata"
    bl_label = "Extract Mesh Metadata"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        from .mesh_metadata import extract_all_meshes, save_catalog_json, save_catalog_csv, print_summary

        blend_dir = os.path.dirname(bpy.data.filepath) or os.getcwd()
        out_dir = os.path.join(blend_dir, "supplementary")
        os.makedirs(out_dir, exist_ok=True)

        def progress(i, total, name):
            if i % 50 == 0:
                print(f"  [{i+1}/{total}] {name}")

        catalog = extract_all_meshes(progress_callback=progress)

        json_path = os.path.join(out_dir, "mesh_catalog.json")
        csv_path = os.path.join(out_dir, "mesh_catalog.csv")
        save_catalog_json(catalog, json_path)
        save_catalog_csv(catalog, csv_path)
        print_summary(catalog)

        self.report({"INFO"}, f"Extracted {len(catalog)} meshes to {out_dir}")
        return {"FINISHED"}


class ANIMOUSE_OT_render_catalog(bpy.types.Operator):
    """Render isolated thumbnails of each mesh with tissue-type coloring"""
    bl_idname = "animouse.render_catalog"
    bl_label = "Render Mesh Catalog"
    bl_options = {"REGISTER"}

    mode: EnumProperty(
        name="Mode",
        items=[
            ("TEST", "Test (8 parts)", "Render 8 representative parts"),
            ("ALL", "All Meshes", "Render all 583 meshes"),
            ("SELECTED", "Selected Only", "Render selected objects"),
        ],
        default="TEST",
    )

    render_size: IntProperty(name="Size", default=512, min=128, max=4096)
    skip_existing: BoolProperty(name="Skip Existing", default=True)

    def execute(self, context):
        from .render_catalog import render_catalog

        test_meshes = [
            "humerus_right", "Skull", "Pectoralis_major_superficial_right",
            "Gluteus medius", "heart", "CNS", "Femur_right", "Retopo_3.068",
        ]

        if self.mode == "TEST":
            targets = test_meshes
        elif self.mode == "SELECTED":
            targets = [o.name for o in context.selected_objects if o.type == "MESH"]
        else:
            targets = None  # all

        config = {
            "render_size": self.render_size,
            "skip_existing": self.skip_existing,
        }

        def progress(i, total, name, status):
            print(f"[{i+1}/{total}] {name}: {status}")

        stats = render_catalog(
            target_names=targets,
            config=config,
            progress_callback=progress,
        )

        msg = f"Rendered: {stats['rendered']}, Skipped: {stats['skipped']}, Failed: {stats['failed']}"
        self.report({"INFO"}, msg)
        print(msg)
        return {"FINISHED"}

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)


class ANIMOUSE_OT_render_whole_body(bpy.types.Operator):
    """Render the complete model from multiple viewpoints"""
    bl_idname = "animouse.render_whole_body"
    bl_label = "Render Whole Body"
    bl_options = {"REGISTER"}

    render_size: IntProperty(name="Size", default=1024, min=256, max=8192)

    def execute(self, context):
        from .compat import eevee_engine_name
        import math, mathutils

        blend_dir = os.path.dirname(bpy.data.filepath) or os.getcwd()
        out_dir = os.path.join(blend_dir, "supplementary", "renders")
        os.makedirs(out_dir, exist_ok=True)

        scene = bpy.data.scenes.new("_animouse_wholebody")
        scene.render.engine = eevee_engine_name()
        scene.render.resolution_x = self.render_size
        scene.render.resolution_y = self.render_size
        scene.render.film_transparent = True
        scene.render.image_settings.file_format = "PNG"
        scene.render.image_settings.color_mode = "RGBA"

        # World
        world = bpy.data.worlds.new("_animouse_wb_world")
        world.use_nodes = True
        bg = world.node_tree.nodes["Background"]
        bg.inputs["Color"].default_value = (0.15, 0.15, 0.18, 1.0)
        bg.inputs["Strength"].default_value = 0.3
        scene.world = world

        # Copy all meshes (evaluated)
        depsgraph = bpy.context.evaluated_depsgraph_get()
        for obj in bpy.data.objects:
            if obj.type == "MESH":
                obj_eval = obj.evaluated_get(depsgraph)
                new_mesh = bpy.data.meshes.new_from_object(obj_eval)
                new_obj = bpy.data.objects.new(f"_animouse_wb_{obj.name}", new_mesh)
                new_obj.matrix_world = obj.matrix_world.copy()
                for slot in obj.material_slots:
                    if slot.material:
                        new_obj.data.materials.append(slot.material)
                scene.collection.objects.link(new_obj)

        # Lights
        for name, rot, energy in [
            ("Key", (50, 10, 30), 5.0),
            ("Fill", (60, -20, -45), 2.0),
        ]:
            ld = bpy.data.lights.new(f"_animouse_wb_{name}", "SUN")
            ld.energy = energy
            lo = bpy.data.objects.new(f"_animouse_wb_{name}", ld)
            scene.collection.objects.link(lo)
            lo.rotation_euler = tuple(math.radians(a) for a in rot)

        # Camera
        cd = bpy.data.cameras.new("_animouse_wb_cam")
        cd.lens = 50
        cd.clip_start = 0.001
        cam = bpy.data.objects.new("_animouse_wb_cam", cd)
        scene.collection.objects.link(cam)
        scene.camera = cam

        # Render from multiple views
        views = {
            "lateral":  ((0.0, -0.15, 0.05), (0, 0, 0.03)),
            "dorsal":   ((0.0, -0.01, 0.18), (0, 0, 0.03)),
            "ventral":  ((0.0, -0.01, -0.12), (0, 0, 0.03)),
            "anterior":  ((0.0, -0.15, 0.04), (0, -0.01, 0.04)),
        }

        orig_scene = bpy.context.window.scene
        bpy.context.window.scene = scene

        for view_name, (cam_loc, look_at) in views.items():
            cam.location = cam_loc
            target = mathutils.Vector(look_at)
            direction = target - cam.location
            cam.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()

            out_path = os.path.join(out_dir, f"whole_body_{view_name}.png")
            scene.render.filepath = out_path
            bpy.ops.render.render(write_still=True)
            print(f"Rendered: {view_name}")

        bpy.context.window.scene = orig_scene

        # Cleanup
        for obj in list(scene.collection.objects):
            bpy.data.objects.remove(obj, do_unlink=True)
        bpy.data.scenes.remove(scene)
        bpy.data.worlds.remove(world)

        self.report({"INFO"}, f"Rendered {len(views)} whole-body views")
        return {"FINISHED"}


# ============================================================================
# UI Panel
# ============================================================================

class ANIMOUSE_PT_main_panel(bpy.types.Panel):
    """AniMouse tools panel in the 3D Viewport sidebar"""
    bl_label = "AniMouse"
    bl_idname = "ANIMOUSE_PT_main_panel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "AniMouse"

    def draw(self, context):
        layout = self.layout

        # Model info
        mesh_count = len([o for o in bpy.data.objects if o.type == "MESH"])
        bone_count = sum(
            len(a.data.bones)
            for a in bpy.data.objects if a.type == "ARMATURE"
        )
        layout.label(text=f"Meshes: {mesh_count}  |  Bones: {bone_count}")

        layout.separator()

        # Metadata
        box = layout.box()
        box.label(text="Metadata", icon="FILE_TEXT")
        box.operator("animouse.extract_metadata", icon="EXPORT")

        # Rendering
        box = layout.box()
        box.label(text="Rendering", icon="RENDER_STILL")
        box.operator("animouse.render_catalog", icon="IMAGE_DATA")
        box.operator("animouse.render_whole_body", icon="CAMERA_DATA")

        # Info
        layout.separator()
        from .compat import version_string
        layout.label(text=f"Blender {version_string()}", icon="INFO")


# ============================================================================
# Registration
# ============================================================================

classes = (
    ANIMOUSE_OT_extract_metadata,
    ANIMOUSE_OT_render_catalog,
    ANIMOUSE_OT_render_whole_body,
    ANIMOUSE_PT_main_panel,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    print(f"AniMouse {'.'.join(str(v) for v in bl_info['version'])} registered")


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    print("AniMouse unregistered")


if __name__ == "__main__":
    register()
