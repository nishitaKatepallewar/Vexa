"""UI Panel definitions for Vexa."""

import bpy


class VexaMainPanel(bpy.types.Panel):
    """Creates a Panel in the View3D UI list."""

    bl_label = "Vexa"
    bl_idname = "VEXA_PT_main_panel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Vexa"

    def draw(self, context: bpy.types.Context) -> None:
        """Draws the UI."""
        layout = self.layout
        scene = context.scene

        layout.label(text="Instruction:")
        
        # Combined prompt and execute button
        row = layout.row(align=True)
        row.prop(scene, "vexa_prompt", text="")
        row.operator("vexa.execute_prompt", text="", icon="PLAY")

        layout.separator()

        # Feedback/Status area
        # pylint: disable=no-member
        if hasattr(scene, "vexa_last_response") and scene.vexa_last_response:
            box = layout.box()
            box.label(text=scene.vexa_last_response)
