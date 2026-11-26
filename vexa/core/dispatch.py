"""Runs any registered tool, check or fix by name.

This is the single entry point for callers that pick a tool by name: the Tools
quick-action buttons, the AI assistant, and any future caller such as a generator.
"""

import difflib
import inspect
from typing import Any, Callable, Dict, Optional

import bpy

from . import runner
from .registry import CHECK, FIX, AgentTools


class UnknownToolError(LookupError):
    """No tool is registered under the requested name."""


def invoke(name: str, args: Optional[Dict[str, Any]] = None, confirmed: bool = False) -> str:
    """Runs a registered tool and returns a message for the user or the LLM.

    Arguments are matched to the tool's parameters by name, tolerating small
    misspellings (LLMs sometimes paraphrase parameter names). A check runs on the
    selection, selects what it found and returns a summary; a fix finds its check's
    issues on the selection and fixes them. Tools and fixes get an undo step: callers
    run them from timers, after any operator has finished, so Blender wouldn't record
    one otherwise.

    A fix that isn't safe only runs with confirmed=True, i.e. after the artist read
    what it changes (the Tools button's dialog). Otherwise, e.g. when the AI picks it,
    the message says what it would do and where to run it.

    Raises UnknownToolError for an unknown name; errors from the tool propagate.
    """
    tool = AgentTools.get(name)
    if tool is None:
        raise UnknownToolError(f"Tool '{name}' not found locally.")
    if tool.kind == CHECK:  # runs on the selection, selects what it found, summarizes
        return runner.run_check_as_tool(name, match_arguments(tool.func, args or {}))
    if tool.kind == FIX and not (tool.fix.safe or confirmed):
        return (f"{tool.display_name} needs your OK first. {tool.fix.confirm} "
                f"To go ahead, click it under Tools > {tool.category}, or the wrench on its row in Results.")
    if tool.kind == FIX:  # finds its check's issues on the selection, then fixes them
        result = runner.run_fix_as_tool(name)
    else:
        result = tool.func(**match_arguments(tool.func, args or {}))
    _push_undo(tool.display_name)
    return str(result)


def match_arguments(func: Callable, provided: Dict[str, Any]) -> Dict[str, Any]:
    """Keeps the arguments `func` accepts, mapping close misspellings to real names."""
    valid = set(inspect.signature(func).parameters)
    matched: Dict[str, Any] = {}
    for key, value in provided.items():
        if key in valid:
            matched[key] = value
            continue
        close = difflib.get_close_matches(key, valid, n=1, cutoff=0.7)
        if close and close[0] not in matched:
            matched[close[0]] = value
    return matched


def _push_undo(message: str) -> None:
    if bpy.ops.ed.undo_push.poll():
        bpy.ops.ed.undo_push(message=message)
