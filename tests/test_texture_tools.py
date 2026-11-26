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
def missing_textures_inside_groups_and_unsaved_bakes():
    """Audit: a missing image inside a node group, and a bake never saved, both passed."""
    import tempfile
    fresh()
    c = cube()
    mat = bpy.data.materials.new("M_Crate")
    if mat.node_tree is None:
        mat.use_nodes = True
    c.data.materials.append(mat)
    group = bpy.data.node_groups.new("Wear", "ShaderNodeTree")
    gone = bpy.data.images.new("T_Wear", 4, 4)
    gone.source, gone.filepath = "FILE", "/nonexistent/T_Wear.png"
    group.nodes.new("ShaderNodeTexImage").image = gone
    mat.node_tree.nodes.new("ShaderNodeGroup").node_tree = group
    mat.node_tree.nodes.new("ShaderNodeTexImage").image = bpy.data.images.new("T_Bake_AO", 8, 8)
    with tempfile.TemporaryDirectory() as d:
        saved = bpy.data.images.new("T_Saved", 8, 8)
        saved.filepath_raw, saved.file_format = os.path.join(d, "T_Saved.png"), "PNG"
        saved.save()
        saved.source = "FILE"
        saved.reload()
        mat.node_tree.nodes.new("ShaderNodeTexImage").image = saved
        _, r = run("detect_missing_textures")
        assert r.issues[0].message == ("Missing: M_Crate: T_Wear, M_Crate: T_Bake_AO (made in Blender and "
                                       "never saved)"), r.issues
        saved.pixels[0] = 0.5  # painted or baked into, not saved yet
        _, r = run("detect_missing_textures")
        assert "T_Saved (has unsaved changes)" in r.issues[0].message, r.issues


@test
def normal_map_in_srgb_is_flagged_and_fixed():
    _crate_with_textures()
    _, r = run("detect_color_space_issues")
    assert r.issues and r.issues[0].target == "Non-Color", r.issues
    _, r = fix("detect_color_space_issues")
    assert r.status == "PASS"


