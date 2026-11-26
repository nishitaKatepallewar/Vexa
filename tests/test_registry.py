"""Tests for AgentTools: checks and fixes registered next to plain tools.

Uses throwaway checks registered just for these tests, so it doesn't depend on any
built-in check.
"""

import os
import sys

# Repo root first, so tests always import this checkout's vexa (not an installed copy).
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import bpy  # noqa: E402

from vexa import tools  # noqa: E402
from vexa.core import dispatch  # noqa: E402
from vexa.core.registry import CHECK, AgentTools  # noqa: E402
from vexa.core.results import Issue  # noqa: E402
from vexa.core.scope import current  # noqa: E402
from helpers import cube, fresh, main, test  # noqa: E402

TEMP = ("_t_flag_all", "_t_fix_all")


class temporary_tools:
    """Registers a throwaway check and fix, and removes them afterwards."""

    def __enter__(self):
        @AgentTools.register_check(display_name="Flag all", category="Test", why="Test only.",
                                   severity="ERROR", pass_text="Fine")
        def _t_flag_all(limit: int = 1, label: str = "x") -> list:
            """Flags every mesh."""
            return [Issue(o.name, f"flagged {label}", value=str(limit), element="FACE", indices=[0])
                    for o in current().meshes]

        @AgentTools.register_fix("_t_flag_all", display_name="Fix all", safe=True)
        def _t_fix_all(issues, limit: int = 1) -> str:
            """Fixes everything."""
            return f"fixed {len(issues)} with limit {limit}"

        return self

    def __exit__(self, *exc):
        for name in TEMP:
            AgentTools._tools.pop(name, None)
        return False


@test
def check_and_fix_are_registered_and_linked():
    with temporary_tools():
        check = AgentTools.get("_t_flag_all", kind=CHECK)
        fix = AgentTools.get("_t_fix_all")
        assert check.kind == "check" and check.fix is None and check.check.severity == "ERROR"
        assert fix.kind == "fix" and fix.check is None and fix.fix.check == "_t_flag_all"
        assert AgentTools.fix_for("_t_flag_all") is fix
        assert AgentTools.get("_t_fix_all", kind=CHECK) is None  # a fix isn't a check
        assert "_t_flag_all" in [c.name for c in AgentTools.all(CHECK)]
        assert "_t_fix_all" not in [c.name for c in AgentTools.all(CHECK)]


@test
def check_settings_appear_in_the_tool_spec():
    with temporary_tools():
        spec = next(s for s in AgentTools.tool_specs() if s.name == "_t_flag_all")
        props = spec.parameters["properties"]
        assert props["limit"]["type"] == "integer" and props["label"]["type"] == "string"
        assert spec.parameters["required"] == []  # every setting has a default
        fix_spec = next(s for s in AgentTools.tool_specs() if s.name == "_t_fix_all")
        assert fix_spec.parameters["properties"] == {}  # the fix tool finds issues itself


@test
def check_called_as_a_tool_runs_on_the_selection():
    fresh()
    a = cube("SM_A")
    cube("SM_B", loc=(5, 0, 0)).select_set(False)
    a.select_set(True)
    with temporary_tools():
        text = dispatch.invoke("_t_flag_all", {"label": "here"})
        assert text.startswith("Flag all:") and "SM_A: flagged here" in text and "SM_B" not in text, text
        assert bpy.context.object.mode == "EDIT"  # flagged faces were selected
        bpy.ops.object.mode_set(mode="OBJECT")


@test
def fix_called_as_a_tool_finds_issues_itself():
    fresh()
    cube("SM_A")
    with temporary_tools():
        assert dispatch.invoke("_t_fix_all") == "fixed 1 with limit 1"


@test
def every_check_label_starts_with_detect():
    from vexa.core.registry import CHECK
    from vexa.core.results import problem_title
    for check in AgentTools.all(CHECK):
        if check.name.startswith("_t_"):
            continue
        assert check.display_name.startswith("Detect "), check.display_name
        assert problem_title(check.display_name) == check.display_name[len("Detect "):]
    assert problem_title("Flag all") == "Flag all"


@test
def fix_for_an_unknown_check_is_rejected():
    try:
        AgentTools.register_fix("_t_no_such_check", safe=True)(lambda issues: "")
    except ValueError:
        return
    raise AssertionError("expected ValueError")


@test
def a_fix_is_either_safe_or_explains_what_it_changes():
    for kwargs in ({}, {"confirm": "  "}, {"safe": True, "confirm": "Changes things."}):
        try:
            AgentTools.register_fix("detect_ngons", **kwargs)
        except ValueError:
            continue
        raise AssertionError(f"expected ValueError for {kwargs}")
    for fix in AgentTools.all("fix"):
        if fix.name.startswith("_t_"):
            continue
        assert fix.fix.safe or len(fix.fix.confirm) > 40, (fix.name, fix.fix.confirm)


@test
def issues_a_fix_must_leave_are_never_passed_to_it():
    from vexa.core import runner
    from vexa.core.scope import build_scope
    fresh()
    cube("SM_A")
    cube("SM_Keep", loc=(5, 0, 0))
    seen = []
    with temporary_tools():
        @AgentTools.register_fix("_t_flag_all", display_name="Fix all", safe=True,
                                 skip_reason=lambda issue: "kept" if issue.object_name == "SM_Keep" else "")
        def _t_fix_all(issues) -> str:
            seen.extend(i.object_name for i in issues)
            return f"fixed {len(issues)}"

        scope = build_scope(list(bpy.context.scene.objects))
        result = runner.run_check("_t_flag_all", None, scope)
        assert result.fixable and result.fix_safe
        assert {i.object_name: i.no_fix for i in result.issues} == {"SM_A": "", "SM_Keep": "kept"}
        message = runner.apply_fix(result, None, scope)
        assert seen == ["SM_A"] and message == "fixed 1. Left for you: SM_Keep (kept)", (seen, message)

        bpy.data.objects.remove(bpy.data.objects["SM_A"])
        result = runner.run_check("_t_flag_all", None, build_scope(list(bpy.context.scene.objects)))
        assert result.issues and not result.fixable  # nothing left the fix may touch
        assert runner.apply_fix(result, None, scope) == "Nothing to fix"


@test
def reregistering_replaces_the_entry():
    with temporary_tools():
        count = len(AgentTools.tool_specs())
        with temporary_tools():
            assert len(AgentTools.tool_specs()) == count


@test
def import_all_registers_again_after_clear():
    before = {name for name in AgentTools._tools}
    AgentTools.clear()
    assert not AgentTools.tool_specs()
    tools.import_all()
    after = {name for name in AgentTools._tools}
    assert before == after and "select_hard_edges" in after


if __name__ == "__main__":
    main(globals())
