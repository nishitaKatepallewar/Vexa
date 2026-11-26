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
    found = {i.object_name: (i.message, i.indices) for i in r.issues}
    assert r.status == "ERROR" and found == {"SM_OneFlipped": ("1 faces point inwards", [2]),
                                             "SM_InsideOut": ("Inside out: 6 faces face inwards",
                                                              list(range(6)))}, found
    assert [i.object_name for i in r.issues if i.no_fix] == ["SM_InsideOut"], r.issues
    msg, r = fix("detect_flipped_normals")
    assert msg.startswith("Flipped 1 faces. Left for you: SM_InsideOut (most of the piece"), msg
    assert [i.object_name for i in r.issues] == ["SM_InsideOut"] and not r.fixable, r.issues
    for obj in (good, one):  # every face now points away from the centre
        assert all(p.normal.dot(p.center) > 0 for p in obj.data.polygons), obj.name
    assert all(p.normal.dot(p.center) < 0 for p in inside_out.data.polygons)  # left as it was


@test
def a_room_is_never_turned_inside_out():
    """Audit: Flip Normals Outward turned an interior (all faces inward) outward."""
    fresh()
    room = cube("SM_Room", size=6)
    _flip(room, [0, 1, 2, 3, 4])  # five walls face in; one was modelled the wrong way round
    _, r = run("detect_flipped_normals")
    assert len(r.issues) == 1 and r.issues[0].message.startswith("Inside out") and not r.fixable, r.issues
    before = [tuple(p.normal) for p in room.data.polygons]
    fix("detect_flipped_normals")
    assert [tuple(p.normal) for p in room.data.polygons] == before


def _node_material(name):
    mat = bpy.data.materials.new(name)
    if mat.node_tree is None:  # Blender 4.x; 5.x materials always have nodes
        mat.use_nodes = True
    return mat


@test
def vertex_colors_a_material_uses_are_kept():
    """Audit: Remove Vertex Colors deleted a mask the material used."""
    fresh()
    c = cube()
    c.data.color_attributes.new("Col", "FLOAT_COLOR", "POINT")
    c.data.color_attributes.new("Mask", "BYTE_COLOR", "CORNER")
    mat = _node_material("M_Painted")
    group = bpy.data.node_groups.new("Blend", "ShaderNodeTree")  # the mask is read inside a group
    group.nodes.new("ShaderNodeVertexColor").layer_name = "Mask"
    mat.node_tree.nodes.new("ShaderNodeGroup").node_tree = group
    c.data.materials.append(mat)
    msg, r = fix("detect_color_attributes")
    assert [a.name for a in c.data.color_attributes] == ["Mask"], msg
    assert msg == "Removed 1 vertex color attributes, kept 1 a material uses", msg
    assert not r.fixable and r.issues[0].no_fix == "used by M_Painted", r.issues

    other = cube("SM_Default", loc=(5, 0, 0))
    other.data.color_attributes.new("Tint", "BYTE_COLOR", "CORNER")
    mat2 = _node_material("M_Tint")
    mat2.node_tree.nodes.new("ShaderNodeVertexColor")  # no name: reads the default colour
    other.data.materials.append(mat2)
    _, r = run("detect_color_attributes", objs=[other])
    assert not r.fixable and r.issues[0].no_fix == "used by M_Tint", r.issues


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


def _half_cube():
    """A cube cut at x=0, open along the cut, with a Mirror that closes it."""
    import bmesh
    obj = cube("SM_Half")
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bmesh.ops.bisect_plane(bm, geom=bm.verts[:] + bm.edges[:] + bm.faces[:], plane_co=(0, 0, 0),
                           plane_no=(1, 0, 0), clear_inner=True)
    bm.to_mesh(obj.data)
    bm.free()
    obj.modifiers.new("Mirror", "MIRROR").use_clip = True
    return obj


@test
def checks_look_at_the_mesh_as_exported():
    """Audit: open edges flagged a Mirror seam that's closed in the export, and the
    triangle budget passed 1,000 while the export had 3,072."""
    fresh()
    half = _half_cube()
    assert sum(1 for e in half.data.edges) and run("detect_open_edges")[1].status == "PASS"
    half.modifiers["Mirror"].show_viewport = False
    _, r = run("detect_open_edges")
    assert r.status == "WARNING", r.summary  # without the Mirror the seam is open

    fresh()
    smooth = cube("SM_Smooth")
    smooth.modifiers.new("Subdivision", "SUBSURF").levels = 2
    _, r = run("detect_over_triangle_budget", max_tris=50)
    assert r.issues[0].value == "192 tris" and r.issues[0].message == "Over triangle budget (12 before modifiers)"
    _, r = run("detect_over_vertex_budget", max_verts=50)
    assert r.issues[0].value == "98 verts", r.issues

    fresh()
    tri = cube("SM_Tri")
    tri.modifiers.new("Triangulate", "TRIANGULATE")
    assert run("detect_untriangulated_meshes")[1].status == "PASS"
    assert run("detect_nonplanar_faces", threshold_deg=0.0)[1].status == "PASS"

    fresh()
    bpy.ops.mesh.primitive_cylinder_add(vertices=8, end_fill_type="TRIFAN")  # caps of triangles
    can = bpy.context.active_object
    assert run("detect_ngons")[1].status == "PASS"
    can.modifiers.new("Decimate", "DECIMATE").decimate_type = "DISSOLVE"  # merges each cap into one n-gon
    _, r = run("detect_ngons")
    issue = r.issues[0]
    assert issue.message == "2 n-gons (made by modifiers)" and issue.element is None, issue
    assert not r.fixable and issue.no_fix.startswith("made by modifiers"), issue


@test
def nonplanar_ignores_slight_bends_by_default():
    """Audit: at 0.001°, 7,864 of 7,872 quads on an organic model were flagged."""
    fresh()
    mesh_from("SM_Slight", [(0, 0, 0), (1, 0, 0), (1, 1, 0.02), (0, 1, 0)], [(0, 1, 2, 3)])  # ~1.1°
    mesh_from("SM_Bent", [(3, 0, 0), (4, 0, 0), (4, 1, 0.5), (3, 1, 0)], [(0, 1, 2, 3)])  # ~19°
    _, r = run("detect_nonplanar_faces")
    assert [i.object_name for i in r.issues] == ["SM_Bent"], r.issues


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
