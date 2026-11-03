"""Tests for material and texture checks."""

import os
import sys

# Repo root first, so tests always import this checkout's vexa (not an installed copy).
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import bpy  # noqa: E402
from helpers import cube, fix, fresh, run, main, test  # noqa: E402


def _crate_with_textures():
    """A cube whose material has a missing image and a 1000x1000 normal map set to sRGB."""
    fresh()
    c = cube()
    mat = bpy.data.materials.new("M_Crate")
    if hasattr(mat, "use_nodes"):
        mat.use_nodes = True
    c.data.materials.append(mat)
    nt = mat.node_tree
    bsdf = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")
    tex_missing = nt.nodes.new("ShaderNodeTexImage")
    img = bpy.data.images.new("T_Gone", 4, 4)
    img.source = "FILE"
    img.filepath = "/nonexistent/T_Gone.png"
    tex_missing.image = img
    tex_n = nt.nodes.new("ShaderNodeTexImage")
    tex_n.image = bpy.data.images.new("T_Crate_N", 1000, 1000)
    tex_n.image.colorspace_settings.name = "sRGB"
    nmap = nt.nodes.new("ShaderNodeNormalMap")
    nt.links.new(tex_n.outputs["Color"], nmap.inputs["Color"])
    nt.links.new(nmap.outputs["Normal"], bsdf.inputs["Normal"])
    return c


@test
def missing_textures():
    _crate_with_textures()
    _, r = run("detect_missing_textures")
    assert r.status == "ERROR" and "T_Gone" in r.issues[0].message, r.issues


@test
def normal_map_in_srgb_is_flagged_and_fixed():
    _crate_with_textures()
    _, r = run("detect_color_space_issues")
    assert r.issues and r.issues[0].target == "Non-Color", r.issues
    _, r = fix("detect_color_space_issues")
    assert r.status == "PASS"


if __name__ == "__main__":
    main(globals())
