"""Operator to execute Vexa prompts (optional AI assistant)."""

import json
import os
import subprocess
import sys
import tempfile

import bpy

from ..core import dispatch
from ..core.llm import WORKER_SCRIPT, create_client
from ..core.prefs import get_prefs
from ..core.registry import AgentTools
from .feedback import show_response

# The network request runs in a separate process (core/llm/worker.py) so Blender's UI
# never freezes. Blender's API docs advise against Python threads that outlive the
# script and recommend a separate process instead. A timer on the main thread polls
# the process and does everything that touches bpy.
_pending = {"proc": None, "client": None, "out": ""}
_POLL_SECONDS = 0.2


def _dispatch_tool(func_name: str, args: dict) -> None:
    try:
        show_response(dispatch.invoke(func_name, args))
    except dispatch.UnknownToolError as e:
        show_response(str(e))
    except TypeError as e:
        show_response(f"Argument Error: {e}")
    except Exception as e:  # noqa: BLE001 - surface any tool failure in the panel
        show_response(f"Execution Error: {e}")


def _poll_request():
    """Timer callback: waits for the worker process, then acts on its result."""
    proc = _pending["proc"]
    if proc is None:
        return None
    if proc.poll() is None:
        return _POLL_SECONDS

    client, out_path = _pending["client"], _pending["out"]
    _pending.update(proc=None, client=None, out="")
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
        show_response(f"Error: {response['error']}")
        return None

    reply = client.parse_response(response)
    if reply.tool_call:
        _dispatch_tool(reply.tool_call.name, reply.tool_call.args)
    else:
        show_response(reply.text or "No understandable response.")
    return None


class VexaExecutePromptOperator(bpy.types.Operator):
    """Sends the instruction to the AI assistant and runs the check it picks"""

    bl_idname = "vexa.execute_prompt"
    bl_label = "Ask Vexa"

    @classmethod
    def poll(cls, context):
        return _pending["proc"] is None

    def execute(self, context: bpy.types.Context) -> set[str]:
        prompt = context.window_manager.vexa_prompt.strip()
        prefs = get_prefs(context)
        api_key = prefs.api_key.strip() if prefs else ""

        if not prompt:
            self.report({"WARNING"}, "Type an instruction first")
            return {"CANCELLED"}

        if not api_key:
            self.report({"ERROR"}, "Add an API key in Vexa's preferences to use the AI assistant")
            return {"CANCELLED"}

        client = create_client(prefs.llm_provider, api_key, prefs.model_name.strip())
        request = client.build_request(prompt, AgentTools.tool_specs())

        fd, out_path = tempfile.mkstemp(prefix="vexa_ai_", suffix=".json")
        os.close(fd)
        try:
            proc = subprocess.Popen(
                [sys.executable, "-I", WORKER_SCRIPT, out_path],
                stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, text=True,
            )
            proc.stdin.write(json.dumps(request.to_dict()))
            proc.stdin.close()
        except OSError as e:
            self.report({"ERROR"}, f"Couldn't start the AI request: {e}")
            return {"CANCELLED"}

        _pending.update(proc=proc, client=client, out=out_path)
        show_response("Thinking…", context)
        bpy.app.timers.register(_poll_request, first_interval=_POLL_SECONDS)
        return {"FINISHED"}
