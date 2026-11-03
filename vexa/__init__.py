"""Main entry point for Vexa Blender Add-on."""

import bpy

from .core import props
from .core.llm import PROVIDERS
from .core.registry import AgentTools
from .operators import check_ops
from .operators.execute_prompt import VexaExecutePromptOperator
from .operators.quick_actions import VexaQuickAction
from .ui.panel import PANEL_CLASSES, VexaToggleCategory

bl_info = {
    "name": "Vexa",
    "author": "Vexa Team",
    "version": (0, 5, 0),
    "blender": (4, 0, 0),
    "location": "View3D > Sidebar > Vexa",
    "description": "Check game assets against Unity, Fab and Unreal targets before export.",
    "category": "3D View",
}


class VexaPreferences(bpy.types.AddonPreferences):
    """Add-on preferences. All checks work without any of these settings."""

    bl_idname = __name__

    presets_dir: bpy.props.StringProperty(
        name="Team presets folder",
        description="Optional folder of extra preset .json files, e.g. a shared studio spec",
        subtype="DIR_PATH",
        default="",
        update=lambda self, context: check_ops.reload_presets(context),
    )

    llm_provider: bpy.props.EnumProperty(
        name="Provider",
        description="Which LLM the AI assistant uses",
        items=[(key, cls.label, f"Use {cls.label}") for key, cls in PROVIDERS.items()],
    )

    api_key: bpy.props.StringProperty(
        name="API Key",
        description="Only needed for the AI instruction box. All checks work without it",
        subtype="PASSWORD",
    )

    model_name: bpy.props.StringProperty(
        name="Model",
        description="Model identifier. Leave empty to use the provider's default",
        default="",
    )

    def draw(self, context: bpy.types.Context) -> None:
        layout = self.layout
        layout.prop(self, "presets_dir")

        box = layout.box()
        box.label(text="AI assistant (optional)", icon="EXPERIMENTAL")
        box.prop(self, "llm_provider")
        box.prop(self, "api_key")
        box.prop(self, "model_name")
        if not self.model_name.strip():
            box.label(text=f"Default model: {PROVIDERS[self.llm_provider].default_model}")


def _import_tools() -> None:
    """Import all tool modules to register them with AgentTools."""
    from . import tools

    tools.import_all()


_CLASSES = (
    (VexaPreferences,)
    + props.CLASSES
    + check_ops.CLASSES
    + (VexaExecutePromptOperator, VexaToggleCategory, VexaQuickAction)
    + PANEL_CLASSES
)


def _register() -> None:
    """Registers the add-on classes and properties."""
    _import_tools()

    for cls in _CLASSES:
        bpy.utils.register_class(cls)
    props.register_props()
    check_ops.reload_presets()

    bpy.types.Scene.vexa_prompt = bpy.props.StringProperty(
        name="Prompt", description="Instruction for Vexa", default=""
    )
    bpy.types.Scene.vexa_last_response = bpy.props.StringProperty(
        name="Response", description="Feedback from Vexa", default=""
    )


def _unregister() -> None:
    """Unregisters the add-on classes and properties."""
    props.unregister_props()
    for cls in reversed(_CLASSES):
        bpy.utils.unregister_class(cls)

    for name in ("vexa_prompt", "vexa_last_response"):
        if hasattr(bpy.types.Scene, name):
            delattr(bpy.types.Scene, name)

    from .ui.panel import _reset_tool_cache

    _reset_tool_cache()
    check_ops.STATE.update(preset_id="", scope="", results=[])

    AgentTools.clear()


def register() -> None:
    """Public register function."""
    _register()


def unregister() -> None:
    """Public unregister function."""
    _unregister()


if __name__ == "__main__":
    register()
