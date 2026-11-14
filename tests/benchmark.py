"""Times every check on a heavy scene (about 83,000 faces).

Not part of run_all.py: timings on shared CI machines are too noisy to pass or fail
on. Run it by hand before and after a refactor, on the same machine:

    python tests/benchmark.py --save before.json        (on main)
    python tests/benchmark.py --compare before.json     (on your branch)

or with Blender: blender -b --factory-startup -P tests/benchmark.py -- --compare before.json

--compare exits non-zero if any check got more than 50% and 50 ms slower.
"""

import json
import os
import statistics
import sys
import time

# Repo root first, so tests always import this checkout's vexa (not an installed copy).
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import bpy  # noqa: E402

from helpers import finish, fresh, run  # noqa: E402
from vexa.core.registry import CHECK, AgentTools  # noqa: E402

REPEATS = 3


def heavy_scene():
    fresh()
    bpy.ops.mesh.primitive_grid_add(x_subdivisions=250, y_subdivisions=250, size=10)  # open, quads
    bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=6, radius=3, location=(12, 0, 0))  # closed, triangles
    for obj in bpy.context.scene.objects:
        if not obj.data.uv_layers:
            obj.data.uv_layers.new(name="UVMap")
        obj.data.materials.append(bpy.data.materials.new("M_" + obj.name))
    faces = sum(len(o.data.polygons) for o in bpy.context.scene.objects)
    print(f"Scene: {faces:,} faces, Blender {bpy.app.version_string}")


def timings() -> dict:
    heavy_scene()
    out = {}
    for entry in AgentTools.all(CHECK):
        samples = []
        for _ in range(REPEATS):
            start = time.perf_counter()
            run(entry.name)
            samples.append(time.perf_counter() - start)
        out[entry.name] = statistics.median(samples)
    return out


def main() -> None:
    args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
    now = timings()
    baseline = {}
    if "--compare" in args:
        with open(args[args.index("--compare") + 1], encoding="utf-8") as f:
            baseline = json.load(f)
    slower = []
    print(f"\n{'check':40} {'now':>9} {'before':>9}")
    for name, seconds in sorted(now.items(), key=lambda kv: -kv[1]):
        before = baseline.get(name)
        flag = ""
        if before is not None and seconds > before * 1.5 and seconds - before > 0.05:
            flag = "  SLOWER"
            slower.append(name)
        print(f"{name:40} {seconds * 1000:7.0f}ms {'' if before is None else f'{before * 1000:7.0f}ms'}{flag}")
    print(f"\nTotal: {sum(now.values()):.2f}s")
    if "--save" in args:
        path = args[args.index("--save") + 1]
        with open(path, "w", encoding="utf-8") as f:
            json.dump(now, f, indent=1)
        print(f"Saved {path}")
    finish(1 if slower else 0)


if __name__ == "__main__":
    main()
