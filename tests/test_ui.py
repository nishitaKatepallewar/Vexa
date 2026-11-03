"""Headless test of the add-on's operators and panel draw code.

Run on its own, or as part of tests/run_all.py:
    blender -b --factory-startup -P tests/test_ui.py
    python tests/test_ui.py          (with the `bpy` module from PyPI installed)

Blender can't draw UI in background mode, so panels are drawn into a recording
fake layout. That still catches Python errors and bad property names in draw code.
"""

import os
import sys
import tempfile
import traceback

import bpy

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import vexa  # noqa: E402


class FakeLayout:
    """Records UI calls; checks that props it's asked to draw actually exist."""

    def __init__(self, log):
        self.log = log

    def __getattr__(self, name):
        if name in ("row", "column", "box", "split", "column_flow", "grid_flow"):
            return lambda *a, **k: FakeLayout(self.log)
        if name == "prop":
            def prop(data, attr, **k):
                assert hasattr(data, attr), f"missing property {attr} on {data}"
                self.log.append(("prop", attr))
            return prop
        if name == "operator":
            def operator(idname, **k):
                cat, op = idname.split(".")
                assert hasattr(getattr(bpy.ops, cat), op), f"missing operator {idname}"
                self.log.append(("operator", idname))
                return type("Props", (), {})()
            return operator
        if name == "template_list":
            def template_list(listtype, list_id, data, prop, active_data, active_prop, **k):
                assert hasattr(data, prop) and hasattr(active_data, active_prop)
                self.log.append(("template_list", listtype))
            return template_list
        if name in ("label", "separator"):
            return lambda *a, **k: self.log.append((name, k.get("text", "")))
        raise AttributeError(name)

    def __setattr__(self, name, value):
        object.__setattr__(self, name, value)


def draw_panel(cls):
    log = []
    fake = type("P", (), {"layout": FakeLayout(log)})()
    cls.draw(fake, bpy.context)
    return log


def setup_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    vexa.register()
    from vexa.core.prefs import ADDON_ID
    if ADDON_ID not in bpy.context.preferences.addons:
        bpy.context.preferences.addons.new().module = ADDON_ID

    bpy.ops.mesh.primitive_cylinder_add(vertices=8)  # n-gon caps
    obj = bpy.context.active_object
    obj.name = "Crate"
    obj.scale = (2, 2, 2)
    bpy.ops.mesh.primitive_cube_add(location=(0.5, 0.4, 0.2))
    bpy.context.active_object.name = "Cube"
    for o in bpy.context.scene.objects:
        o.select_set(True)
    return obj


