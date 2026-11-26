"""Tests for transform checks."""

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
def transforms_detect_and_fix():
    fresh()
    c = cube()
    c.scale = (2, 2, 2)
    c.rotation_euler = (0.5, 0, 0)
    _, r = run("detect_unapplied_transforms")
    assert r.status == "ERROR" and r.fixable, r
    msg, r = fix("detect_unapplied_transforms")
    assert r.status == "PASS", (msg, r)


@test
def location_checked_only_when_asked():
    fresh()
    c = cube(loc=(3, 0, 1))
    _, r = run("detect_unapplied_transforms")
    assert r.status == "PASS", r.summary  # location is ignored by default
    _, r = run("detect_unapplied_transforms", check_location=True)
    assert r.status == "ERROR" and r.issues[0].message == "Not at world origin", r.issues
    c.scale = (2, 2, 2)
    _, r = run("detect_unapplied_transforms", check_location=True)
    assert r.issues[0].message == "Unapplied scale; not at world origin", r.issues
    msg, r = fix("detect_unapplied_transforms", check_location=True)
    assert r.status == "PASS", (msg, r.summary)
    assert c.location.length < 1e-6 and abs(c.dimensions.x - 4.0) < 1e-5  # moved, scale applied


@test
def negative_scale_not_auto_fixed():
    fresh()
    c = cube()
    c.scale = (-1, 1, 1)
    _, r = run("detect_negative_scale")
    assert r.status == "ERROR" and not r.fixable
    _, t = run("detect_unapplied_transforms")
    assert not t.fixable and "negative" in t.issues[0].no_fix, t.issues
    assert runner.apply_fix(t, {}, build_scope([c])) == "Nothing to fix"


def _world_verts(obj):
    bpy.context.view_layer.update()
    ev = obj.evaluated_get(bpy.context.evaluated_depsgraph_get())
    return sorted(tuple(round(c, 4) for c in obj.matrix_world @ v.co) for v in ev.data.vertices)


@test
def apply_transforms_moves_an_assembly_as_one_piece():
    """Audit: with 'at the world origin', every part moved to 0,0,0 (1.95 m apart -> 0)."""
    fresh()
    body = cube("SM_Cart", loc=(5, 2, 0))
    body.scale = (2, 1, 1)
    wheel = cube("SM_Wheel", size=0.5, loc=(6.95, 2, -0.5))
    wheel.parent = body
    wheel.matrix_parent_inverse = body.matrix_world.inverted()
    cube("UCX_SM_Cart_01", loc=(5, 2, 0)).scale = (2, 1, 1)
    gap = (wheel.matrix_world.translation - body.matrix_world.translation).length
    _, r = run("detect_unapplied_transforms", check_location=True)
    assert "SM_Wheel" not in [i.object_name for i in r.issues], r.issues  # placed by its parent
    msg, r = fix("detect_unapplied_transforms", check_location=True)
    bpy.context.view_layer.update()
    assert body.location.length < 1e-6 and abs(body.dimensions.x - 4) < 1e-5, (msg, body.location)
    assert abs((wheel.matrix_world.translation - body.matrix_world.translation).length - gap) < 1e-5, msg
    ucx = bpy.data.objects["UCX_SM_Cart_01"]
    assert ucx.location.length < 1e-6 and abs(ucx.dimensions.x - 4) < 1e-5, msg  # moved and applied too
    assert "moved SM_Cart to the origin with 1 collision meshes" in msg, msg


@test
def apply_transforms_never_moves_separate_assets_onto_each_other():
    fresh()
    cube("SM_Crate", loc=(3, 0, 0))
    cube("SM_Barrel", loc=(-3, 0, 0))
    _, r = run("detect_unapplied_transforms", check_location=True)
    assert not r.fixable and all("several separate assets" in i.no_fix for i in r.issues), r.issues
    assert bpy.data.objects["SM_Crate"].location.x == 3


@test
def apply_transforms_leaves_objects_whose_look_would_change():
    """Audit: applying scale under a Bevel changed the bevel (4.80 -> 5.60)."""
    fresh()
    bevel = cube("SM_Bevel")
    bevel.scale = (2, 2, 2)
    bevel.modifiers.new("Bevel", "BEVEL").width = 0.2
    normals = cube("SM_Normals", loc=(5, 0, 0))
    normals.scale = (1, 1, 3)
    if hasattr(normals.data, "use_auto_smooth"):  # Blender 4.0
        normals.data.use_auto_smooth = True
    normals.data.normals_split_custom_set([(0.6, 0, 0.8)] * len(normals.data.loops))
    animated = cube("SM_Animated", loc=(10, 0, 0))
    animated.scale = (2, 2, 2)
    animated.keyframe_insert("scale", frame=1)
    smooth = cube("SM_Smooth", loc=(15, 0, 0))
    smooth.scale = (2, 2, 2)
    smooth.modifiers.new("Subdivision", "SUBSURF")
    before = {o.name: _world_verts(o) for o in bpy.context.scene.objects}
    _, r = run("detect_unapplied_transforms")
    reasons = {i.object_name: i.no_fix for i in r.issues}
    assert "Bevel" in reasons["SM_Bevel"] and "custom normals" in reasons["SM_Normals"], reasons
    assert "animated" in reasons["SM_Animated"] and reasons["SM_Smooth"] == "", reasons
    msg, r = fix("detect_unapplied_transforms")
    assert msg.startswith("Applied transforms on 1 objects. Left for you:"), msg
    assert smooth.scale.x == 1 and _world_verts(smooth) == before["SM_Smooth"]  # same shape, applied
    for name in ("SM_Bevel", "SM_Normals", "SM_Animated"):
        assert _world_verts(bpy.data.objects[name]) == before[name], name


