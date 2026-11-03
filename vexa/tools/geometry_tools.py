"""Geometry checks: n-gons, non-planar faces, intersections, triangle budget."""

import math
from itertools import combinations

import bmesh
import numpy as np
from mathutils.bvhtree import BVHTree
from mathutils.geometry import distance_point_to_plane

from ..core.registry import AgentTools
from ..core.results import Issue
from ..core.scope import current

EPSILON = 1e-6


# ---------- helpers ----------

def _face_sizes(mesh) -> np.ndarray:
    sizes = np.zeros(len(mesh.polygons), dtype=np.int32)
    mesh.polygons.foreach_get("loop_total", sizes)
    return sizes


def _is_face_planar(verts, threshold_rad: float) -> bool:
    """Point-to-plane test: every vertex must lie within threshold of the plane
    defined by the first three. Catches symmetric warping a diagonal test misses."""
    if len(verts) < 4:
        return True
    plane_co = verts[0]
    plane_no = (verts[1] - verts[0]).cross(verts[2] - verts[0])
    if plane_no.length < EPSILON:
        return True
    plane_no.normalize()
    for v in verts[3:]:
        dist = abs(distance_point_to_plane(v, plane_co, plane_no))
        radius = (v - plane_co).length
        if radius > EPSILON and math.asin(min(dist / radius, 1.0)) > threshold_rad:
            return False
    return True


def _nonplanar_indices(mesh, threshold_deg: float) -> list:
    threshold_rad = math.radians(threshold_deg)
    co = [v.co for v in mesh.vertices]
    out = []
    for poly in mesh.polygons:
        if poly.loop_total < 4:
            continue
        if not _is_face_planar([co[i] for i in poly.vertices], threshold_rad):
            out.append(poly.index)
    return out


def _triangulate_faces(obj, face_indices) -> int:
    """Triangulates the given faces in Object Mode. Returns how many were triangulated."""
    if not face_indices:
        return 0
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bm.faces.ensure_lookup_table()
    faces = [bm.faces[i] for i in face_indices if i < len(bm.faces)]
    bmesh.ops.triangulate(bm, faces=faces, quad_method="SHORT_EDGE", ngon_method="BEAUTY")
    bm.to_mesh(obj.data)
    bm.free()
    obj.data.update()
    return len(faces)


def _triangulate_issues(issues) -> int:
    scene = current().scene
    total = 0
    for issue in issues:
        obj = scene.objects.get(issue.object_name)
        if obj:
            total += _triangulate_faces(obj, issue.indices)
    return total


def triangle_count(mesh) -> int:
    return int(np.sum(np.maximum(_face_sizes(mesh) - 2, 0)))


def _world_bvh(obj):
    mw = obj.matrix_world
    verts = [mw @ v.co for v in obj.data.vertices]
    return BVHTree.FromPolygons(verts, [tuple(p.vertices) for p in obj.data.polygons])


# ---------- n-gons ----------

@AgentTools.register_check(
    display_name="Detect N-gons",
    category="Geometry",
    why="Faces with more than 4 sides are triangulated unpredictably on export, "
        "which can cause shading artifacts and broken normal maps.",
    pass_text="None",
    is_quick_action=True,
)
def detect_ngons() -> list:
    """Finds faces with more than four sides in the selected meshes."""
    issues = []
    for obj in current().meshes:
        idx = np.nonzero(_face_sizes(obj.data) > 4)[0].tolist()
        if idx:
            issues.append(Issue(obj.name, f"{len(idx)} n-gons", value=f"{len(idx)} n-gons",
                                element="FACE", indices=idx))
    return issues


@AgentTools.register_fix("detect_ngons", display_name="Triangulate N-gons", is_quick_action=True)
def triangulate_ngons(issues) -> str:
    """Triangulates every n-gon in the selected meshes."""
    return f"Triangulated {_triangulate_issues(issues)} n-gons"


# ---------- non-planar faces ----------

@AgentTools.register_check(
    display_name="Detect Non-Planar Faces",
    category="Geometry",
    why="Bent quads and n-gons can be split along either diagonal by the engine, "
        "changing the silhouette and shading from what you see in Blender.",
    pass_text="None",
    is_quick_action=True,
)
def detect_nonplanar_faces(threshold_deg: float = 0.001) -> list:
    """Finds quads and n-gons whose vertices don't lie on one plane.

    threshold_deg: how far (in degrees) a vertex may bend out of the face's plane.
    """
    issues = []
    for obj in current().meshes:
        idx = _nonplanar_indices(obj.data, threshold_deg)
        if idx:
            message = f"{len(idx)} non-planar faces"
            if any(m.type == "SUBSURF" for m in obj.modifiers):
                message += " (has Subdivision Surface, so this may be expected)"
            issues.append(Issue(obj.name, message, value=f"{len(idx)} faces",
                                element="FACE", indices=idx))
    return issues


@AgentTools.register_fix("detect_nonplanar_faces", display_name="Triangulate Non-Planar Faces", is_quick_action=True)
def triangulate_nonplanar_faces(issues) -> str:
    """Triangulates every non-planar face in the selected meshes."""
    return f"Triangulated {_triangulate_issues(issues)} non-planar faces"


# ---------- intersections ----------

@AgentTools.register_check(
    display_name="Detect Mesh Intersections",
    category="Geometry",
    why="Overlapping geometry between separate objects wastes texture space and "
        "causes z-fighting or lighting errors in engine.",
    pass_text="None",
    is_quick_action=True,
)
def detect_intersecting_meshes() -> list:
    """Finds faces where separate selected meshes intersect each other."""
    meshes = [o for o in current().meshes if len(o.data.polygons)]
    if len(meshes) < 2:
        return []
    trees = {o.name: _world_bvh(o) for o in meshes}
    hits = {o.name: set() for o in meshes}
    for a, b in combinations(meshes, 2):
        for ia, ib in trees[a.name].overlap(trees[b.name]):
            hits[a.name].add(ia)
            hits[b.name].add(ib)
    return [Issue(name, f"{len(idx)} faces intersect another object", value=f"{len(idx)} faces",
                  element="FACE", indices=sorted(idx))
            for name, idx in hits.items() if idx]
