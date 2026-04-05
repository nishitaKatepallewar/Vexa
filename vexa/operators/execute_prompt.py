"""Operator to execute Vexa prompts."""

import difflib
import inspect

import bpy

from ..core.client import create_llm_client
from ..core.registry import AgentTools


class VexaExecutePromptOperator(bpy.types.Operator):
    """Sends the current prompt to Gemini and executes the returned function."""

    bl_idname = "vexa.execute_prompt"
    bl_label = "Execute Vexa Prompt"

    def execute(self, context: bpy.types.Context) -> set[str]:
        scene = context.scene
        prompt = scene.get("vexa_prompt", "")
        prefs = context.preferences.addons["vexa"].preferences
        api_key = prefs.api_key
        model_name = prefs.model_name

        if not prompt:
            self.report({"WARNING"}, "Please enter a prompt")
            return {"CANCELLED"}

        if not api_key:
            self.report({"ERROR"}, "No API Key found. Check Preferences.")
            return {"CANCELLED"}

        client = create_llm_client("gemini", api_key, model_name)
        schemas = AgentTools.get_schemas()

        self.report({"INFO"}, "Thinking...")
        response = client.generate_content(prompt, schemas)

        if "error" in response:
            self.report({"ERROR"}, f"Gemini Error: {response['error']}")
            scene["vexa_last_response"] = f"Error: {response['error']}"
            return {"CANCELLED"}

        func_name, args = client.parse_function_call(response)

        if func_name:
            self._dispatch_tool(context, func_name, args)
        else:
            self._handle_chat_response(context, response)

        return {"FINISHED"}

    def _dispatch_tool(
        self, context: bpy.types.Context, func_name: str, args: dict
    ) -> None:
        tool_func = AgentTools.get_tool(func_name)
        scene = context.scene

        if not tool_func:
            msg = f"Tool '{func_name}' not found locally."
            scene["vexa_last_response"] = msg
            self.report({"WARNING"}, msg)
            return

        try:
            final_args = self._map_arguments(tool_func, args)
            result = tool_func(**final_args)
            scene["vexa_last_response"] = str(result)
            self.report({"INFO"}, f"Executed {func_name}")
        except TypeError as e:
            scene["vexa_last_response"] = f"Argument Error: {str(e)}"
            self.report({"ERROR"}, f"Argument Error: {str(e)}")
        except Exception as e:
            scene["vexa_last_response"] = f"Execution Error: {str(e)}"
            self.report({"ERROR"}, f"Execution Error: {str(e)}")

    def _map_arguments(self, func, provided_args: dict) -> dict:
        sig = inspect.signature(func)
        valid_names = set(sig.parameters.keys())
        final_args = {}

        for key, value in provided_args.items():
            if key in valid_names:
                final_args[key] = value
            else:
                matches = difflib.get_close_matches(key, valid_names, n=1, cutoff=0.7)
                if matches and matches[0] not in final_args:
                    final_args[matches[0]] = value

        return final_args

    def _handle_chat_response(self, context: bpy.types.Context, response: dict) -> None:
        scene = context.scene
        try:
            candidates = response.get("candidates", [])
            if candidates:
                msg = candidates[0]["content"]["parts"][0]["text"]
                scene["vexa_last_response"] = msg
            else:
                scene["vexa_last_response"] = "No understandable response."
        except (KeyError, IndexError):
            scene["vexa_last_response"] = "No understandable response."
