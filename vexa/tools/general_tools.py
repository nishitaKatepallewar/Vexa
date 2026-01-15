"""General purpose AI tools for Blender."""

import bpy
from ..core.registry import AgentTools


@AgentTools.register
def count_vertices() -> str:
    """Counts the total number of vertices for the currently selected objects.

    Returns:
        A formatted string describing the result.
    """
    total_vertices = 0
    processed_objects = []

    # pylint: disable=no-member
    objects_to_process = bpy.context.selected_objects

    if not objects_to_process:
        return "No objects selected."

    for obj in objects_to_process:
        if obj.type == "MESH":
            total_vertices += len(obj.data.vertices)
            processed_objects.append(obj.name)

    return (
        f"Counted {total_vertices} vertices in {len(processed_objects)} objects "
        f"({', '.join(processed_objects)})."
    )


@AgentTools.register
def rename_object(new_name: str) -> str:
    """Renames the single active (selected) object to the new name provided.

    Args:
        new_name: The new name to apply.

    Returns:
        A status message.
    """
    # pylint: disable=no-member
    obj = bpy.context.active_object
    if not obj:
        return "No active object to rename."

    old_name = obj.name
    obj.name = new_name
    return f"Renamed '{old_name}' to '{new_name}'."
