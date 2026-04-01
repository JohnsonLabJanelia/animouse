"""
Extract mesh metadata catalog from the command line.

Usage:
    blender --background model.blend --python scripts/extract_catalog.py
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import bpy
from animouse.mesh_metadata import extract_all_meshes, save_catalog_json, save_catalog_csv, print_summary

blend_dir = os.path.dirname(bpy.data.filepath) or os.getcwd()
out_dir = os.path.join(blend_dir, "supplementary")
os.makedirs(out_dir, exist_ok=True)


def progress(i, total, name):
    if i % 50 == 0 or i == total - 1:
        print(f"[{i+1}/{total}] {name}")


# Enable all collections
def enable_all(lc):
    lc.exclude = False
    lc.hide_viewport = False
    for c in lc.children:
        enable_all(c)


enable_all(bpy.context.view_layer.layer_collection)
for o in bpy.data.objects:
    o.hide_viewport = False

print("\nExtracting mesh metadata...")
catalog = extract_all_meshes(progress_callback=progress)

json_path = os.path.join(out_dir, "mesh_catalog.json")
csv_path = os.path.join(out_dir, "mesh_catalog.csv")
save_catalog_json(catalog, json_path)
save_catalog_csv(catalog, csv_path)
print_summary(catalog)

print(f"\nSaved: {json_path}")
print(f"Saved: {csv_path}")
