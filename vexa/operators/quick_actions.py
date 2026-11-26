"""The Tools buttons: run any registered tool, check or fix by name."""

import logging

import bpy

from ..core import dispatch
from ..core.registry import FIX, AgentTools
from .check_ops import confirm_dialog, draw_confirm
from .feedback import show_response

logger = logging.getLogger(__name__)

# The tool currently running, so its button can show a clock. Session state only:
# it isn't saved in the .blend file.
RUNNING = {"tool": ""}


def _execute_tool_async(tool_name: str):
    """Timer callback: runs the tool after the button has redrawn as busy.

    Fixes that need care were confirmed in the button's dialog before this runs.
    """
    try:
        message = dispatch.invoke(tool_name, confirmed=True)
    except Exception as e:  # noqa: BLE001 - show any tool failure in the panel
        logger.error(f"Quick action error for {tool_name}: {e}")
        message = f"Error: {e}"
    finally:
        RUNNING["tool"] = ""
    show_response(message)


class VexaQuickAction(bpy.types.Operator):
    """Executes a registered tool directly without LLM."""

    bl_idname = "vexa.quick_action"
    bl_label = "Quick Action"

    tool_name: bpy.props.StringProperty(
        name="Tool Name",
        description="The name of the tool to execute",
    )

    def invoke(self, context, event):
        tool = AgentTools.get(self.tool_name)
        if tool and tool.kind == FIX and not tool.fix.safe:
            return confirm_dialog(self, context, tool)
        return self.execute(context)

    def draw(self, context):
        tool = AgentTools.get(self.tool_name)
        if tool and tool.kind == FIX:
            draw_confirm(self.layout, tool, [o.name for o in context.selected_objects])

    def execute(self, context: bpy.types.Context) -> set[str]:
        if AgentTools.get(self.tool_name) is None:
            self.report({"ERROR"}, f"Tool '{self.tool_name}' not found")
            return {"CANCELLED"}

        RUNNING["tool"] = self.tool_name
        show_response("", context)

        captured_name = self.tool_name
        bpy.app.timers.register(
            lambda tn=captured_name: _execute_tool_async(tn), first_interval=0.01
        )

        return {"FINISHED"}