@test
def color_space_leaves_float_and_dual_use_images():
    c = _crate_with_textures()
    nt = c.data.materials[0].node_tree
    bsdf = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")
    hdr = nt.nodes.new("ShaderNodeTexImage")
    hdr.image = bpy.data.images.new("T_Albedo_EXR", 4, 4, float_buffer=True)
    hdr.image.colorspace_settings.name = "Linear Rec.709"  # right for a float colour map
    nt.links.new(hdr.outputs["Color"], bsdf.inputs["Base Color"])
    _, r = run("detect_color_space_issues")
    assert [i.value for i in r.issues] == ["T_Crate_N"], r.issues  # the EXR isn't flagged

    # T_Crate_N also feeds Roughness in another material, set up as colour there.
    other = bpy.data.materials.new("M_Other")
    if other.node_tree is None:
        other.use_nodes = True
    node = other.node_tree.nodes.new("ShaderNodeTexImage")
    node.image = bpy.data.images["T_Crate_N"]
    other_bsdf = next(n for n in other.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
    other.node_tree.links.new(node.outputs["Color"], other_bsdf.inputs["Base Color"])
    _, r = run("detect_color_space_issues")
    assert not r.fixable and r.issues[0].no_fix == "used both as a colour map and as a data map", r.issues
    fix("detect_color_space_issues")
    assert bpy.data.images["T_Crate_N"].colorspace_settings.name == "sRGB"


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
def unused_slots_fixed_on_objects_that_arent_selected():
    # Scope "Scene" or "Collection" checks objects the artist hasn't selected.
    fresh()
    c = cube()
    for name in ("M_A", None, "M_B"):
        c.data.materials.append(bpy.data.materials.new(name) if name else None)
    other = cube("SM_Other", loc=(5, 0, 0))
    bpy.ops.object.select_all(action="DESELECT")
    other.select_set(True)
    bpy.context.view_layer.objects.active = other
    msg, r = fix("detect_unused_material_slots")
    assert msg == "Removed 2 unused slots" and r.status == "PASS", (msg, r.summary)
    assert [s.material.name for s in c.material_slots] == ["M_A"]
    # The artist's selection is left as it was.
    assert [o.name for o in bpy.context.selected_objects] == ["SM_Other"]
    assert bpy.context.view_layer.objects.active == other


@test
def unused_slots_skipped_on_objects_outside_the_view_layer():
    fresh()
    hidden = bpy.data.collections.new("Excluded")
    bpy.context.scene.collection.children.link(hidden)
    c = cube()
    bpy.context.scene.collection.objects.unlink(c)
    hidden.objects.link(c)
    c.data.materials.append(bpy.data.materials.new("M_A"))
    c.data.materials.append(None)
    bpy.context.view_layer.layer_collection.children["Excluded"].exclude = True
    msg, r = fix("detect_unused_material_slots")
    assert msg == "Nothing to fix" and r.issues[0].no_fix == "not in the view layer", (msg, r.issues)
    assert len(c.material_slots) == 2


@test
def slots_a_modifier_uses_are_kept():
    """Blender's Remove Unused Slots deletes a slot only a Solidify rim uses (4.2 and 5.2)."""
    fresh()
    bpy.ops.mesh.primitive_plane_add()
    plane = bpy.context.active_object
    for name in ("M_Face", "M_Rim"):
        plane.data.materials.append(bpy.data.materials.new(name))
    solidify = plane.modifiers.new("Solidify", "SOLIDIFY")
    solidify.use_rim, solidify.material_offset_rim = True, 1
    _, r = run("detect_unused_material_slots")
    assert r.status == "PASS", r.issues  # the exported mesh's rim uses M_Rim
    # A slot nothing uses, before the rim's: removing it would shift the rim's offset.
    plane.data.materials.append(bpy.data.materials.new("M_Rim2"))
    solidify.material_offset_rim = 2
    _, r = run("detect_unused_material_slots")
    assert r.issues[0].message == "Material slots: 1 unused", r.issues
    assert not r.fixable and "Solidify" in r.issues[0].no_fix, r.issues
    fix("detect_unused_material_slots")
    assert [s.material.name for s in plane.material_slots] == ["M_Face", "M_Rim", "M_Rim2"]



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
def too_many_materials():
    fresh()
    c = cube()
    for name in ("M_Wood", "M_Metal", "M_Spare"):
        c.data.materials.append(bpy.data.materials.new(name))
    for p in c.data.polygons:
        p.material_index = 0 if p.index < 3 else 1  # M_Spare is in a slot but unused
    single = cube("SM_Single", loc=(5, 0, 0))
    single.data.materials.append(bpy.data.materials.new("M_One"))
    _, r = run("detect_too_many_materials")
    assert [(i.object_name, i.message) for i in r.issues] == [("SM_Crate", "2 materials: M_Metal, M_Wood")], r.issues
    _, r = run("detect_too_many_materials", max_materials=2)
    assert r.status == "PASS", r.issues


@test
def unused_materials_detect_and_fix():
    fresh()
    c = cube()
    c.data.materials.append(bpy.data.materials.new("M_Used"))
    bpy.data.materials.new("M_Orphan")
    bpy.data.materials.new("M_Kept").use_fake_user = True
    bpy.data.materials.create_gpencil_data(bpy.data.materials.new("GP_Stroke"))
    _, r = run("detect_unused_materials")
    assert r.issues[0].message == "Unused materials: M_Orphan", r.issues  # a fake user means keep it
    msg, r = fix("detect_unused_materials")
    assert r.status == "PASS" and msg == "Removed 1 unused materials", (msg, r.summary)
    # Audit: the fix deleted M_Kept. Blender's Purge keeps fake users, so Vexa does too.
    assert sorted(m.name for m in bpy.data.materials) == ["GP_Stroke", "M_Kept", "M_Used"]


if __name__ == "__main__":
    main(globals())
