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
def negative_scale_not_auto_fixed():
    fresh()
    c = cube()
    c.scale = (-1, 1, 1)
    _, r = run("detect_negative_scale")
    assert r.status == "ERROR" and not r.fixable
    _, t = run("detect_unapplied_transforms")
    msg = runner.apply_fix(t, {}, build_scope([c]))
    assert "Skipped" in msg and "negative" in msg, msg


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

if __name__ == "__main__":
    main(globals())
