"""Tests for UV checks."""

import os
import sys

# Repo root first, so tests always import this checkout's vexa (not an installed copy).
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from helpers import cube, fresh, mesh_from, run, main, test  # noqa: E402


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

if __name__ == "__main__":
    main(globals())
