"""Tests for core/dispatch.py: running any registered tool, check or fix by name."""

import os
import sys

# Repo root first, so tests always import this checkout's vexa (not an installed copy).
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import bpy  # noqa: E402

from vexa.core import dispatch  # noqa: E402
from helpers import cube, fresh, main, test  # noqa: E402


@test
def plain_tool_with_a_misspelled_argument():
    fresh()
    obj = cube("SM_Old")
    bpy.context.view_layer.objects.active = obj
    assert dispatch.invoke("rename_object", {"new_nme": "SM_New"}) == "Renamed 'SM_Old' to 'SM_New'."
    assert obj.name == "SM_New"


@test
def arguments_the_tool_does_not_take_are_dropped():
    assert dispatch.match_arguments(lambda limit=1: None, {"limit": 3, "unrelated": True}) == {"limit": 3}


@test
def check_runs_on_the_selection_and_summarizes():
    fresh()
    cube("SM_A").select_set(True)
    text = dispatch.invoke("detect_over_triangle_budget", {"max_tris": 1})
    assert text.startswith("Triangle budget:") and "SM_A" in text, text


@test
def fix_finds_its_check_issues_itself():
    fresh()
    bpy.ops.mesh.primitive_cylinder_add(vertices=8)
    assert dispatch.invoke("triangulate_ngons") == "Triangulated 2 n-gons"
    assert dispatch.invoke("triangulate_ngons").endswith("nothing to fix.")


@test
def unknown_tool_is_reported():
    try:
        dispatch.invoke("no_such_tool")
    except dispatch.UnknownToolError as e:
        assert "no_such_tool" in str(e)
        return
    raise AssertionError("expected UnknownToolError")


if __name__ == "__main__":
    main(globals())
