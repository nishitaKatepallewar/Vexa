"""General purpose AI tools for Blender."""

import bpy
import math
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


def _switch_to_edit(select_type="FACE"):
    """Switches to edit mode with specified selection type."""
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_mode(type=select_type)


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

    _switch_to_object()
    edge_count = len(obj.data.edges)
    sharp = np.zeros(edge_count, dtype=bool)
    obj.data.edges.foreach_get("use_edge_sharp", sharp)
    count = int(sharp.sum())
    obj.data.edges.foreach_set("select", sharp)

    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    _switch_to_edit("EDGE")
    return f"{count} sharp edges detected."


@AgentTools.register(
    display_name="Detect Mesh Intersections",
    is_quick_action=True,
    category="Geometry",
)
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


def _find_ngons(obj) -> list:
    """Finds n-gon face indices in a mesh object."""
    indices = []
    for idx, face in enumerate(obj.data.polygons):
        if len(face.vertices) > 4:
            indices.append(idx)
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

    indices_by_obj = {}
    for obj in meshes:
        indices = _find_ngons(obj)
        if indices:
            indices_by_obj[obj] = indices

    if not indices_by_obj:
        return "No n-gons found. Mesh is clean."

    total = sum(len(idx) for idx in indices_by_obj.values())
    results = [f"{obj.name} ({len(idx)})" for obj, idx in indices_by_obj.items()]

    _switch_to_object()
    for obj in indices_by_obj:
        sel = np.zeros(len(obj.data.polygons), dtype=bool)
        sel[indices_by_obj[obj]] = True
        obj.data.polygons.foreach_set("select", sel)
        obj.select_set(True)

    if bpy.context.selected_objects:
        bpy.context.view_layer.objects.active = list(indices_by_obj.keys())[0]
        _switch_to_edit()

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

    indices_by_obj = {}
    for obj in meshes:
        indices = _find_ngons(obj)
        if indices:
            indices_by_obj[obj] = indices

    if not indices_by_obj:
        return "No n-gons to triangulate. Mesh is already clean."

    total = sum(len(idx) for idx in indices_by_obj.values())
    results = [f"{obj.name} ({len(idx)})" for obj, idx in indices_by_obj.items()]

    _switch_to_object()
    for obj in indices_by_obj:
        obj.select_set(True)

    if bpy.context.selected_objects:
        bpy.ops.object.mode_set(mode="EDIT")
        bpy.ops.mesh.quads_convert_to_tris()
        _switch_to_object()

    return f"Triangulated {total} n-gons: {', '.join(results)}"


def _has_subd_modifier(obj) -> bool:
    """Check if object has an active Subdivision Surface modifier."""
    for mod in obj.modifiers:
        if mod.type == "SUBSURF":
            return True
    return False


def _compute_quad_nonplanarity(verts, EPSILON=1e-6):
    """Compute max angle between triangles formed by both diagonals.

    Diagonal 0-2: tests triangles (v0,v1,v2) and (v0,v2,v3)
    Diagonal 1-3: tests triangles (v0,v1,v3) and (v1,v2,v3)
    Returns max angle between the two diagonal tests.
    """
    v0, v1, v2, v3 = verts[0], verts[1], verts[2], verts[3]

    # Diagonal 0-2: triangles (v0,v1,v2) and (v0,v2,v3)
    tri_a = (v1 - v0).cross(v2 - v0)
    tri_b = (v2 - v0).cross(v3 - v0)

    # Diagonal 1-3: triangles (v0,v1,v3) and (v1,v2,v3)
    tri_c = (v1 - v0).cross(v3 - v0)
    tri_d = (v2 - v1).cross(v3 - v1)

    angle_d1 = 0.0
    if tri_a.length > EPSILON and tri_b.length > EPSILON:
        angle_d1 = tri_a.normalized().angle(tri_b.normalized())

    angle_d2 = 0.0
    if tri_c.length > EPSILON and tri_d.length > EPSILON:
        angle_d2 = tri_c.normalized().angle(tri_d.normalized())

    return max(angle_d1, angle_d2)


def _newell_normal(verts):
    """Compute best-fit normal using Newell's method - numerically stable for all n-gons."""
    from mathutils import Vector

    n = Vector((0, 0, 0))
    count = len(verts)
    for i in range(count):
        a, b = verts[i], verts[(i + 1) % count]
        n.x += (a.y - b.y) * (a.z + b.z)
        n.y += (a.z - b.z) * (a.x + b.x)
        n.z += (a.x - b.x) * (a.y + b.y)
    return n


