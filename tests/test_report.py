"""Tests for core/report.py: what a report contains and how it's saved."""

import json
import os
import sys
import tempfile

# Repo root first, so tests always import this checkout's vexa (not an installed copy).
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import bpy  # noqa: E402

from vexa.core import report, runner  # noqa: E402
from vexa.core.presets import get_preset  # noqa: E402
from helpers import cube, fresh, main, test  # noqa: E402


def _run():
    fresh()
    c = cube("Crate")
    c.scale = (2, 2, 2)
    preset = get_preset("unity_asset_store")
    return preset, runner.run_preset(preset, list(bpy.context.scene.objects))


@test
def report_has_verdict_counts_and_versions():
    preset, results = _run()
    data = report.report_dict(preset, results, "SCENE")
    assert data["status"] == "ERROR" and data["counts"]["ERROR"] >= 1
    assert data["preset"]["id"] == "unity_asset_store" and data["scope"] == "SCENE"
    assert data["vexa"].count(".") == 2 and data["blender"] == bpy.app.version_string
    assert sum(data["counts"].values()) == len(data["results"])


@test
def each_result_says_why_it_matters():
    preset, results = _run()
    data = report.report_dict(preset, results)
    transforms = next(r for r in data["results"] if r["check"] == "detect_unapplied_transforms")
    assert transforms["why"] and transforms["issues"][0]["object_name"] == "Crate"


@test
def json_report_round_trips():
    preset, results = _run()
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "r.json")
        report.write_report(path, preset, results)
        with open(path, encoding="utf-8") as f:
            assert json.load(f)["results"][0]["check"] in preset.checks


if __name__ == "__main__":
    main(globals())
