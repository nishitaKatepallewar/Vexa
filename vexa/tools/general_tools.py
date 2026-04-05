"""General purpose AI tools for Blender."""

import bpy
import numpy as np
from mathutils.bvhtree import BVHTree
from itertools import combinations
from vexa.core.registry import AgentTools


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


@AgentTools.register
def select_hard_edges() -> str:
    """Selects all hard (sharp) edges in the active object.

    Returns:
        A status message with the count of hard edges.
    """
    # pylint: disable=no-member
    obj = bpy.context.active_object
    if not obj or obj.type != "MESH":
        return "No active mesh object selected."

    bpy.ops.object.mode_set(mode="OBJECT")

    hard_edges_count = 0
    for edge in obj.data.edges:
        if edge.use_edge_sharp:
            edge.select = True
            hard_edges_count += 1
        else:
            edge.select = False

    bpy.ops.object.mode_set(mode="EDIT")
    
    return f"{hard_edges_count} edges detected."


def _get_evaluated_bvh(
    obj: bpy.types.Object, depsgraph: bpy.types.Depsgraph
) -> BVHTree:
    """Creates a World-Space BVH Tree from an object using Numpy.

    Args:
        obj: The object to evaluate.
        depsgraph: The dependency graph for evaluation.

    Returns:
        A BVHTree representing the object in world space.
    """
    obj_eval = obj.evaluated_get(depsgraph)
    mesh = obj_eval.to_mesh()

    vert_count = len(mesh.vertices)
    verts = np.zeros(vert_count * 3, dtype=np.float32)
    mesh.vertices.foreach_get("co", verts)
    verts_3d = verts.reshape((-1, 3))

    mat = np.array(obj.matrix_world)
    ones = np.ones((vert_count, 1))
    verts_4d = np.hstack((verts_3d, ones))
    world_verts = verts_4d @ mat.T
    world_verts = world_verts[:, :3]

    bvh = BVHTree.FromPolygons(
        world_verts.tolist(), [p.vertices for p in mesh.polygons]
    )
    obj_eval.to_mesh_clear()
    return bvh


@AgentTools.register
def select_faces_with_intersecting_meshes() -> str:
    """Selects faces where meshes intersect for selected objects.

    Returns:
        A status message indicating the number of intersections found.
    """
    # pylint: disable=no-member
    if bpy.context.object:
        bpy.ops.object.mode_set(mode="OBJECT")

    context = bpy.context
    depsgraph = context.evaluated_depsgraph_get()
    selected_meshes = [o for o in context.selected_objects if o.type == "MESH"]

    if len(selected_meshes) < 2:
        return "Select at least 2 mesh objects."

    intersecting_data = {obj.name: set() for obj in selected_meshes}
    bvh_cache = {}

    pairs = list(combinations(selected_meshes, 2))

    for obj_a, obj_b in pairs:
        if obj_a not in bvh_cache:
            bvh_cache[obj_a] = _get_evaluated_bvh(obj_a, depsgraph)
        if obj_b not in bvh_cache:
            bvh_cache[obj_b] = _get_evaluated_bvh(obj_b, depsgraph)

        overlap_pairs = bvh_cache[obj_a].overlap(bvh_cache[obj_b])

        if overlap_pairs:
            for idx_a, idx_b in overlap_pairs:
                intersecting_data[obj_a.name].add(idx_a)
                intersecting_data[obj_b.name].add(idx_b)

    total_intersects = 0
    objects_with_issues = []

    for obj in selected_meshes:
        target_indices = intersecting_data[obj.name]

        # Reset selection
        for attr in ["vertices", "edges", "polygons"]:
            collection = getattr(obj.data, attr)
            collection.foreach_set("select", np.zeros(len(collection), dtype=bool))

        if target_indices:
            total_intersects += len(target_indices)
            objects_with_issues.append(obj)

            # Select intersecting faces
            select_state = np.zeros(len(obj.data.polygons), dtype=bool)
            select_state[list(target_indices)] = True
            obj.data.polygons.foreach_set("select", select_state)

            obj.select_set(True)
            context.view_layer.objects.active = obj
        else:
            obj.select_set(False)

    if total_intersects > 0:
        bpy.ops.object.mode_set(mode="EDIT")
        bpy.ops.mesh.select_mode(type="FACE")
        return (
            f"Found {total_intersects} intersecting faces on "
            f"{len(objects_with_issues)} objects."
        )

    return "No intersections found. Scene is clean."