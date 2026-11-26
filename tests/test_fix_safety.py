"""No fix may create a new problem.

Every fix runs on every test scene. Before and after, every check runs with its
default settings; no check may get worse (runner.new_problems). Fixes that need
the artist's confirmation may only cause what their dialog warns about, listed in
CONFIRMED_SIDE_EFFECTS with the words from the dialog that cover it.
"""

import os
import sys

# Repo root first, so tests always import this checkout's vexa (not an installed copy).
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import bpy  # noqa: E402
import bmesh  # noqa: E402  (after bpy: the pip bpy module provides bmesh)

from helpers import cube, fresh, main, mesh_from, test  # noqa: E402
from test_check_snapshot import SCENES  # noqa: E402
from vexa.core import runner  # noqa: E402
from vexa.core.presets import Preset  # noqa: E402
from vexa.core.registry import CHECK, FIX, AgentTools  # noqa: E402
from vexa.core.scope import build_scope, excluded_collections, is_exported  # noqa: E402

# fix -> {check title it may make worse: words in its confirm text that warn about it}
CONFIRMED_SIDE_EFFECTS = {
    "set_unit_scale": {"Unapplied Transforms": "Apply Transforms can apply afterwards"},
    "apply_negative_scale": {"Flipped UVs": "Flipped UVs may flag those faces"},
}


def scene_workflow():
    """What artists' files contain that the other scenes don't: modifiers, assemblies,
    collision for a renamed mesh, a skinned mesh, an interior, a used vertex mask."""
    fresh()
    half = cube("SM Half")  # invalid name, with collision to rename along
    bm = bmesh.new()
    bm.from_mesh(half.data)
    bmesh.ops.bisect_plane(bm, geom=bm.verts[:] + bm.edges[:] + bm.faces[:], plane_co=(0, 0, 0),
                           plane_no=(1, 0, 0), clear_inner=True)
    bm.to_mesh(half.data)
    bm.free()
    half.modifiers.new("Mirror", "MIRROR")
    cube("UCX_SM Half_01", size=2.1)
    cart = cube("SM_Cart", loc=(6, 0, 0))
    cart.scale = (2, 1, 1)
    cart.modifiers.new("Bevel", "BEVEL").width = 0.1
    wheel = cube("SM_Wheel", size=0.5, loc=(7.9, 0, -0.5))
    wheel.parent = cart
    wheel.matrix_parent_inverse = cart.matrix_world.inverted()
    wheel.scale = (1, 1, 1.5)
    room = cube("SM_Room", size=6, loc=(20, 0, 0))
    bm = bmesh.new()
    bm.from_mesh(room.data)
    bmesh.ops.reverse_faces(bm, faces=bm.faces[:])
    bm.to_mesh(room.data)
    bm.free()
    painted = cube("SM_Painted", loc=(30, 0, 0))
    painted.data.color_attributes.new("Mask", "BYTE_COLOR", "CORNER")
    painted.data.color_attributes.new("Junk", "BYTE_COLOR", "CORNER")
    mat = bpy.data.materials.new("M_Painted")
    if mat.node_tree is None:
        mat.use_nodes = True
    mat.node_tree.nodes.new("ShaderNodeVertexColor").layer_name = "Mask"
    painted.data.materials.append(mat)
    painted.data.materials.append(bpy.data.materials.new("M_Spare"))
    bpy.data.materials.new("M_Library").use_fake_user = True
    rig = bpy.data.objects.new("Rig", bpy.data.armatures.new("Rig"))
    bpy.context.scene.collection.objects.link(rig)
    body = cube("Body", loc=(40, 0, 0))
    body.modifiers.new("Armature", "ARMATURE").object = rig
    body.scale = (1.5, 1.5, 1.5)
    mesh_from("SM_Bent", [(50, 0, 0), (51, 0, 0), (51, 1, 0.6), (50, 1, 0)], [(0, 1, 2, 3)])
    bpy.ops.object.light_add(type="POINT", location=(0, 0, 10))


