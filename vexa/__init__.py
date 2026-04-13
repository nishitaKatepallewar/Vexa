"""Main entry point for Vexa Blender Add-on."""

import bpy

from .ui.panel import VexaMainPanel, VexaToggleCategory
from .operators.execute_prompt import VexaExecutePromptOperator
from .operators.quick_actions import VexaQuickAction
from .core.registry import AgentTools

bl_info = {
    "name": "Vexa",
    "author": "Vexa Team",
    "version": (0, 4, 0),
    "blender": (4, 0, 0),
    "location": "View3D > Sidebar > Vexa",
    "description": "QC checks in seconds.",
    "category": "3D View",
}


class VexaPreferences(bpy.types.AddonPreferences):
    """Add-on preferences to store API credentials."""

    bl_idname = __name__

    api_key: bpy.props.StringProperty(
        name="Gemini API Key",
        description="Enter your Google Gemini API Key",
        subtype="PASSWORD",
    )

    model_name: bpy.props.StringProperty(
        name="Model Name",
        description="Gemini Model Identifier (e.g. gemini-2.5-flash)",
        default="gemini-2.5-flash",
    )

    def draw(self, context: bpy.types.Context) -> None:
        layout = self.layout
        layout.prop(self, "api_key")
        layout.prop(self, "model_name")


def _import_tools() -> None:
    """Import all tool modules to register them with AgentTools."""
    from .tools import general_tools
    from .tools import texture_tools


def _register() -> None:
    """Registers the add-on classes and properties."""
    _import_tools()

    bpy.utils.register_class(VexaPreferences)
    bpy.utils.register_class(VexaMainPanel)
    bpy.utils.register_class(VexaExecutePromptOperator)
    bpy.utils.register_class(VexaToggleCategory)
    bpy.utils.register_class(VexaQuickAction)

    bpy.types.Scene.vexa_prompt = bpy.props.StringProperty(
        name="Prompt", description="Instruction for Vexa", default=""
    )
    bpy.types.Scene.vexa_last_response = bpy.props.StringProperty(
        name="Response", description="Feedback from Vexa", default=""
    )


def _unregister() -> None:
    """Unregisters the add-on classes and properties."""
    bpy.utils.unregister_class(VexaPreferences)
    bpy.utils.unregister_class(VexaMainPanel)
    bpy.utils.unregister_class(VexaExecutePromptOperator)
    bpy.utils.unregister_class(VexaToggleCategory)
    bpy.utils.unregister_class(VexaQuickAction)

    if "vexa_prompt" in bpy.types.Scene.__annotations__:
        del bpy.types.Scene.__annotations__["vexa_prompt"]
    if "vexa_last_response" in bpy.types.Scene.__annotations__:
        del bpy.types.Scene.__annotations__["vexa_last_response"]

    from .ui.panel import _reset_tool_cache

    _reset_tool_cache()

    AgentTools._tools.clear()
    AgentTools._schemas.clear()


def register() -> None:
    """Public register function."""
    _register()


def unregister() -> None:
    """Public unregister function."""
    _unregister()


if __name__ == "__main__":
    register()
