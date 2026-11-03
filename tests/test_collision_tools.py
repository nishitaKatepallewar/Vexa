"""Tests for collision checks."""

import os
import sys

# Repo root first, so tests always import this checkout's vexa (not an installed copy).
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import bpy  # noqa: E402
from helpers import cube, fresh, run, main, test  # noqa: E402


@test
def collision_names_and_convexity():
    fresh()
    cube("SM_Crate")
    cube("UCX_SM_Crate_01", size=2.1)
    _, r = run("detect_invalid_collision_meshes")
    assert r.status == "PASS", [i.message for i in r.issues]
    bpy.ops.mesh.primitive_torus_add()
    bpy.context.active_object.name = "UCX_Missing_01"
    _, r = run("detect_invalid_collision_meshes")
    msgs = sorted(i.message for i in r.issues)
    assert msgs == ["Collision mesh isn't convex", "Collision name doesn't match any mesh"], msgs

if __name__ == "__main__":
    main(globals())
