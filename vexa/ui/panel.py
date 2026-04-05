"""UI Panel definitions for Vexa."""

import bpy

from ..core.registry import AgentTools

_CACHED_TOOLS_BY_CATEGORY = None
_CACHED_CATEGORIES = None


def _reset_tool_cache():
    """Resets the tool cache. Call this when tools are re-registered."""
    global _CACHED_TOOLS_BY_CATEGORY, _CACHED_CATEGORIES
    _CACHED_TOOLS_BY_CATEGORY = None
    _CACHED_CATEGORIES = None


def _get_tools_by_category():
    """Returns cached tools grouped by category."""
    global _CACHED_TOOLS_BY_CATEGORY, _CACHED_CATEGORIES
    if _CACHED_TOOLS_BY_CATEGORY is None:
        _CACHED_TOOLS_BY_CATEGORY = AgentTools.get_tools_by_category()
        _CACHED_CATEGORIES = AgentTools.get_categories()
    return _CACHED_TOOLS_BY_CATEGORY, _CACHED_CATEGORIES


def _get_expansion_prop(category: str) -> str:
    """Returns the expansion property name for a category."""
    return f"vexa_{category.lower().replace(' ', '_')}_expanded"


def _is_expanded(scene: bpy.types.Scene, category: str) -> bool:
    """Checks if a category is expanded."""
    prop = _get_expansion_prop(category)
    return scene.get(prop, False)


class VexaMainPanel(bpy.types.Panel):
    """Creates a Panel in the View3D UI list."""

    bl_label = "Vexa"
    bl_idname = "VEXA_PT_main_panel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Vexa"

    def draw(self, context: bpy.types.Context) -> None:
        layout = self.layout
        scene = context.scene

        layout.label(text="Instruction:")

        row = layout.row(align=True)
        row.prop(scene, "vexa_prompt", text="")
        row.operator("vexa.execute_prompt", text="", icon="PLAY")

        layout.separator()

        self._draw_quick_actions(context, layout)

        layout.separator()

        response = scene.get("vexa_last_response", "")
        if response:
            box = layout.box()
            box.label(text=response)

    def _draw_quick_actions(
        self, context: bpy.types.Context, layout: bpy.types.UILayout
    ) -> None:
        """Draws quick action buttons from registry."""
        tools_by_cat, categories = _get_tools_by_category()
        scene = context.scene

        for cat in categories:
            category_tools = [
                t for t in tools_by_cat.get(cat, []) if t.metadata.is_quick_action
            ]
            if not category_tools:
                continue

            is_expanded = _is_expanded(scene, cat)

            box = layout.box()
            col = box.column(align=True)
            row = col.row(align=True)

            icon = "DOWNARROW_HLT" if is_expanded else "RIGHTARROW"
            op = row.operator("vexa.toggle_category", text="", icon=icon, emboss=False)
            op.category = cat
            row.label(text=cat)

            if is_expanded:
                for tool in category_tools:
                    is_loading = (
                        scene.get("vexa_is_loading", False)
                        and scene.get("vexa_loading_tool", "") == tool.name
                    )

                    icon = "TIME" if is_loading else "PLAY"
                    button_row = box.column(align=True)
                    btn_row = button_row.row(align=True)
                    op = btn_row.operator(
                        "vexa.quick_action", text="", icon=icon, emboss=False
                    )
                    op.tool_name = tool.name
                    btn_row.label(text=tool.metadata.display_name)


class VexaToggleCategory(bpy.types.Operator):
    """Toggles a category expansion state."""

    bl_idname = "vexa.toggle_category"
    bl_label = "Toggle Category"

    category: bpy.props.StringProperty(name="Category", default="")

    def execute(self, context: bpy.types.Context) -> set[str]:
        scene = context.scene
        prop = _get_expansion_prop(self.category)

        if prop not in scene:
            scene[prop] = False
        else:
            scene[prop] = not scene[prop]
        return {"FINISHED"}
