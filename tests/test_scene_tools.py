"""Tests for scene checks."""

import os
import sys

# Repo root first, so tests always import this checkout's vexa (not an installed copy).
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import bpy  # noqa: E402

from helpers import cube, fresh, run, main, test  # noqa: E402


@test
def unwanted_objects():
    fresh()
    cube()
    cube("UCX_SM_Crate_01")
    bpy.ops.object.camera_add()
    bpy.ops.object.light_add(type="POINT")
    bpy.ops.object.empty_add()
    bpy.context.active_object.name = "SOCKET_Handle"
    _, r = run("detect_unwanted_objects")
    found = sorted(i.message for i in r.issues)
    assert r.status == "WARNING" and found == ["Unwanted camera", "Unwanted light"], found
    _, r = run("detect_unwanted_objects", allowed_types=["MESH", "CAMERA", "LIGHT"])
    assert r.status == "PASS", r.issues
    _, r = run("detect_unwanted_objects", allowed_types=["MESH", "CAMRA"])
    assert r.summary == "Check failed: unknown object types: CAMRA", r.summary


if __name__ == "__main__":
    main(globals())
