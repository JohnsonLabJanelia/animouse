"""
Mesh metadata extraction for the mouse biomechanical model.

Extracts geometric properties (volume, surface area, bounding box, center of mass)
and organizational metadata (tissue type, collection, laterality, connections)
for every mesh in the model.
"""

import bpy
import bmesh
import mathutils
import json
import csv
import os
from collections import Counter

from .tissue_types import get_tissue_type, get_laterality, get_collection_path

# Blender internal units are meters; we report in mm
M_TO_MM = 1000.0
M3_TO_MM3 = 1e9
M2_TO_MM2 = 1e6


def compute_mesh_geometry(obj):
    """Compute geometric properties of a mesh object.

    Uses the evaluated (subdivided) mesh for accuracy.

    Args:
        obj: A Blender mesh object

    Returns:
        dict with keys: vertices, faces, edges, volume_mm3, surface_area_mm2,
                        center_of_mass_mm
    """
    depsgraph = bpy.context.evaluated_depsgraph_get()
    obj_eval = obj.evaluated_get(depsgraph)
    mesh_eval = obj_eval.to_mesh()

    bm = bmesh.new()
    bm.from_mesh(mesh_eval)
    bmesh.ops.triangulate(bm, faces=bm.faces)

    try:
        volume = abs(bm.calc_volume())
    except Exception:
        volume = 0.0

    surface_area = sum(f.calc_area() for f in bm.faces)

    n_verts = len(bm.verts)
    n_faces = len(bm.faces)
    n_edges = len(bm.edges)

    # Center of mass (vertex average in world space)
    if bm.verts:
        world_mat = obj.matrix_world
        com = sum((world_mat @ v.co for v in bm.verts), mathutils.Vector()) / len(bm.verts)
    else:
        com = obj.location.copy()

    bm.free()
    obj_eval.to_mesh_clear()

    return {
        "vertices": n_verts,
        "faces": n_faces,
        "edges": n_edges,
        "volume_mm3": round(volume * M3_TO_MM3, 4),
        "surface_area_mm2": round(surface_area * M2_TO_MM2, 4),
        "center_of_mass_mm": [round(c * M_TO_MM, 3) for c in com],
    }


def get_armature_connections(obj):
    """Find armature/bone connections for an object.

    Args:
        obj: A Blender object

    Returns:
        list of str describing connections
    """
    connections = []
    if obj.parent and obj.parent.type == "ARMATURE" and obj.parent_bone:
        connections.append(f"parent_bone:{obj.parent_bone}")
    for mod in obj.modifiers:
        if mod.type == "ARMATURE" and mod.object:
            connections.append(f"armature:{mod.object.name}")
    return connections


def extract_single_mesh(obj):
    """Extract full metadata for a single mesh object.

    Args:
        obj: A Blender mesh object

    Returns:
        dict with all metadata fields
    """
    geo = compute_mesh_geometry(obj)
    connections = get_armature_connections(obj)

    return {
        "name": obj.name,
        "tissue_type": get_tissue_type(obj),
        "collection": get_collection_path(obj),
        "laterality": get_laterality(obj.name),
        "vertices": geo["vertices"],
        "faces": geo["faces"],
        "edges": geo["edges"],
        "volume_mm3": geo["volume_mm3"],
        "surface_area_mm2": geo["surface_area_mm2"],
        "bbox_x_mm": round(obj.dimensions[0] * M_TO_MM, 3),
        "bbox_y_mm": round(obj.dimensions[1] * M_TO_MM, 3),
        "bbox_z_mm": round(obj.dimensions[2] * M_TO_MM, 3),
        "location_mm": [round(l * M_TO_MM, 3) for l in obj.location],
        "center_of_mass_mm": geo["center_of_mass_mm"],
        "materials": [s.material.name for s in obj.material_slots if s.material],
        "connections": connections,
    }


def extract_all_meshes(progress_callback=None):
    """Extract metadata for every mesh object in the scene.

    Args:
        progress_callback: optional callable(index, total, name) for progress reporting

    Returns:
        list of dicts, one per mesh object, sorted by name
    """
    meshes = sorted(
        [o for o in bpy.data.objects if o.type == "MESH"],
        key=lambda o: o.name,
    )

    catalog = []
    for i, obj in enumerate(meshes):
        if progress_callback:
            progress_callback(i, len(meshes), obj.name)
        catalog.append(extract_single_mesh(obj))

    return catalog


def save_catalog_json(catalog, filepath):
    """Save catalog to JSON."""
    with open(filepath, "w") as f:
        json.dump(catalog, f, indent=2)


def save_catalog_csv(catalog, filepath):
    """Save catalog to CSV."""
    fields = [
        "name", "tissue_type", "collection", "laterality",
        "vertices", "faces", "edges",
        "volume_mm3", "surface_area_mm2",
        "bbox_x_mm", "bbox_y_mm", "bbox_z_mm",
        "location_mm", "center_of_mass_mm",
        "materials", "connections",
    ]
    with open(filepath, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for rec in catalog:
            row = dict(rec)
            row["location_mm"] = str(row["location_mm"])
            row["center_of_mass_mm"] = str(row["center_of_mass_mm"])
            row["materials"] = "; ".join(row["materials"])
            row["connections"] = "; ".join(row["connections"])
            writer.writerow(row)


def print_summary(catalog):
    """Print a summary of the catalog to stdout."""
    tissue_counts = Counter(r["tissue_type"] for r in catalog)
    lat_counts = Counter(r["laterality"] for r in catalog)

    print(f"\nTotal meshes: {len(catalog)}")
    print(f"Total vertices: {sum(r['vertices'] for r in catalog):,}")
    print(f"Total volume: {sum(r['volume_mm3'] for r in catalog):.1f} mm3")

    print("\nBy tissue type:")
    for t, c in tissue_counts.most_common():
        print(f"  {t}: {c}")

    print("\nBy laterality:")
    for l, c in lat_counts.most_common():
        print(f"  {l}: {c}")

    print("\nTop 10 by volume:")
    by_vol = sorted(catalog, key=lambda r: r["volume_mm3"], reverse=True)[:10]
    for r in by_vol:
        print(f"  {r['name']}: {r['volume_mm3']:.1f} mm3 ({r['tissue_type']})")