def run() -> int:
    """Runs the UI tests and returns the number of failures."""
    failures = []

    def step(name, fn):
        try:
            fn()
            print(f"PASS  {name}")
        except Exception:
            failures.append(name)
            print(f"FAIL  {name}")
            traceback.print_exc()

    setup_scene()
    from vexa.operators.check_ops import STATE
    from vexa.ui import panel
    from vexa.core.registry import AgentTools
    from vexa.core import props

    scene = bpy.context.scene
    wm = bpy.context.window_manager

    def presets_listed():
        items = [i[0] for i in props._preset_items(scene, bpy.context)]
        assert {"general", "unity_asset_store", "fab", "unreal"} <= set(items), items

    def panel_before_run():
        log = draw_panel(panel.VexaMainPanel)
        assert ("operator", "vexa.run_checks") in log

    def run_checks():
        scene.vexa_preset = "unity_asset_store"
        scene.vexa_scope = "SELECTED"
        assert bpy.ops.vexa.run_checks() == {"FINISHED"}
        assert wm.vexa_has_run and len(wm.vexa_results) == len(STATE["results"]) > 0
        statuses = {r.check_id: r.status for r in STATE["results"]}
        assert statuses["detect_unapplied_transforms"] == "ERROR", statuses
        assert statuses["detect_default_names"] == "WARNING", statuses

    def panels_after_run():
        log = draw_panel(panel.VexaMainPanel)
        assert ("template_list", "VEXA_UL_results") in log
        draw_panel(panel.VEXA_PT_preset_checks)
        draw_panel(panel.VEXA_PT_tools)
        # UIList rows
        ul = object()
        for item in wm.vexa_results:
            panel.VEXA_UL_results.draw_item(ul, bpy.context, FakeLayout([]), wm, item, 0, wm,
                                            "vexa_results_index", 0)

    def select_problem_faces():
        assert bpy.ops.vexa.select_issues(check_id="detect_ngons") == {"FINISHED"}
        assert bpy.context.object.mode == "EDIT"
        assert sum(p.select for p in bpy.data.objects["Crate"].data.polygons) == 2
        bpy.ops.object.mode_set(mode="OBJECT")

    def fix_one():
        assert bpy.ops.vexa.fix_check(check_id="detect_unapplied_transforms") == {"FINISHED"}
        st = {r.check_id: r.status for r in STATE["results"]}
        assert st["detect_unapplied_transforms"] == "PASS", st

    def fix_all():
        for o in scene.objects:
            o.select_set(True)
        bpy.ops.vexa.run_checks()
        assert bpy.ops.vexa.fix_all() == {"FINISHED"}
        left = [r.check_id for r in STATE["results"] if r.fixable]
        assert not left, left

    def toggle_check():
        bpy.ops.vexa.toggle_check(check_id="detect_default_names")
        assert "detect_default_names" not in {r.check_id for r in STATE["results"]}
        bpy.ops.vexa.toggle_check(check_id="detect_default_names")
        assert "detect_default_names" in {r.check_id for r in STATE["results"]}

    def export_report():
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "vexa_report.json")
            assert bpy.ops.vexa.export_report(filepath=path) == {"FINISHED"}
            import json
            data = json.load(open(path))
            assert data["preset"]["id"] == "unity_asset_store" and data["results"]

    def team_presets_folder():
        from vexa.core.prefs import get_prefs
        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, "studio.json"), "w") as f:
                f.write('{"id": "acme", "name": "Acme Studio", "checks": {"detect_over_triangle_budget": {"max_tris": 10}}}')
            get_prefs().presets_dir = d
            items = [i[0] for i in props._preset_items(scene, bpy.context)]
            assert "acme" in items, items
            get_prefs().presets_dir = ""

    def preferences_draw():
        from vexa.core.prefs import get_prefs
        prefs = get_prefs()
        log = []
        fake = type("Prefs", (), {name: getattr(prefs, name) for name in
                                  ("presets_dir", "llm_provider", "api_key", "model_name")})()
        fake.layout = FakeLayout(log)
        vexa.VexaPreferences.draw(fake, bpy.context)
        drawn = {entry[1] for entry in log if entry[0] == "prop"}
        assert {"presets_dir", "llm_provider", "api_key", "model_name"} <= drawn, drawn
        assert ("label", "Default model: gemini-2.5-flash") in log, log

    def ai_panel_hidden_without_key():
        assert not panel.VEXA_PT_ai.poll(bpy.context)

    def ai_request_runs_in_separate_process():
        import time
        from vexa.core.prefs import get_prefs
        from vexa.core.llm.gemini import GeminiClient
        from vexa.operators import execute_prompt as ep
        get_prefs().api_key = "test-key"
        assert get_prefs().llm_provider == "gemini" and get_prefs().model_name == ""
        original = GeminiClient.build_request

        def unreachable(self, prompt, tools):
            request = original(self, prompt, tools)
            request.host, request.timeout = "vexa-test.invalid", 5
            return request

        GeminiClient.build_request = unreachable
        try:
            scene.vexa_prompt = "find ngons"
            assert bpy.ops.vexa.execute_prompt() == {"FINISHED"}
            assert ep._pending["proc"] is not None
            deadline = time.time() + 20
            while ep._poll_request() is not None and time.time() < deadline:
                time.sleep(0.2)
            assert ep._pending["proc"] is None
            assert scene["vexa_last_response"].startswith("Error:"), scene["vexa_last_response"]
        finally:
            GeminiClient.build_request = original
            get_prefs().api_key = ""

    def quick_action_runs_a_check():
        from vexa.operators.quick_actions import _execute_tool_async
        bpy.ops.object.select_all(action="DESELECT")
        bpy.ops.mesh.primitive_cylinder_add(vertices=8, location=(10, 0, 0))
        _execute_tool_async("detect_ngons")
        assert scene["vexa_last_response"].startswith("Detect N-gons: 2 n-gons"), scene["vexa_last_response"]
        bpy.ops.object.mode_set(mode="OBJECT")
        _execute_tool_async("triangulate_ngons")
        assert scene["vexa_last_response"] == "Triangulated 2 n-gons", scene["vexa_last_response"]

    def ai_tool_call_runs_a_check():
        from vexa.operators.execute_prompt import _dispatch_tool
        _dispatch_tool("detect_over_triangle_budget", {"max_tris": 1})
        assert scene["vexa_last_response"].startswith("Triangle budget:"), scene["vexa_last_response"]
        names = {s.name for s in AgentTools.tool_specs()}
        assert {"detect_ngons", "detect_missing_lightmap_uvs", "triangulate_ngons", "select_hard_edges"} <= names

    def reenable_keeps_tools():
        vexa.unregister()
        vexa.register()
        assert AgentTools.get_check("detect_ngons") and AgentTools.get_registered("select_hard_edges")
        log = draw_panel(panel.VexaMainPanel)  # no stale results after re-enabling
        assert ("template_list", "VEXA_UL_results") not in log

    def unregister_clean():
        vexa.unregister()
        assert not hasattr(bpy.types.Scene, "vexa_preset")

    for name, fn in [
        ("presets listed in Target dropdown", presets_listed),
        ("panel draws before first run", panel_before_run),
        ("Check Assets runs Unity preset", run_checks),
        ("panels and result rows draw", panels_after_run),
        ("select problem faces", select_problem_faces),
        ("fix one check", fix_one),
        ("fix all safe issues", fix_all),
        ("toggle a check off and on", toggle_check),
        ("export JSON report", export_report),
        ("team presets folder", team_presets_folder),
        ("preferences draw", preferences_draw),
        ("AI panel hidden without key", ai_panel_hidden_without_key),
        ("AI request runs in a separate process", ai_request_runs_in_separate_process),
        ("quick action runs a check and its fix", quick_action_runs_a_check),
        ("AI tool call runs a check", ai_tool_call_runs_a_check),
        ("disable and re-enable keeps every tool", reenable_keeps_tools),
        ("unregister cleanly", unregister_clean),
    ]:
        step(name, fn)

    print(f"\n{17 - len(failures)}/17 UI tests passed on Blender {bpy.app.version_string}")
    return len(failures)


if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from helpers import finish

    finish(run())
