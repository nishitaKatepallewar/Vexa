"""Operator to execute Vexa prompts."""

import difflib
import inspect

import bpy

from ..core.client import GeminiClient
from ..core.registry import AgentTools

# Ensure tools are registered by importing them
# pylint: disable=unused-import
from ..tools import general_tools


class VexaExecutePromptOperator(bpy.types.Operator):
    """Sends the current prompt to Gemini and executes the returned function."""

    bl_idname = "vexa.execute_prompt"
    bl_label = "Execute Vexa Prompt"

    def execute(self, context: bpy.types.Context) -> set[str]:
        """Executes the operator."""
        scene = context.scene
        prompt = scene.vexa_prompt
        # pylint: disable=no-member
        prefs = context.preferences.addons[
            __package__.split(".")[0]
        ].preferences
        api_key = prefs.api_key
        model_name = prefs.model_name

        if not prompt:
            self.report({"WARNING"}, "Please enter a prompt")
            return {"CANCELLED"}

        if not api_key:
            self.report({"ERROR"}, "No API Key found. Check Preferences.")
            return {"CANCELLED"}

        client = GeminiClient(api_key, model_name)
        schemas = AgentTools.get_schemas()

        self.report({"INFO"}, "Thinking...")
        response = client.generate_content(prompt, schemas)

        if "error" in response:
            error_msg = response["error"]
            self.report({"ERROR"}, f"Gemini Error: {error_msg}")
            scene.vexa_last_response = f"Error: {error_msg}"
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
        """Helper to execute the requested tool."""
        tool_func = AgentTools.get_tool(func_name)
        scene = context.scene

        if not tool_func:
            msg = f"Tool '{func_name}' not found locally."
            scene.vexa_last_response = msg
            self.report({"WARNING"}, msg)
            return

        try:
            final_args = self._map_arguments(tool_func, args)
            result = tool_func(**final_args)
            scene.vexa_last_response = str(result)
            self.report({"INFO"}, f"Executed {func_name}")
        except TypeError as type_err:
            err_msg = f"Argument Error: {str(type_err)}"
            scene.vexa_last_response = err_msg
        except Exception as error:  # pylint: disable=broad-except
            err_msg = f"Execution Error: {str(error)}"
            scene.vexa_last_response = err_msg

    def _map_arguments(self, func, provided_args: dict) -> dict:
        """Corrects argument names using fuzzy matching and validation."""
        sig = inspect.signature(func)
        valid_names = set(sig.parameters.keys())
        final_args = {}

        for key, value in provided_args.items():
            if key in valid_names:
                final_args[key] = value
            else:
                matches = difflib.get_close_matches(
                    key, valid_names, n=1, cutoff=0.7
                )
                if matches:
                    corrected_key = matches[0]
                    if corrected_key not in final_args:
                        final_args[corrected_key] = value

        return final_args

    def _handle_chat_response(
        self, context: bpy.types.Context, response: dict
    ) -> None:
        """Helper to handle non-functional chat responses."""
        scene = context.scene
        try:
            candidates = response.get("candidates", [])
            if candidates:
                msg = candidates[0]["content"]["parts"][0]["text"]
                scene.vexa_last_response = msg
            else:
                scene.vexa_last_response = "No understandable response."
        except (KeyError, IndexError):
            scene.vexa_last_response = "No understandable response."
