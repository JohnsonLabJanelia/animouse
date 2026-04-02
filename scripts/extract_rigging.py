"""
Extract rigging/armature info for all meshes from the blend file.

Usage:
    blender --background model.blend --python scripts/extract_rigging.py

Outputs rigging_info.json alongside mesh_catalog.json.
"""

import bpy
import json
import os

blend_dir = os.path.dirname(bpy.data.filepath) or os.getcwd()
out_path = os.path.join(blend_dir, "supplementary", "rigging_info.json")

# Enable all collections
def enable_all(lc):
    lc.exclude = False
    lc.hide_viewport = False
    for c in lc.children:
        enable_all(c)
enable_all(bpy.context.view_layer.layer_collection)

# --- Build armature maps ---
armature_obj = None
for obj in bpy.data.objects:
    if obj.type == "ARMATURE":
        armature_obj = obj
        break

bone_names = set()
bone_parent_map = {}      # bone_name -> parent bone name
bone_children_map = {}    # bone_name -> [child bone names]
stretch_to_map = {}       # origin_bone -> insertion_bone (STRETCH_TO constraint)
ik_map = {}               # bone -> IK target
bone_to_skeletal = {}     # bone_name -> which skeletal bone it's parented to

if armature_obj:
    arm = armature_obj.data
    bone_names = {b.name for b in arm.bones}

    for b in arm.bones:
        bone_parent_map[b.name] = b.parent.name if b.parent else None
        bone_children_map[b.name] = [c.name for c in b.children]

    # Walk up to find the nearest "named" (non-Bone.XXX) skeletal parent
    def find_skeletal_parent(bone_name):
        """Walk up the bone hierarchy to find attachment to skeletal bones."""
        visited = set()
        current = bone_name
        chain = []
        while current and current not in visited:
            visited.add(current)
            parent = bone_parent_map.get(current)
            if parent:
                chain.append(parent)
            current = parent
        # Return the chain of named bones (skip Bone.XXX intermediates)
        return [b for b in chain if not b.startswith("Bone.")]

    for b in arm.bones:
        bone_to_skeletal[b.name] = find_skeletal_parent(b.name)

    # Parse pose bone constraints
    for pb in armature_obj.pose.bones:
        for c in pb.constraints:
            if c.type == "STRETCH_TO" and c.subtarget:
                stretch_to_map[pb.name] = c.subtarget
            elif c.type == "IK" and c.subtarget:
                ik_map[pb.name] = c.subtarget

# --- Build muscle origin-insertion descriptions ---
# Pattern: "Muscle_right" bone (origin on trunk/spine) with STRETCH_TO to
# "Muscle_stretch_to_right" bone (insertion on scapula/humerus/etc.)
def describe_muscle_rig(bone_name):
    """Describe the muscle rig for a bone that matches a mesh name."""
    parts = []

    # Is this bone an origin bone with a STRETCH_TO constraint?
    if bone_name in stretch_to_map:
        insertion_bone = stretch_to_map[bone_name]
        # Find what skeletal bone each end attaches to
        origin_parent = bone_parent_map.get(bone_name, "")
        insertion_parent = bone_parent_map.get(insertion_bone, "")
        parts.append(f"origin: {origin_parent} → insertion: {insertion_parent}")

    # What skeletal chain is it part of?
    skeletal_chain = bone_to_skeletal.get(bone_name, [])
    if skeletal_chain and not parts:
        parts.append(f"skeletal chain: {' → '.join(skeletal_chain[:3])}")

    # IK?
    if bone_name in ik_map:
        parts.append(f"IK target: {ik_map[bone_name]}")

    return "; ".join(parts)


# --- Extract per-mesh rigging info ---
rigging = {}

for obj in sorted(bpy.data.objects, key=lambda o: o.name):
    if obj.type != "MESH":
        continue

    info = {
        "parent": None,
        "parent_type": None,
        "parent_bone": None,
        "armature_modifier": None,
        "vertex_groups": [],
        "has_armature_bone": False,
        "muscle_rig": "",
        "is_rigged": False,
    }

    # Object parenting
    if obj.parent:
        info["parent"] = obj.parent.name
        info["parent_type"] = obj.parent.type
        info["is_rigged"] = True
        if obj.parent_bone:
            info["parent_bone"] = obj.parent_bone

    # Armature modifier
    for mod in obj.modifiers:
        if mod.type == "ARMATURE" and mod.object:
            info["armature_modifier"] = mod.object.name
            info["is_rigged"] = True

    # Vertex groups
    vgroups = [vg.name for vg in obj.vertex_groups]
    if vgroups:
        info["vertex_groups"] = vgroups
        info["is_rigged"] = True

    # Matching armature bone
    if obj.name in bone_names:
        info["has_armature_bone"] = True
        info["muscle_rig"] = describe_muscle_rig(obj.name)
        info["is_rigged"] = True

    rigging[obj.name] = info

os.makedirs(os.path.dirname(out_path), exist_ok=True)
with open(out_path, "w") as f:
    json.dump(rigging, f, indent=2)

rigged_count = sum(1 for v in rigging.values() if v["is_rigged"])
muscle_rigged = sum(1 for v in rigging.values() if v.get("muscle_rig"))
print(f"\nRigging info extracted: {len(rigging)} meshes, {rigged_count} rigged, {muscle_rigged} with muscle rig")
print(f"Saved to: {out_path}")
