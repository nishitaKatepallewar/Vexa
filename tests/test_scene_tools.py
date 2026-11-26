"""Tests for scene checks."""

import os
import sys

# Repo root first, so tests always import this checkout's vexa (not an installed copy).
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import bpy  # noqa: E402

from vexa.core import runner  # noqa: E402
from vexa.core.scope import build_scope, excluded_collections, is_exported  # noqa: E402
from helpers import cube, fresh, run, main, test  # noqa: E402


@test
def unwanted_objects():
    fresh()
    cube()
    cube("UCX_SM_Crate_01")
    bpy.ops.object.camera_add()
    bpy.ops.object.light_add(type="POINT")
    bpy.ops.object.empty_add()
    bpy.context.active_object.name = "SOCKET_Handle"
    _, r = run("detect_unwanted_objects")
    found = sorted(i.message for i in r.issues)
    assert r.status == "WARNING" and found == ["Unwanted camera", "Unwanted light"], found
    _, r = run("detect_unwanted_objects", allowed_types=["MESH", "CAMERA", "LIGHT"])
    assert r.status == "PASS", r.issues
    _, r = run("detect_unwanted_objects", allowed_types=["MESH", "CAMRA"])
    assert r.summary == "Check failed: unknown object types: CAMRA", r.summary



def _exported():
    excluded = excluded_collections(bpy.context.view_layer)
    return [o for o in bpy.context.scene.objects if is_exported(o, excluded)]


@test
def unwanted_objects_move_out_of_the_export_and_nothing_is_deleted():
    import os
    import tempfile
    fresh()
    crate = cube()
    bpy.ops.object.camera_add()
    bpy.ops.object.light_add(type="POINT", location=(0, 0, 5))
    lamp = bpy.context.active_object
    bpy.ops.object.empty_add()
    holder = bpy.context.active_object
    crate.parent = holder  # an empty holding the asset: moving it would orphan the crate
    _, r = run("detect_unwanted_objects", objs=_exported())
    assert r.fix_safe and [i.object_name for i in r.issues if i.no_fix] == [holder.name], r.issues
    message = runner.apply_fix(r, {}, build_scope(_exported()))
    assert message.startswith("Moved 2 objects to 'Not for export'"), message
    assert len(bpy.data.objects) == 4 and lamp.name in bpy.data.collections["Not for export"].objects
    _, r = run("detect_unwanted_objects", objs=_exported())
    assert [i.object_name for i in r.issues] == [holder.name], r.issues
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "crate.fbx")
        bpy.ops.export_scene.fbx(filepath=path)
        fresh()
        bpy.ops.import_scene.fbx(filepath=path)
        assert sorted(o.type for o in bpy.context.scene.objects) == ["EMPTY", "MESH"]


if __name__ == "__main__":
    main(globals())
