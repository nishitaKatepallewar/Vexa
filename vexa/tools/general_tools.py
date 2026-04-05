"""General purpose AI tools for Blender."""

import bpy
import numpy as np
from itertools import combinations
from mathutils.bvhtree import BVHTree

from vexa.core.registry import AgentTools


def _selected_meshes():
    """Yields mesh objects from current selection."""
    for obj in bpy.context.selected_objects:
        if obj.type == "MESH":
            yield obj


def _mesh_to_world_verts(mesh, matrix_world):
    """Converts mesh vertices to world space."""
    vert_count = len(mesh.vertices)
    verts = np.zeros(vert_count * 3, dtype=np.float32)
    mesh.vertices.foreach_get("co", verts)
    verts_3d = verts.reshape((-1, 3))

    mat = np.array(matrix_world)
    ones = np.ones((vert_count, 1))
    verts_4d = np.hstack((verts_3d, ones))
    return (verts_4d @ mat.T)[:, :3]


def _create_bvh_tree(obj, depsgraph):
    """Creates a world-space BVH tree for an object."""
    obj_eval = obj.evaluated_get(depsgraph)
    mesh = obj_eval.to_mesh()
    world_verts = _mesh_to_world_verts(mesh, obj.matrix_world)
    bvh = BVHTree.FromPolygons(
        world_verts.tolist(), [p.vertices for p in mesh.polygons]
    )
    obj_eval.to_mesh_clear()
    return bvh


def _reset_selection(obj):
    """Resets all selection states on an object."""
    for attr in ("vertices", "edges", "polygons"):
        collection = getattr(obj.data, attr)
        collection.foreach_set("select", np.zeros(len(collection), dtype=bool))


def _switch_to_edit():
    """Switches to edit mode with face selection."""
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_mode(type="FACE")


def _switch_to_object():
    """Switches to object mode."""
    bpy.ops.object.mode_set(mode="OBJECT")


@AgentTools.register()
def count_vertices() -> str:
    """Counts total vertices in selected objects."""
    total = 0
    processed = []

    for obj in _selected_meshes():
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


@AgentTools.register()
def select_hard_edges() -> str:
    """Selects all sharp edges in the active mesh."""
    obj = bpy.context.active_object
    if not obj or obj.type != "MESH":
        return "No active mesh object selected."

    _switch_to_object()
    count = sum(1 for e in obj.data.edges if e.use_edge_sharp)

    for edge in obj.data.edges:
        edge.select = edge.use_edge_sharp

    _switch_to_edit()
    return f"{count} sharp edges detected."


@AgentTools.register()
def select_faces_with_intersecting_meshes() -> str:
    """Selects faces where selected meshes intersect."""
    meshes = list(_selected_meshes())
    if len(meshes) < 2:
        return "Select at least 2 mesh objects."

    _switch_to_object()
    depsgraph = bpy.context.evaluated_depsgraph_get()
    bvh_cache = {obj: _create_bvh_tree(obj, depsgraph) for obj in meshes}

    intersections = {obj.name: set() for obj in meshes}
    for obj_a, obj_b in combinations(meshes, 2):
        for idx_a, idx_b in bvh_cache[obj_a].overlap(bvh_cache[obj_b]):
            intersections[obj_a.name].add(idx_a)
            intersections[obj_b.name].add(idx_b)

    total = 0
    affected = []
    for obj in meshes:
        _reset_selection(obj)
        if intersections[obj.name]:
            total += len(intersections[obj.name])
            affected.append(obj)
            sel = np.zeros(len(obj.data.polygons), dtype=bool)
            sel[list(intersections[obj.name])] = True
            obj.data.polygons.foreach_set("select", sel)
            obj.select_set(True)
            bpy.context.view_layer.objects.active = obj
        else:
            obj.select_set(False)

    if total > 0:
        _switch_to_edit()
        return f"Found {total} intersecting faces on {len(affected)} objects."

    return "No intersections found. Scene is clean."


def _find_ngons(obj, select: bool = False) -> tuple:
    """Finds n-gon face indices in a mesh object."""
    indices = []
    for idx, face in enumerate(obj.data.polygons):
        if len(face.vertices) > 4:
            indices.append(idx)
            if select:
                face.select = True
    return indices


@AgentTools.register(
    display_name="Detect N-gons",
    is_quick_action=True,
    category="Geometry",
)
def detect_ngons() -> str:
    """Detects and selects n-gon faces in selected meshes."""
    meshes = list(_selected_meshes())
    if not meshes:
        return "No objects selected."

    total = 0
    results = []

    for obj in meshes:
        bpy.context.view_layer.objects.active = obj
        _switch_to_object()
        _reset_selection(obj)

        indices = _find_ngons(obj, select=True)
        if indices:
            _switch_to_edit()
            results.append(f"{obj.name} ({len(indices)})")
            total += len(indices)
        else:
            _switch_to_object()

    if total == 0:
        return "No n-gons found. Mesh is clean."

    return f"Found {total} n-gons: {', '.join(results)}"


@AgentTools.register(
    display_name="Triangulate N-gons",
    is_quick_action=True,
    category="Geometry",
)
def triangulate_ngons() -> str:
    """Triangulates all n-gons in selected meshes."""
    meshes = list(_selected_meshes())
    if not meshes:
        return "No objects selected."

    total = 0
    results = []

    for obj in meshes:
        bpy.context.view_layer.objects.active = obj
        _switch_to_object()
        _reset_selection(obj)

        indices = _find_ngons(obj, select=True)
        if indices:
            _switch_to_edit()
            bpy.ops.mesh.quads_convert_to_tris()
            _switch_to_object()
            results.append(f"{obj.name} ({len(indices)})")
            total += len(indices)
        else:
            _switch_to_object()

    if total == 0:
        return "No n-gons to triangulate. Mesh is already clean."

    return f"Triangulated {total} n-gons: {', '.join(results)}"
