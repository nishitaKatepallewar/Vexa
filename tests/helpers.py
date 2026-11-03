"""Shared helpers for Vexa's headless tests.

Every test builds its own fixture in an empty scene, so no .blend files are needed.
Run a single file or everything:

    blender -b --factory-startup -P tests/run_all.py
    python tests/run_all.py            (with the `bpy` module from PyPI installed)
"""

import os
import sys
import traceback

import bpy

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from vexa import tools  # noqa: E402
from vexa.core import runner  # noqa: E402
from vexa.core.presets import Preset  # noqa: E402
from vexa.core.scope import build_scope  # noqa: E402

tools.import_all()  # register every tool, check and fix


def test(fn):
    """Marks a function as a test. Tests run in definition order."""
    fn.is_vexa_test = True
    return fn


def collect(namespace: dict) -> list:
    return [v for v in namespace.values() if callable(v) and getattr(v, "is_vexa_test", False)]


def run_tests(tests: list) -> int:
    """Runs tests, prints PASS/FAIL per test, returns the number of failures."""
    failed = 0
    for fn in tests:
        try:
            fn()
            print(f"PASS  {fn.__module__}.{fn.__name__}")
        except Exception:  # noqa: BLE001 - report every failure, keep going
            failed += 1
            print(f"FAIL  {fn.__module__}.{fn.__name__}")
            traceback.print_exc()
    print(f"\n{len(tests) - failed}/{len(tests)} passed on Blender {bpy.app.version_string}")
    return failed


def finish(failed: int) -> None:
    """Exits with 0 if everything passed, 1 otherwise.

    Uses os._exit after flushing output: Blender's Python module (pip `bpy`) can
    crash while the interpreter tears down after a run that registered the add-on,
    because Blender's own shutdown handling isn't installed in that mode. Every
    result has already been reported by this point, so skipping teardown is safe.
    """
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(1 if failed else 0)


def main(namespace: dict) -> None:
    finish(run_tests(collect(namespace)))


# ---------- fixtures ----------

def fresh():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    return bpy.context.scene


def one(check_id, **params):
    """A preset containing just one check."""
    return Preset(id="t", name="t", checks={check_id: dict(params)})


def run(check_id, objs=None, **params):
    preset = one(check_id, **params)
    objs = list(bpy.context.scene.objects) if objs is None else objs
    return preset, runner.run_preset(preset, objs)[0]


def fix(check_id, **params):
    """Runs a check on the whole scene, applies its fix, and returns (message, re-run result)."""
    _, res = run(check_id, **params)
    scope = build_scope(list(bpy.context.scene.objects))
    msg = runner.apply_fix(res, params, scope)
    return msg, run(check_id, **params)[1]


def cube(name="SM_Crate", size=2.0, loc=(0, 0, 0)):
    bpy.ops.mesh.primitive_cube_add(size=size, location=loc)
    obj = bpy.context.active_object
    obj.name = name
    return obj


def mesh_from(name, verts, faces):
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts, [], faces)
    me.update()
    obj = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(obj)
    return obj