@test
def pivot_and_unit_scale():
    fresh()
    c = cube(size=2.0)
    _, r = run("detect_off_center_pivots")
    assert r.status == "WARNING" and "1.000" in r.summary, r.summary
    _, r = fix("detect_off_center_pivots")
    assert r.status == "PASS", r.summary
    assert abs(min(v.co.z for v in c.data.vertices)) < 1e-5
    bpy.context.scene.unit_settings.scale_length = 0.01
    _, r = run("detect_wrong_unit_scale", scale_length=1.0)
    assert r.status == "WARNING"
    _, r = fix("detect_wrong_unit_scale", scale_length=1.0)
    assert r.status == "PASS"


def _real(v):
    return round(v * bpy.context.scene.unit_settings.scale_length, 4)


@test
def set_units_keeps_the_real_size():
    """Audit: changing 1.0 to 0.01 without rescaling exported a 2 m crate as 2 cm."""
    import os
    import tempfile
    fresh()
    crate = cube("SM_Crate", size=2.0, loc=(3, 0, 0))
    crate.modifiers.new("Bevel", "BEVEL").width = 0.1
    lid = cube("SM_Lid", size=1.0, loc=(3, 0, 1.5))
    lid.parent = crate
    lid.matrix_parent_inverse = crate.matrix_world.inverted()
    def shape(obj):  # the evaluated mesh, in real-world metres
        bpy.context.view_layer.update()
        ev = obj.evaluated_get(bpy.context.evaluated_depsgraph_get())
        return sorted(tuple(_real(c) for c in obj.matrix_world @ v.co) for v in ev.data.vertices)

    before = shape(crate)
    _, r = run("detect_wrong_unit_scale", scale_length=0.01)
    assert r.fixable and not r.fix_safe
    msg, r = fix("detect_wrong_unit_scale", scale_length=0.01)
    assert r.status == "PASS", (msg, r.summary)
    assert shape(crate) == before  # same size, place and bevel in metres
    assert _real(crate.dimensions.x) == 2.0, crate.dimensions
    assert _real((lid.matrix_world.translation - crate.matrix_world.translation).z) == 1.5
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "crate.fbx")
        bpy.ops.export_scene.fbx(filepath=path, use_selection=False)
        fresh()
        bpy.ops.import_scene.fbx(filepath=path)
        crate = bpy.data.objects["SM_Crate"]
        assert round(crate.dimensions.x, 3) == 2.0, crate.dimensions  # still 2 m in the FBX


@test
def set_units_leaves_animated_scenes_alone():
    fresh()
    crate = cube()
    crate.keyframe_insert("location", frame=1)
    bpy.context.scene.unit_settings.system_rotation = "RADIANS"
    _, r = run("detect_wrong_unit_scale", scale_length=0.01, rotation_unit="DEGREES")
    scale_issue = next(i for i in r.issues if "scale" in i.message)
    assert "animated" in scale_issue.no_fix and r.fixable, r.issues  # rotation unit can still be fixed
    msg, r = fix("detect_wrong_unit_scale", scale_length=0.01, rotation_unit="DEGREES")
    units = bpy.context.scene.unit_settings
    assert units.scale_length == 1.0 and units.system_rotation == "DEGREES", msg
    assert "animated" in msg and abs(crate.scale.x - 1.0) < 1e-6, msg


@test
def length_and_rotation_units():
    fresh()
    units = bpy.context.scene.unit_settings
    cm = dict(scale_length=0.01, length_unit="CENTIMETERS", rotation_unit="DEGREES")
    units.system_rotation = "RADIANS"
    _, r = run("detect_wrong_unit_scale", **cm)
    assert len(r.issues) == 3, r.issues  # scale, length and rotation
    msg, r = fix("detect_wrong_unit_scale", **cm)
    assert r.status == "PASS", (msg, r.issues)
    assert abs(units.scale_length - 0.01) < 1e-6
    assert (units.length_unit, units.system_rotation) == ("CENTIMETERS", "DEGREES")
    _, r = run("detect_wrong_unit_scale", scale_length=0.01)
    assert r.status == "PASS"  # units are only checked when asked
    _, r = run("detect_wrong_unit_scale", length_unit="CENTIMETRES")
    assert r.summary.startswith("Check failed: length_unit must be one of"), r.summary


if __name__ == "__main__":
    main(globals())
