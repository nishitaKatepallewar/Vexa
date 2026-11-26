"""Tests for presets and the runner, using throwaway checks."""

import json
import os
import sys
import tempfile

# Repo root first, so tests always import this checkout's vexa (not an installed copy).
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import bpy  # noqa: E402

from vexa.core import presets, runner  # noqa: E402
from vexa.core.presets import Preset, get_preset, load_presets  # noqa: E402
from vexa.core.registry import AgentTools  # noqa: E402
from vexa.core.results import Issue  # noqa: E402
from vexa.core.scope import build_scope, current  # noqa: E402
from helpers import cube, fresh, main, test  # noqa: E402

TEMP = ("_t_flag_all", "_t_fix_all", "_t_broken")


class temporary_checks:
    def __enter__(self):
        @AgentTools.register_check(display_name="Flag all", category="Test", why="Test only.",
                                   pass_text="Fine")
        def _t_flag_all(limit: int = 1) -> list:
            return [Issue(o.name, "flagged", value=str(limit)) for o in current().meshes]

        @AgentTools.register_fix("_t_flag_all", safe=True)
        def _t_fix_all(issues) -> str:
            return f"fixed {len(issues)}"

        @AgentTools.register_check(display_name="Broken", category="Test", why="Test only.")
        def _t_broken() -> list:
            raise RuntimeError("boom")

        return self

    def __exit__(self, *exc):
        for name in TEMP:
            AgentTools._tools.pop(name, None)
        return False


@test
def settings_overlay_defaults_and_reject_typos():
    with temporary_checks():
        assert runner.check_settings("_t_flag_all") == {"limit": 1}
        assert runner.check_settings("_t_flag_all", {"limit": 5}) == {"limit": 5}
        try:
            runner.check_settings("_t_flag_all", {"limt": 5})
        except ValueError as e:
            assert "limt" in str(e)
        else:
            raise AssertionError("expected ValueError for an unknown setting")


@test
def statuses_failures_and_unknown_checks():
    fresh()
    cube("SM_A")
    with temporary_checks():
        preset = Preset(id="p", name="p", checks={
            "_t_flag_all": {"severity": "error", "limit": 3}, "_t_broken": {}, "_t_missing": {}})
        results = {r.check_id: r for r in runner.run_preset(preset, list(bpy.context.scene.objects))}
        flag = results["_t_flag_all"]
        assert flag.status == "ERROR" and flag.fixable and flag.issues[0].value == "3"
        assert results["_t_broken"].summary.startswith("Check failed"), results["_t_broken"].summary
        assert results["_t_missing"].summary.startswith("Unknown check")
        scope = build_scope(list(bpy.context.scene.objects))
        assert runner.apply_fix(flag, preset.settings("_t_flag_all"), scope) == "fixed 1"


@test
def pass_text_when_no_issues():
    fresh()
    with temporary_checks():
        result = runner.run_preset(Preset(id="p", name="p", checks={"_t_flag_all": {}}), [])[0]
        assert result.status == "PASS" and result.summary == "Fine" and not result.fixable


@test
def collision_meshes_are_separated():
    fresh()
    cube("SM_A")
    cube("UCX_SM_A_01")
    scope = build_scope(list(bpy.context.scene.objects))
    assert [o.name for o in scope.meshes] == ["SM_A"]
    assert [o.name for o in scope.collision] == ["UCX_SM_A_01"]


@test
def team_presets_folder_overrides_by_id():
    with tempfile.TemporaryDirectory() as d:
        with open(os.path.join(d, "studio.json"), "w") as f:
            json.dump({"id": "acme", "name": "Acme", "checks": {"detect_over_triangle_budget": {"max_tris": 10}}}, f)
        load_presets([d])
        assert get_preset("acme").settings("detect_over_triangle_budget") == {"max_tris": 10}
    load_presets()
    assert get_preset("acme") is None


@test
def loading_with_no_preset_files_is_empty_not_recursive():
    original = presets.BUILTIN_DIR
    with tempfile.TemporaryDirectory() as d:
        presets.BUILTIN_DIR = d
        try:
            assert load_presets() == [] and presets.all_presets() == []
            assert get_preset("general") is None
        finally:
            presets.BUILTIN_DIR = original
            load_presets()


@test
def new_problems_lists_checks_that_got_worse():
    from vexa.core.results import CheckResult

    def res(check, status, faces=0, others=0):
        issues = [Issue("A", "x", element="FACE", indices=list(range(faces)))] if faces else []
        issues += [Issue("A", "y") for _ in range(others)]
        return CheckResult(check, check.title(), status, f"{faces + others} issues", issues=issues,
                           size=faces + others)

    before = [res("ngons", "WARNING", faces=4), res("normals", "PASS"), res("names", "WARNING", others=1),
              res("budget", "WARNING", others=1)]
    after = [res("ngons", "PASS"), res("normals", "ERROR", faces=2), res("names", "WARNING", others=2),
             res("budget", "ERROR", others=1), res("new_check", "ERROR", others=3)]
    assert runner.new_problems(before, after) == ["Normals (2 issues)", "Names (2 issues)", "Budget (1 issues)"]
    assert runner.new_problems(before, before) == []


@test
def problem_size_counts_faces_by_area():
    """Triangulating two flagged quads into four triangles isn't a bigger problem."""
    import bmesh
    fresh()
    c = cube()
    scope = build_scope([c])
    quads = runner.problem_size([Issue(c.name, "x", element="FACE", indices=[0, 1])], scope)
    bm = bmesh.new()
    bm.from_mesh(c.data)
    bm.faces.ensure_lookup_table()
    tris = bmesh.ops.triangulate(bm, faces=[bm.faces[0], bm.faces[1]])["faces"]
    indices = [f.index for f in tris]
    bm.to_mesh(c.data)
    bm.free()
    assert abs(runner.problem_size([Issue(c.name, "x", element="FACE", indices=indices)], scope) - quads) < 1e-6
    assert runner.problem_size([Issue(c.name, "x", element="EDGE", indices=[1, 2, 3]), Issue(None, "y")],
                               scope) == 4


if __name__ == "__main__":
    main(globals())
