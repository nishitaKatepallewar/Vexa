"""Generic quick action operator that executes any registered tool."""

import logging
import bpy

from ..core import dispatch
from ..core.registry import AgentTools

logger = logging.getLogger(__name__)


def _execute_tool_async(tool_name: str):
    """Module-level function to run tool async."""
    scene = bpy.context.scene
    try:
        scene["vexa_last_response"] = dispatch.invoke(tool_name)
    except Exception as e:
        logger.error(f"Quick action error for {tool_name}: {e}")
        scene["vexa_last_response"] = f"Error: {str(e)}"
    finally:
        scene["vexa_is_loading"] = False
        scene["vexa_loading_tool"] = ""


class VexaQuickAction(bpy.types.Operator):
    """Executes a registered tool directly without LLM."""

    bl_idname = "vexa.quick_action"
    bl_label = "Quick Action"

    tool_name: bpy.props.StringProperty(
        name="Tool Name",
        description="The name of the tool to execute",
    )

    def execute(self, context: bpy.types.Context) -> set[str]:
        if AgentTools.get_registered(self.tool_name) is None:
            self.report({"ERROR"}, f"Tool '{self.tool_name}' not found")
            return {"CANCELLED"}

        scene = context.scene
        scene["vexa_is_loading"] = True
        scene["vexa_loading_tool"] = self.tool_name
        scene["vexa_last_response"] = ""

        captured_name = self.tool_name
        bpy.app.timers.register(
            lambda tn=captured_name: _execute_tool_async(tn), first_interval=0.01
        )

        return {"FINISHED"}
