"""Tests for geometry checks."""

import os
import sys

# Repo root first, so tests always import this checkout's vexa (not an installed copy).
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import bpy  # noqa: E402
from helpers import cube, fix, fresh, mesh_from, run, main, test  # noqa: E402


@test
def ngons_detect_and_fix():
    fresh()
    bpy.ops.mesh.primitive_cylinder_add(vertices=8)
    _, r = run("detect_ngons")
    assert r.status == "WARNING" and r.issues[0].indices and len(r.issues[0].indices) == 2, r
    _, r = fix("detect_ngons")
    assert r.status == "PASS", r


@test
def nonplanar_quad():
    fresh()
    mesh_from("SM_Bent", [(0, 0, 0), (1, 0, 0), (1, 1, 0.3), (0, 1, 0)], [(0, 1, 2, 3)])
    mesh_from("SM_Flat", [(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0)], [(0, 1, 2, 3)])
    _, r = run("detect_nonplanar_faces")
    assert [i.object_name for i in r.issues] == ["SM_Bent"], r
    _, r = fix("detect_nonplanar_faces")
    assert r.status == "PASS", r


@test
def intersecting_meshes_found():
    fresh()
    cube("SM_A")
    cube("SM_B", loc=(1, 0.5, 0.3))
    cube("SM_Far", loc=(10, 0, 0))
    _, r = run("detect_intersecting_meshes")
    names = sorted(i.object_name for i in r.issues)
    assert names == ["SM_A", "SM_B"], names


if __name__ == "__main__":
    main(globals())
