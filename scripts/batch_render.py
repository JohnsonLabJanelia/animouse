"""
Batch render mesh catalog from the command line.

Usage:
    blender --background model.blend --python scripts/batch_render.py
    blender --background model.blend --python scripts/batch_render.py -- --mode all
    blender --background model.blend --python scripts/batch_render.py -- --mode test
    blender --background model.blend --python scripts/batch_render.py -- --names "Skull,heart,CNS"
    blender --background model.blend --python scripts/batch_render.py -- --size 1024 --samples 128
"""

import sys
import os

# Add parent directory to path so we can import the animouse package
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from animouse.render_catalog import render_catalog

# Parse args after "--"
argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def get_arg(flag, default=None):
    if flag in argv:
        idx = argv.index(flag)
        if idx + 1 < len(argv):
            return argv[idx + 1]
    return default


TEST_MESHES = [
    "humerus_right", "Skull", "Pectoralis_major_superficial_right",
    "Gluteus medius", "heart", "CNS", "Femur_right", "Retopo_3.068",
]

mode = get_arg("--mode", "test")
names_str = get_arg("--names", "")
size = int(get_arg("--size", "512"))
samples = int(get_arg("--samples", "64"))

if names_str:
    targets = [n.strip() for n in names_str.split(",")]
elif mode == "all":
    targets = None
else:
    targets = TEST_MESHES

config = {
    "render_size": size,
    "cycles_samples": samples,
    "skip_existing": "--no-skip" not in argv,
}


def progress(i, total, name, status):
    print(f"[{i+1}/{total}] {name}: {status}")


print(f"\nBatch Render: mode={mode}, size={size}px")
stats = render_catalog(target_names=targets, config=config, progress_callback=progress)
print(f"\nDone: {stats['rendered']} rendered, {stats['skipped']} skipped, {stats['failed']} failed")
