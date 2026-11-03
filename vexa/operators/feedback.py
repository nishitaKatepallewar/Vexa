"""Shows results from work that finishes outside an operator (timers, background requests)."""

import bpy


def redraw_3d_views(context=None) -> None:
    """Asks every 3D View to redraw, so the sidebar shows new state."""
    wm = (context or bpy.context).window_manager
    for window in wm.windows:
        for area in window.screen.areas:
            if area.type == "VIEW_3D":
                area.tag_redraw()


def show_response(text: str, context=None) -> None:
    """Sets the message shown under Tools and Ask Vexa, and redraws."""
    (context or bpy.context).window_manager.vexa_last_response = text
    redraw_3d_views(context)
