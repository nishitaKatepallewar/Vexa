"""Tests for naming checks."""

import os
import sys

# Repo root first, so tests always import this checkout's vexa (not an installed copy).
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import bpy  # noqa: E402
from helpers import cube, fix, fresh, run, main, test  # noqa: E402


@test
def naming_checks():
    fresh()
    bpy.ops.mesh.primitive_cube_add()  # "Cube"
    c2 = cube("Crate 01.v2")
    mat = bpy.data.materials.new("Wood Mat")
    c2.data.materials.append(mat)
    _, r = run("detect_default_names")
    assert [i.object_name for i in r.issues] == ["Cube"]
    _, r = run("detect_invalid_name_characters")
    assert len(r.issues) == 2, r.issues
    _, r = fix("detect_invalid_name_characters")
    assert r.status == "PASS", r.issues
    assert bpy.data.objects.get("Crate_01_v2") and bpy.data.materials.get("Wood_Mat")


@test
def rename_avoids_name_clash():
    fresh()
    cube("Crate_A")
    cube("Crate A")  # sanitizes to Crate_A, which is taken
    _, r = fix("detect_invalid_name_characters")
    assert r.status == "PASS", [i.message for i in r.issues]
    assert bpy.data.objects.get("Crate_A_1"), [o.name for o in bpy.data.objects]


@test
def prefix_added_and_collision_names_follow():
    fresh()
    cube("Crate")
    col = cube("UCX_Crate_01", size=2.1)
    _, r = run("detect_missing_name_prefix", prefix="SM_")
    assert [i.object_name for i in r.issues] == ["Crate"], r.issues  # collision ignored
    _, r = fix("detect_missing_name_prefix", prefix="SM_")
    assert r.status == "PASS" and col.name == "UCX_SM_Crate_01", col.name

if __name__ == "__main__":
    main(globals())
