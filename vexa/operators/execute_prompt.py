"""Operator to execute Vexa prompts (optional AI assistant)."""

import difflib
import inspect
import json
import os
import subprocess
import sys
import tempfile

import bpy

from ..core.client import create_llm_client
from ..core.prefs import get_prefs
from ..core.registry import AgentTools

# The network request runs in a separate process (core/ai_worker.py) so Blender's UI
# never freezes. Blender's API docs advise against Python threads that outlive the
# script and recommend a separate process instead. A timer on the main thread polls
# the process and does everything that touches bpy.
_WORKER = os.path.join(os.path.dirname(os.path.dirname(__file__)), "core", "ai_worker.py")
_pending = {"proc": None, "client": None, "out": ""}
_POLL_SECONDS = 0.2


def _redraw_panels() -> None:
    wm = bpy.context.window_manager
    for window in wm.windows:
        for area in window.screen.areas:
            if area.type == "VIEW_3D":
                area.tag_redraw()


def _set_response(text: str) -> None:
    bpy.context.scene["vexa_last_response"] = text
    _redraw_panels()


def _map_arguments(func, provided_args: dict) -> dict:
    sig = inspect.signature(func)
    valid_names = set(sig.parameters.keys())
    final_args = {}

    for key, value in (provided_args or {}).items():
        if key in valid_names:
            final_args[key] = value
        else:
            matches = difflib.get_close_matches(key, valid_names, n=1, cutoff=0.7)
            if matches and matches[0] not in final_args:
                final_args[matches[0]] = value

    return final_args


def _dispatch_tool(func_name: str, args: dict) -> None:
    tool_func = AgentTools.get_tool(func_name)
    if not tool_func:
        _set_response(f"Tool '{func_name}' not found locally.")
        return
    try:
        result = tool_func(**_map_arguments(tool_func, args))
        _set_response(str(result))
    except TypeError as e:
        _set_response(f"Argument Error: {e}")
    except Exception as e:  # noqa: BLE001 - surface any tool failure in the panel
        _set_response(f"Execution Error: {e}")


def _chat_text(response: dict) -> str:
    try:
        return response["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError, TypeError):
        return "No understandable response."


def _poll_request():
    """Timer callback: waits for the worker process, then acts on its result."""
    proc = _pending["proc"]
    if proc is None:
        return None
    if proc.poll() is None:
        return _POLL_SECONDS

    client, out_path = _pending["client"], _pending["out"]
    _pending.update(proc=None, client=None, out="")
    bpy.context.scene["vexa_is_thinking"] = False
    try:
        with open(out_path, "r", encoding="utf-8") as f:
            response = json.load(f) or {"error": "No response."}
    except (OSError, ValueError):
        response = {"error": f"The AI request failed (exit code {proc.returncode})."}
    finally:
        try:
            os.remove(out_path)
        except OSError:
            pass

    if "error" in response:
        _set_response(f"Error: {response['error']}")
        return None

    func_name, args = client.parse_function_call(response)
    if func_name:
        _dispatch_tool(func_name, args)
    else:
        _set_response(_chat_text(response))
    return None


class VexaExecutePromptOperator(bpy.types.Operator):
    """Sends the instruction to the AI assistant and runs the check it picks"""

    bl_idname = "vexa.execute_prompt"
    bl_label = "Ask Vexa"

    @classmethod
    def poll(cls, context):
        return _pending["proc"] is None

    def execute(self, context: bpy.types.Context) -> set[str]:
        scene = context.scene
        prompt = scene.vexa_prompt.strip()
        prefs = get_prefs(context)
        api_key = prefs.api_key.strip() if prefs else ""

        if not prompt:
            self.report({"WARNING"}, "Type an instruction first")
            return {"CANCELLED"}

        if not api_key:
            self.report({"ERROR"}, "Add a Gemini API key in Vexa's preferences to use the AI assistant")
            return {"CANCELLED"}

        client = create_llm_client("gemini", api_key, prefs.model_name)
        schemas = AgentTools.get_schemas()

        fd, out_path = tempfile.mkstemp(prefix="vexa_ai_", suffix=".json")
        os.close(fd)
        try:
            proc = subprocess.Popen(
                [sys.executable, "-I", _WORKER, out_path],
                stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, text=True,
            )
            proc.stdin.write(json.dumps(client.request_spec(prompt, schemas)))
            proc.stdin.close()
        except OSError as e:
            self.report({"ERROR"}, f"Couldn't start the AI request: {e}")
            return {"CANCELLED"}

        _pending.update(proc=proc, client=client, out=out_path)
        scene["vexa_is_thinking"] = True
        scene["vexa_last_response"] = "Thinking…"
        bpy.app.timers.register(_poll_request, first_interval=_POLL_SECONDS)
        return {"FINISHED"}
