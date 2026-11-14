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
def untriangulated_detect_and_fix():
    fresh()
    c = cube()  # 6 quads
    mesh_from("SM_Tri", [(0, 0, 0), (1, 0, 0), (1, 1, 0)], [(0, 1, 2)])
    _, r = run("detect_untriangulated_meshes")
    assert [i.object_name for i in r.issues] == ["SM_Crate"] and len(r.issues[0].indices) == 6, r.issues
    msg, r = fix("detect_untriangulated_meshes")
    assert r.status == "PASS" and msg == "Triangulated 6 faces", (msg, r.summary)
    assert len(c.data.polygons) == 12


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
def open_edges():
    fresh()
    cube("SM_Closed")
    mesh_from("SM_Plane", [(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0)], [(0, 1, 2, 3)])
    # Three faces sharing one edge, plus a loose edge.
    fin = mesh_from("SM_Fin", [(0, 0, 0), (0, 0, 1), (1, 0, 0), (-1, 0, 0), (0, 1, 0), (5, 5, 5)],
                    [(0, 1, 2), (0, 1, 3), (0, 1, 4)])
    fin.data.edges.add(1)
    fin.data.edges[-1].vertices = (4, 5)
    _, r = run("detect_open_edges")
    by_name = {i.object_name: i for i in r.issues}
    assert sorted(by_name) == ["SM_Fin", "SM_Plane"], by_name
    assert by_name["SM_Plane"].message == "4 open edges", by_name["SM_Plane"]
    assert by_name["SM_Fin"].message == "6 open, 1 non-manifold, 1 loose edges", by_name["SM_Fin"]
    assert by_name["SM_Plane"].element == "EDGE" and len(by_name["SM_Plane"].indices) == 4


@test
def intersecting_meshes_found():
    fresh()
    cube("SM_A")
    cube("SM_B", loc=(1, 0.5, 0.3))
    cube("SM_Far", loc=(10, 0, 0))
    _, r = run("detect_intersecting_meshes")
    names = sorted(i.object_name for i in r.issues)
    assert names == ["SM_A", "SM_B"], names


@test
def tri_budget():
    fresh()
    bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=4)  # 1280 tris
    _, r = run("detect_over_triangle_budget", max_tris=1000)
    assert r.status == "WARNING" and "1,280" in r.summary, r.summary
    _, r = run("detect_over_triangle_budget", max_tris=5000)
    assert r.status == "PASS"

if __name__ == "__main__":
    main(globals())