def _is_ngon_planar(verts, threshold_rad, EPSILON=1e-6):
    """Check if n-gon is planar using fan-angle test against Newell normal.

    Uses centroid-based triangle fan - scale-independent, angle-consistent
    with quad method, geometrically sound for convex and concave n-gons.
    """
    from mathutils import Vector

    if len(verts) < 4:
        return True

    newell_normal = _newell_normal(verts)
    if newell_normal.length < EPSILON:
        return True

    newell_normal = newell_normal.normalized()

    centroid = sum(verts, Vector()) / len(verts)

    for i in range(len(verts)):
        a = verts[i]
        b = verts[(i + 1) % len(verts)]

        tri_normal = (a - centroid).cross(b - centroid)
        if tri_normal.length < EPSILON:
            continue

        if newell_normal.angle(tri_normal.normalized()) > threshold_rad:
            return False

    return True


def _find_nonplanar_faces_core(bm, threshold: float = 5.0):
    """Unified core detection using BMesh - works in Edit Mode.

    Uses local space coordinates to match BMesh operator behavior.
    Uses Newell's method for robust n-gon detection.
    """
    from mathutils import Vector

    threshold_rad = math.radians(threshold)
    EPSILON = 1e-6
    bm.faces.ensure_lookup_table()

    nonplanar_faces = []
    for face in bm.faces:
        if len(face.verts) < 4:
            continue

        verts = [v.co for v in face.verts]

        if len(verts) == 4:
            max_angle = _compute_quad_nonplanarity(verts, EPSILON)
            if max_angle > threshold_rad:
                nonplanar_faces.append(face)
        else:
            if not _is_ngon_planar(verts, threshold_rad, EPSILON):
                nonplanar_faces.append(face)

    return nonplanar_faces


@AgentTools.register(
    display_name="Detect Non-Planar Faces",
    is_quick_action=True,
    category="Geometry",
)
def detect_nonplanar_faces(threshold: float = 5.0) -> str:
    """Detects non-planar (bent) faces in selected meshes.

    Uses unified core detection for consistency with split operation.
    """
    import bmesh

    meshes = list(_selected_meshes())
    if not meshes:
        return "No objects selected."

    total = 0
    results = []
    has_subd = False

    original_mode = bpy.context.object.mode

    try:
        for obj in meshes:
            if _has_subd_modifier(obj):
                has_subd = True

            bpy.ops.object.mode_set(mode="OBJECT")
            bpy.context.view_layer.objects.active = obj
            bpy.ops.object.mode_set(mode="EDIT")

            bpy.ops.mesh.select_all(action="DESELECT")

            bm = bmesh.from_edit_mesh(obj.data)
            nonplanar_faces = _find_nonplanar_faces_core(bm, threshold)

            if nonplanar_faces:
                for f in nonplanar_faces:
                    f.select = True
                bmesh.update_edit_mesh(obj.data)
                results.append(f"{obj.name} ({len(nonplanar_faces)})")
                total += len(nonplanar_faces)
            else:
                bmesh.update_edit_mesh(obj.data)

            bpy.ops.object.mode_set(mode="OBJECT")

        if total == 0:
            msg = "No non-planar faces found. Mesh is clean."
            if has_subd:
                msg += " (Note: Subdivision Surface modifiers detected)"
            return msg

        response = f"Found {total} non-planar faces: {', '.join(results)}"
        if has_subd:
            response += " (Note: Subdivision Surface modifiers detected - results may be expected)"
        return response

    finally:
        if original_mode != "OBJECT":
            bpy.ops.object.mode_set(mode=original_mode)


@AgentTools.register(
    display_name="Triangulate Non-Planar Faces",
    is_quick_action=True,
    category="Geometry",
)
def triangulate_nonplanar_faces(threshold: float = 5.0) -> str:
    """Triangulates non-planar faces in selected meshes.

    Uses unified core detection - same logic for detect and triangulate.
    Processes each selected object individually in Edit Mode.
    """
    import bmesh

    meshes = list(_selected_meshes())
    if not meshes:
        return "No objects selected."

    bpy.ops.ed.undo_push(message="Triangulate Non-Planar Faces")

    total_triangulated = 0
    processed = []

    original_mode = bpy.context.object.mode

    try:
        for obj in meshes:
            bpy.ops.object.mode_set(mode="OBJECT")
            bpy.context.view_layer.objects.active = obj
            bpy.ops.object.mode_set(mode="EDIT")

            bm = bmesh.from_edit_mesh(obj.data)
            nonplanar_faces = _find_nonplanar_faces_core(bm, threshold)

            if not nonplanar_faces:
                bpy.ops.object.mode_set(mode="OBJECT")
                continue

            source_face_count = len(nonplanar_faces)

            bmesh.ops.triangulate(
                bm,
                faces=nonplanar_faces,
                quad_method="SHORT_EDGE",
                ngon_method="BEAUTY",
            )

            total_triangulated += source_face_count

            bmesh.update_edit_mesh(obj.data)
            bpy.ops.object.mode_set(mode="OBJECT")

            processed.append(f"{obj.name} ({source_face_count})")

    finally:
        if original_mode != "OBJECT":
            bpy.ops.object.mode_set(mode=original_mode)

    if not processed:
        return "No non-planar faces found. Mesh is clean."

    return f"Triangulated {total_triangulated} faces: {', '.join(processed)}"
