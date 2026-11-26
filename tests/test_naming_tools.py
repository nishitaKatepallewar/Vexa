"""Tests for naming checks."""

import os
import sys

# Repo root first, so tests always import this checkout's vexa (not an installed copy).
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import bpy  # noqa: E402
from vexa.core import runner  # noqa: E402
from vexa.core.scope import build_scope  # noqa: E402
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
def renaming_a_mesh_renames_its_collision_too():
    """Audit: with only the mesh selected, its UCX_ kept the old name and the link broke."""
    fresh()
    crate = cube("SM Crate")
    cube("UCX_SM Crate_01", size=2.1)
    cube("UCX_SM Crate_01.001", size=2.1)  # a duplicate, as Blender names it
    _, r = run("detect_invalid_name_characters", objs=[crate])
    assert r.fixable and r.fix_safe
    runner.apply_fix(r, {}, build_scope([crate]))
    names = sorted(o.name for o in bpy.data.objects)
    assert names == ["SM_Crate", "UCX_SM_Crate_01", "UCX_SM_Crate_02"], names
    _, r = run("detect_invalid_collision_meshes")
    assert r.status == "PASS", r.issues
    _, r = run("detect_missing_collision", objs=[crate])
    assert r.status == "PASS", r.issues


@test
def collision_is_left_if_its_mesh_is_not_checked():
    fresh()
    cube("SM Crate")
    col = cube("UCX_SM Crate_01", size=2.1)
    _, r = run("detect_invalid_name_characters", objs=[col])
    assert not r.fixable and "SM Crate isn't being checked" in r.issues[0].no_fix, r.issues
    _, r = run("detect_invalid_name_characters", objs=[cube("UCX_SM_Box_01.001", loc=(5, 0, 0))])
    assert r.fixable  # its mesh doesn't exist, so the name alone is fixed


@test
def prefix_added_and_collision_names_follow():
    fresh()
    cube("Crate")
    col = cube("UCX_Crate_01", size=2.1)
    _, r = run("detect_missing_name_prefix", prefix="SM_")
    assert [i.object_name for i in r.issues] == ["Crate"], r.issues  # collision ignored
    _, r = fix("detect_missing_name_prefix", prefix="SM_")
    assert r.status == "PASS" and col.name == "UCX_SM_Crate_01", col.name


@test
def skeletal_meshes_get_the_skeletal_prefix():
    """Audit: Add Name Prefix renamed a skeletal mesh to SM_SK_Body."""
    fresh()
    rig = bpy.data.objects.new("Rig", bpy.data.armatures.new("Rig"))
    bpy.context.scene.collection.objects.link(rig)
    for name, loc in (("SK_Body", (0, 0, 0)), ("Hair", (3, 0, 0))):
        cube(name, loc=loc).modifiers.new("Armature", "ARMATURE").object = rig
    cube("Crate", loc=(6, 0, 0))
    cube("UCX_Crate_01", loc=(6, 0, 0))
    cube("UCX_Crate2_01", loc=(9, 0, 0))  # belongs to another mesh, Crate2
    _, r = run("detect_missing_name_prefix")
    assert {i.object_name: i.message for i in r.issues} == {
        "Hair": "Missing SK_ prefix (skeletal mesh)", "Crate": "Missing SM_ prefix (mesh)"}, r.issues
    assert r.fix_safe
    msg, r = fix("detect_missing_name_prefix")
    assert r.status == "PASS", (msg, r.issues)
    names = sorted(o.name for o in bpy.data.objects)
    assert names == ["Rig", "SK_Body", "SK_Hair", "SM_Crate", "UCX_Crate2_01", "UCX_SM_Crate_01"], names
    _, r = run("detect_missing_name_prefix", skeletal_prefix="")
    assert r.status == "PASS"


if __name__ == "__main__":
    main(globals())
