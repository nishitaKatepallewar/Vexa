"""Tests for UV checks."""

import os
import sys

# Repo root first, so tests always import this checkout's vexa (not an installed copy).
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from helpers import cube, fix, fresh, mesh_from, run, main, test  # noqa: E402


@test
def uv_present_and_lightmap():
    fresh()
    mesh_from("SM_NoUV", [(0, 0, 0), (1, 0, 0), (1, 1, 0)], [(0, 1, 2)])
    c = cube()
    _, r = run("detect_missing_uv_maps")
    assert [i.object_name for i in r.issues] == ["SM_NoUV"], r
    _, r = run("detect_missing_lightmap_uvs", objs=[c])
    assert r.status == "ERROR" and "No lightmap" in r.issues[0].message
    lm = c.data.uv_layers.new(name="Lightmap")
    for d in lm.data:
        d.uv = (d.uv[0] * 0.5, d.uv[1] * 0.5)
    _, r = run("detect_missing_lightmap_uvs", objs=[c])
    assert r.status == "PASS", r.summary
    lm.data[0].uv = (1.5, 0.2)
    _, r = run("detect_missing_lightmap_uvs", objs=[c])
    assert "outside 0–1" in r.issues[0].message


@test
def extra_uv_maps_detect_and_fix():
    fresh()
    c = cube()  # one UV map
    _, r = run("detect_extra_uv_maps")
    assert r.status == "PASS", r.summary
    c.data.uv_layers.new(name="Lightmap")
    c.data.uv_layers.new(name="Spare")
    _, r = run("detect_extra_uv_maps")
    assert r.status == "WARNING" and r.issues[0].message == "Extra UV maps: Lightmap, Spare", r.issues
    _, r = run("detect_extra_uv_maps", max_uv_maps=2)
    assert r.issues[0].message == "Extra UV maps: Spare", r.issues
    msg, r = fix("detect_extra_uv_maps")
    assert r.status == "PASS" and msg == "Removed 2 UV maps", (msg, r.summary)
    assert [layer.name for layer in c.data.uv_layers] == ["UVMap"]


@test
def extra_uv_maps_fix_keeps_the_render_uv_map():
    fresh()
    c = cube()
    c.data.uv_layers.new(name="Painted").active_render = True
    msg, r = fix("detect_extra_uv_maps")
    assert "Skipped" in msg and r.status == "WARNING", (msg, r.summary)
    assert len(c.data.uv_layers) == 2



@test
def uvs_outside_0_1():
    fresh()
    cube("SM_Inside")  # Blender's cube UVs are inside 0–1
    c = cube("SM_Tiled", loc=(5, 0, 0))
    layer = c.data.uv_layers[0]
    for loop in c.data.polygons[3].loop_indices:
        u, v = layer.data[loop].uv
        layer.data[loop].uv = (u + 1.0, v)
    _, r = run("detect_uvs_outside_0_1")
    assert [(i.object_name, i.indices) for i in r.issues] == [("SM_Tiled", [3])], r.issues
    assert r.issues[0].message == "UVs outside 0–1 on 1 face (UVMap)", r.issues


def _three_quads_with_uvs():
    """Quad 0 is normal, quad 1 is mirrored on top of quad 0, quad 2 is mirrored on its own."""
    quad = [(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0)]
    verts = quad + [(x + 2, y, z) for x, y, z in quad] + [(x + 4, y, z) for x, y, z in quad]
    obj = mesh_from("SM_Mirrored", verts, [(0, 1, 2, 3), (4, 5, 6, 7), (8, 9, 10, 11)])
    layer = obj.data.uv_layers.new(name="UVMap")
    normal = [(0, 0), (1, 0), (1, 1), (0, 1)]
    mirrored = [(1, 0), (0, 0), (0, 1), (1, 1)]
    apart = [(u + 2, v) for u, v in mirrored]
    for loop, uv in zip(range(12), normal + mirrored + apart):
        layer.data[loop].uv = uv
    return obj


@test
def flipped_uvs():
    fresh()
    cube()  # Blender's default cube UVs aren't flipped
    _three_quads_with_uvs()
    _, r = run("detect_flipped_uvs")
    assert [(i.object_name, i.indices) for i in r.issues] == [("SM_Mirrored", [2])], r.issues
    _, r = run("detect_flipped_uvs", allow_overlapping=False)
    assert r.issues[0].indices == [1, 2], r.issues


if __name__ == "__main__":
    main(globals())
