"""Main entry point for Vexa Blender Add-on."""

# pylint: disable=import-error, no-name-in-module
import bpy

from .ui.panel import VexaMainPanel
from .operators.execute_prompt import VexaExecutePromptOperator

bl_info = {
    "name": "Vexa",
    "author": "Vexa Team",
    "version": (0, 3, 0),
    "blender": (4, 0, 0),
    "location": "View3D > Sidebar > Vexa",
    "description": "QC checks within seconds.",
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
        """Draws the preferences UI."""
        layout = self.layout
        layout.prop(self, "api_key")
        layout.prop(self, "model_name")


def register() -> None:
    """Registers the add-on classes and properties."""
    bpy.utils.register_class(VexaPreferences)
    bpy.utils.register_class(VexaMainPanel)
    bpy.utils.register_class(VexaExecutePromptOperator)

    bpy.types.Scene.vexa_prompt = bpy.props.StringProperty(
        name="Prompt", description="Instruction for Vexa", default=""
    )
    bpy.types.Scene.vexa_last_response = bpy.props.StringProperty(
        name="Response", description="Feedback from Vexa", default=""
    )


def unregister() -> None:
    """Unregisters the add-on classes and properties."""
    bpy.utils.unregister_class(VexaPreferences)
    bpy.utils.unregister_class(VexaMainPanel)
    bpy.utils.unregister_class(VexaExecutePromptOperator)

    del bpy.types.Scene.vexa_prompt
    del bpy.types.Scene.vexa_last_response


if __name__ == "__main__":
    register()
