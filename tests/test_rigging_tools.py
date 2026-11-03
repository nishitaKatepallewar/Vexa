"""Tests for rigging checks."""

import os
import sys

# Repo root first, so tests always import this checkout's vexa (not an installed copy).
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import bpy  # noqa: E402
from helpers import cube, fresh, run, main, test  # noqa: E402


@test
def bone_influences():
    fresh()
    c = cube()
    arm_data = bpy.data.armatures.new("Rig")
    arm = bpy.data.objects.new("Rig", arm_data)
    bpy.context.scene.collection.objects.link(arm)
    bpy.context.view_layer.objects.active = arm
    bpy.ops.object.mode_set(mode="EDIT")
    for i in range(6):
        b = arm_data.edit_bones.new(f"B{i}")
        b.head, b.tail = (0, 0, i), (0, 0, i + 1)
    bpy.ops.object.mode_set(mode="OBJECT")
    mod = c.modifiers.new("Armature", "ARMATURE")
    mod.object = arm
    for i in range(6):
        vg = c.vertex_groups.new(name=f"B{i}")
        vg.add([0], 0.2, "REPLACE")
    _, r = run("detect_excess_bone_influences", max_influences=4)
    assert r.status == "WARNING" and r.issues[0].indices == [0], r.issues
    _, r = run("detect_excess_bone_influences", max_influences=8)
    assert r.status == "PASS"

if __name__ == "__main__":
    main(globals())
