"""General purpose tools for Blender: counting, renaming, selecting hard edges.

Checks with structured results (n-gons, non-planar faces, intersections, …) live in
the area modules: geometry_tools, transform_tools, uv_tools, texture_tools, …
"""

import bpy
import numpy as np

from ..core.registry import AgentTools
from ..core.scope import current


@AgentTools.register()
def count_vertices() -> str:
    """Counts total vertices in selected objects."""
    total = 0
    processed = []

    for obj in current().all_meshes:
        total += len(obj.data.vertices)
        processed.append(obj.name)

    if not processed:
        return "No objects selected."

    return f"Counted {total} vertices in {len(processed)} objects ({', '.join(processed)})."


@AgentTools.register()
def rename_object(new_name: str) -> str:
    """Renames the active object."""
    obj = bpy.context.active_object
    if not obj:
        return "No active object to rename."

    old_name = obj.name
    obj.name = new_name
    return f"Renamed '{old_name}' to '{new_name}'."


@AgentTools.register(
    display_name="Select Hard Edges",
    is_quick_action=True,
    category="Geometry",
)
def select_hard_edges() -> str:
    """Selects all sharp edges in the active mesh."""
    obj = bpy.context.active_object
    if not obj or obj.type != "MESH":
        return "No active mesh object selected."

    bpy.ops.object.mode_set(mode="OBJECT")
    edge_count = len(obj.data.edges)
    sharp = np.zeros(edge_count, dtype=bool)
    obj.data.edges.foreach_get("use_edge_sharp", sharp)
    count = int(sharp.sum())
    obj.data.edges.foreach_set("select", sharp)

    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_mode(type="EDGE")
    return f"{count} sharp edges detected."
