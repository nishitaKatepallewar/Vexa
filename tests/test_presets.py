"""Tests that every built-in preset loads, refers to real checks, and runs."""

import os
import sys

# Repo root first, so tests always import this checkout's vexa (not an installed copy).
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import tempfile  # noqa: E402

import bpy  # noqa: E402

from vexa.core import runner  # noqa: E402
from vexa.core.presets import load_presets  # noqa: E402
from vexa.core.registry import AgentTools  # noqa: E402
from helpers import cube, fresh, main, test  # noqa: E402


@test
def every_builtin_preset_runs():
    fresh()
    cube()
    cube("UCX_SM_Crate_01")
    presets = load_presets()
    assert {p.id for p in presets} >= {"general", "unity_asset_store", "fab", "unreal"}
    for p in presets:
        for cid in p.checks:
            assert AgentTools.get_check(cid), f"{p.id} refers to unknown check {cid}"
            runner.check_settings(cid, p.settings(cid))  # raises on an unknown setting
        results = runner.run_preset(p, list(bpy.context.scene.objects))
        assert all(not r.summary.startswith("Check failed") for r in results), [r.summary for r in results]
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "report.json")
        runner.write_report(path, presets[0], results)
        assert os.path.getsize(path) > 100

if __name__ == "__main__":
    main(globals())
