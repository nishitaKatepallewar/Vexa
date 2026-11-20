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


def _flip(obj, face_indices):
    import bmesh
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bm.faces.ensure_lookup_table()
    bmesh.ops.reverse_faces(bm, faces=[bm.faces[i] for i in face_indices])
    bm.to_mesh(obj.data)
    bm.free()


@test
def flipped_normals_detect_and_fix():
    fresh()
    good = cube("SM_Good")
    one = cube("SM_OneFlipped", loc=(5, 0, 0))
    _flip(one, [2])
    inside_out = cube("SM_InsideOut", loc=(10, 0, 0))
    _flip(inside_out, range(6))
    plane = mesh_from("SM_PlaneDown", [(0, 0, 0), (0, 1, 0), (1, 1, 0), (1, 0, 0)], [(0, 1, 2, 3)])
    assert plane.data.polygons[0].normal.z < 0  # open surface: not judged
    _, r = run("detect_flipped_normals")
    found = {i.object_name: i.indices for i in r.issues}
    assert r.status == "ERROR" and found == {"SM_OneFlipped": [2], "SM_InsideOut": list(range(6))}, found
    msg, r = fix("detect_flipped_normals")
    assert r.status == "PASS" and msg == "Flipped 7 faces", (msg, r.summary)
    for obj in (good, one, inside_out):  # every face now points away from the centre
        assert all(p.normal.dot(p.center) > 0 for p in obj.data.polygons), obj.name


@test
def vertex_colors_detect_and_fix():
    fresh()
    c = cube()
    cube("SM_Clean", loc=(5, 0, 0))
    c.data.color_attributes.new("Col", "FLOAT_COLOR", "POINT")
    c.data.color_attributes.new("Mask", "BYTE_COLOR", "CORNER")
    _, r = run("detect_color_attributes")
    assert [(i.object_name, i.message) for i in r.issues] == [("SM_Crate", "Vertex colors: Col, Mask")], r.issues
    msg, r = fix("detect_color_attributes")
    assert r.status == "PASS" and msg == "Removed 2 vertex color attributes", (msg, r.summary)


@test
def unapplied_modifiers():
    fresh()
    c = cube()
    c.modifiers.new("Bevel", "BEVEL")
    c.modifiers.new("Rig", "ARMATURE")
    cube("SM_Clean", loc=(5, 0, 0))
    _, r = run("detect_unapplied_modifiers")
    assert [(i.object_name, i.message) for i in r.issues] == [("SM_Crate", "Unapplied modifiers: Bevel")], r.issues
    _, r = run("detect_unapplied_modifiers", ignore=["ARMATURE", "BEVEL"])
    assert r.status == "PASS", r.issues
    _, r = run("detect_unapplied_modifiers", ignore=["BEVVEL"])
    assert r.summary == "Check failed: unknown modifier types: BEVVEL", r.summary


@test
def flipped_normals_on_a_mesh_of_many_parts():
    # One mesh made of thousands of separate closed parts (bolts, rivets) used to take
    # hours: normals were recalculated once per part, each time across the whole mesh.
    import time
    import bmesh
    from mathutils import Matrix
    fresh()
    me = bpy.data.meshes.new("SM_Kitbash")
    bm = bmesh.new()
    for i in range(3000):
        geom = bmesh.ops.create_icosphere(bm, subdivisions=1, radius=0.3,
                                          matrix=Matrix.Translation((i % 60, i // 60, 0)))
        if i == 7:  # one part inside out
            bmesh.ops.reverse_faces(bm, faces=list({f for v in geom["verts"] for f in v.link_faces}))
    bm.to_mesh(me)
    bm.free()
    obj = bpy.data.objects.new("SM_Kitbash", me)
    bpy.context.scene.collection.objects.link(obj)
    start = time.perf_counter()
    _, r = run("detect_flipped_normals", objs=[obj])
    seconds = time.perf_counter() - start
    assert r.status == "ERROR" and len(r.issues[0].indices) == 20, r.summary  # that one part (20 faces)
    assert seconds < 10, f"took {seconds:.1f}s"  # well over a minute before the fix


@test
def flipped_normals_skip_pieces_with_no_inside():
    # Imported meshes can contain two copies of one face. Together they look like a
    # closed piece, but it has no volume, so neither copy is "inward".
    fresh()
    verts = [(0, 0, 0), (1, 0, 0), (0, 1, 0), (3, 0, 0), (4, 0, 0), (3, 1, 0)]
    mesh_from("SM_Doubled", verts, [(0, 1, 2), (0, 1, 2), (3, 4, 5), (5, 4, 3)])
    _, r = run("detect_flipped_normals")
    assert r.status == "PASS", r.issues


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


@test
def vertex_budget():
    fresh()
    bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=4)  # 642 verts
    _, r = run("detect_over_vertex_budget", max_verts=500)
    assert r.status == "WARNING" and r.summary == "642 verts / 500", r.summary
    _, r = run("detect_over_vertex_budget", max_verts=642)
    assert r.status == "PASS"


if __name__ == "__main__":
    main(globals())