def scene_moved_project():
    """A saved project whose textures were linked from another machine."""
    import atexit
    import shutil
    import tempfile
    fresh()
    folder = tempfile.mkdtemp(prefix="vexa_project_")
    atexit.register(shutil.rmtree, folder, True)
    os.makedirs(os.path.join(folder, "textures"))
    crate = cube("SM_Crate")
    mat = bpy.data.materials.new("M_Crate")
    if mat.node_tree is None:
        mat.use_nodes = True
    crate.data.materials.append(mat)
    pixels = bpy.data.images.new("px", 4, 4)
    pixels.filepath_raw, pixels.file_format = os.path.join(folder, "textures", "T_Crate_D.png"), "PNG"
    pixels.save()
    bpy.data.images.remove(pixels)
    image = bpy.data.images.new("T_Crate_D.png", 4, 4)
    image.source, image.filepath = "FILE", "/old/machine/T_Crate_D.png"
    mat.node_tree.nodes.new("ShaderNodeTexImage").image = image
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(folder, "crate.blend"))


ALL_SCENES = dict(SCENES, workflow=scene_workflow, moved_project=scene_moved_project)


def _everything() -> Preset:
    """Every check with its defaults, except where two defaults contradict: the lightmap
    check wants UV1, so the UV map limit allows it."""
    checks = {c.name: {} for c in AgentTools.all(CHECK)}
    checks["detect_extra_uv_maps"] = {"max_uv_maps": 2}
    return Preset(id="all", name="All checks", checks=checks)


def _objects() -> list:
    excluded = excluded_collections(bpy.context.view_layer)
    return [o for o in bpy.context.scene.objects if is_exported(o, excluded)]


_RUNS = []


def _runs():
    """(fix, scene, new problems, own size before, own size after) for every fix that had
    something to fix in a scene; the size after is -1 if nothing the fix may change is
    left. Computed once for all the tests."""
    if _RUNS:
        return _RUNS
    preset = _everything()
    for fix in AgentTools.all(FIX):
        for scene_name, build in ALL_SCENES.items():
            build()
            before = runner.run_preset(preset, _objects())
            result = next(r for r in before if r.check_id == fix.fix.check)
            if not result.fixable:
                continue
            runner.apply_fix(result, preset.settings(fix.fix.check), build_scope(_objects()))
            after = runner.run_preset(preset, _objects())
            own = next(r for r in after if r.check_id == fix.fix.check)
            _RUNS.append((fix, scene_name, runner.new_problems(before, after), result.size,
                          own.size if own.fixable else -1))  # -1: nothing it may fix is left
    return _RUNS


def _side_effects():
    return [(fix, scene, worse) for fix, scene, worse, _, _ in _runs() if worse]


@test
def every_fix_does_all_it_can_or_makes_its_problem_smaller():
    stuck = [f"{fix.display_name} on '{scene}': {before:g} -> {after:g}"
             for fix, scene, _, before, after in _runs() if not after < before]
    assert not stuck, "\n" + "\n".join(stuck)
    assert {fix.name for fix, *_ in _runs()} == {f.name for f in AgentTools.all(FIX)}, "a fix never ran"


@test
def no_fix_creates_a_new_problem():
    failures = []
    for fix, scene_name, worse in _side_effects():
        allowed = CONFIRMED_SIDE_EFFECTS.get(fix.name, {}) if not fix.fix.safe else {}
        unexpected = [w for w in worse if not any(w.startswith(title + " (") for title in allowed)]
        if unexpected:
            failures.append(f"{fix.display_name} on '{scene_name}' made worse: {'; '.join(unexpected)}")
    assert not failures, "\n" + "\n".join(failures)


@test
def side_effects_allowed_here_are_in_the_fixes_own_warning():
    for name, effects in CONFIRMED_SIDE_EFFECTS.items():
        fix = AgentTools.get(name)
        assert not fix.fix.safe, f"{name} is safe, so it may have no side effects"
        for title, words in effects.items():
            assert words in fix.fix.confirm, f"{name}'s dialog doesn't warn about {title}"


if __name__ == "__main__":
    main(globals())
