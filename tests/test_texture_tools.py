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


@test
def texture_sizes():
    _crate_with_textures()
    _, r = run("detect_invalid_texture_sizes")
    assert any("T_Crate_N" in i.message for i in r.issues), r.issues
    _, r = run("detect_invalid_texture_sizes", power_of_two=False)
    assert r.status == "PASS", r.issues


@test
def empty_slots():
    fresh()
    c = cube()
    c.data.materials.append(bpy.data.materials.new("M_Used"))
    c.data.materials.append(None)  # slot 1: no faces use it
    _, r = run("detect_unused_material_slots")
    assert r.status == "WARNING" and "1 unused" in r.issues[0].message, r.issues
    _, r = fix("detect_unused_material_slots")
    assert r.status == "PASS" and len(c.material_slots) == 1



@test
def textured_materials():
    _crate_with_textures()
    plain = cube("SM_Plain", loc=(5, 0, 0))
    plain.data.materials.append(bpy.data.materials.new("M_Plain"))
    _, r = run("detect_textured_materials")
    assert [(i.object_name, i.message, i.value) for i in r.issues] == \
        [("SM_Crate", "Textures on M_Crate", "2 image nodes")], r.issues


@test
def texture_format():
    c = _crate_with_textures()  # T_Gone.png on disk path, T_Crate_N generated
    mat = c.data.materials[0]
    tex = mat.node_tree.nodes.new("ShaderNodeTexImage")
    tex.image = bpy.data.images.new("T_Crate_D", 4, 4)
    tex.image.source = "FILE"
    tex.image.filepath = "//textures/T_Crate_D.JPG"
    _, r = run("detect_wrong_texture_format")
    assert [(i.message, i.target) for i in r.issues] == [("T_Crate_D: JPEG", "PNG")], r.issues
    _, r = run("detect_wrong_texture_format", formats=["png", "jpg"])
    assert r.status == "PASS", r.issues
    _, r = run("detect_wrong_texture_format", formats=["PNGG"])
    assert r.summary == "Check failed: unknown formats: PNGG", r.summary


@test
def unused_materials_detect_and_fix():
    fresh()
    c = cube()
    c.data.materials.append(bpy.data.materials.new("M_Used"))
    bpy.data.materials.new("M_Orphan")
    bpy.data.materials.new("M_Kept").use_fake_user = True
    _, r = run("detect_unused_materials")
    assert r.issues[0].message == "Unused materials: M_Kept, M_Orphan", r.issues
    msg, r = fix("detect_unused_materials")
    assert r.status == "PASS" and msg == "Removed 2 unused materials", (msg, r.summary)
    assert [m.name for m in bpy.data.materials] == ["M_Used"]


if __name__ == "__main__":
    main(globals())
