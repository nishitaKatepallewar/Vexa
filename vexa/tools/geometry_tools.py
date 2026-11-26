"""Geometry checks: n-gons, triangulation, non-planar faces, open edges, flipped normals,
vertex colours, modifiers, intersections, triangle and vertex budgets."""

import math
from itertools import combinations

import bmesh
import bpy
import numpy as np
from mathutils.bvhtree import BVHTree
from mathutils.geometry import distance_point_to_plane

from ..core.meshes import exported_mesh, has_shape_modifiers
from ..core.nodes import material_nodes
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


def _found(obj, find) -> tuple:
    """What find(mesh) -> indices reports for the object, as (indices, count, note).

    The count comes from the mesh as exported, with modifiers applied: a Mirror can
    close a seam, a Triangulate modifier leaves no quads, a Bevel can add n-gons.
    Indices are always in the object's own mesh, so Select Problems can show them.
    `note` is "" if modifiers don't change the result, otherwise words to say so.
    """
    own = find(obj.data)
    if not has_shape_modifiers(obj):
        return own, len(own), ""
    with exported_mesh(obj) as mesh:
        count = len(find(mesh))
    if count == len(own):
        return own, count, ""
    if not own:
        return [], count, " (made by modifiers)"
    return own, count, " after modifiers"


def _triangulate_skip_reason(issue) -> str:
    if not issue.indices:
        return "made by modifiers: change or apply them first"
    return ""


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
        idx, count, note = _found(obj, lambda mesh: np.nonzero(_face_sizes(mesh) > 4)[0].tolist())
        if count:
            issues.append(Issue(obj.name, f"{count} n-gons{note}", value=f"{count} n-gons",
                                element="FACE" if idx else None, indices=idx))
    return issues


@AgentTools.register_fix(
    "detect_ngons", display_name="Triangulate N-gons", is_quick_action=True,
    skip_reason=_triangulate_skip_reason,
    confirm=(
        "Splits every n-gon into triangles. Do this before baking normal maps: triangulating "
        "after a bake changes the triangles the bake was made on and causes shading seams. If "
        "you triangulate with a Triangulate modifier or in the exporter, you don't need this."
    ),
)
def triangulate_ngons(issues) -> str:
    """Triangulates every n-gon in the selected meshes."""
    return f"Triangulated {_triangulate_issues(issues)} n-gons"


# ---------- untriangulated meshes ----------

@AgentTools.register_check(
    display_name="Detect Untriangulated Meshes",
    category="Geometry",
    why="If the engine triangulates on import, it can split quads along a different "
        "diagonal than your baker did, which breaks shading and normal maps.",
    pass_text="All triangles",
    is_quick_action=True,
)
def detect_untriangulated_meshes() -> list:
    """Finds quads and n-gons in meshes that must be delivered fully triangulated."""
    issues = []
    for obj in current().meshes:
        idx, count, note = _found(obj, lambda mesh: np.nonzero(_face_sizes(mesh) > 3)[0].tolist())
        if count:
            issues.append(Issue(obj.name, f"{count} faces aren't triangles{note}", value=f"{count} faces",
                                target="0", element="FACE" if idx else None, indices=idx))
    return issues


@AgentTools.register_fix(
    "detect_untriangulated_meshes", display_name="Triangulate Meshes", is_quick_action=True,
    skip_reason=_triangulate_skip_reason,
    confirm=(
        "Splits every quad and n-gon into triangles. Do this before baking normal maps: "
        "triangulating after a bake changes the triangles the bake was made on and causes "
        "shading seams. If you triangulate with a Triangulate modifier or in the exporter, "
        "you don't need this."
    ),
)
def triangulate_meshes(issues) -> str:
    """Triangulates every quad and n-gon in the selected meshes."""
    return f"Triangulated {_triangulate_issues(issues)} faces"


# ---------- non-planar faces ----------

@AgentTools.register_check(
    display_name="Detect Non-Planar Faces",
    category="Geometry",
    why="Bent quads and n-gons can be split along either diagonal by the engine, "
        "changing the silhouette and shading from what you see in Blender.",
    pass_text="None",
    is_quick_action=True,
)
def detect_nonplanar_faces(threshold_deg: float = 5.0) -> list:
    """Finds quads and n-gons whose vertices don't lie on one plane.

    threshold_deg: how far (in degrees) a vertex may bend out of the face's plane.
    Slight bends are normal on organic models and harmless; 5° flags faces whose
    diagonal choice visibly changes the shape.
    """
    issues = []
    for obj in current().meshes:
        idx, count, note = _found(obj, lambda mesh: _nonplanar_indices(mesh, threshold_deg))
        if count:
            issues.append(Issue(obj.name, f"{count} non-planar faces{note}", value=f"{count} faces",
                                element="FACE" if idx else None, indices=idx))
    return issues


@AgentTools.register_fix(
    "detect_nonplanar_faces", display_name="Triangulate Non-Planar Faces", is_quick_action=True,
    skip_reason=_triangulate_skip_reason,
    confirm=(
        "Splits each bent face into triangles. Do this before baking normal maps: "
        "triangulating after a bake changes the triangles the bake was made on and causes "
        "shading seams."
    ),
)
def triangulate_nonplanar_faces(issues) -> str:
    """Triangulates every non-planar face in the selected meshes."""
    return f"Triangulated {_triangulate_issues(issues)} non-planar faces"


# ---------- open edges ----------

def _edge_face_counts(mesh) -> np.ndarray:
    """How many faces use each edge."""
    loop_edges = np.zeros(len(mesh.loops), dtype=np.int32)
    mesh.loops.foreach_get("edge_index", loop_edges)
    return np.bincount(loop_edges, minlength=len(mesh.edges))


@AgentTools.register_check(
    display_name="Detect Open Edges",
    category="Geometry",
    why="Holes and gaps show as see-through cracks in engine, break baking and "
        "collision, and an uncapped base is visible from low camera angles.",
    pass_text="Closed",
    is_quick_action=True,
)
def detect_open_edges() -> list:
    """Finds holes and gaps: edges used by one face, edges shared by more than two
    faces, and loose edges with no face at all.

    Turn this check off for assets that are open on purpose, such as planes and cards.
    """
    issues = []
    for obj in current().meshes:
        counts = _edge_face_counts(obj.data)
        idx = np.nonzero(counts != 2)[0].tolist()
        note = ""
        if has_shape_modifiers(obj):  # e.g. a Mirror closes the seam in the export
            with exported_mesh(obj) as mesh:
                counts = _edge_face_counts(mesh)
            note = "" if int(np.count_nonzero(counts != 2)) == len(idx) else " after modifiers"
        total = int(np.count_nonzero(counts != 2))
        if not total:
            continue
        parts = []
        for label, mask in (("open", counts == 1), ("non-manifold", counts > 2), ("loose", counts == 0)):
            n = int(np.count_nonzero(mask))
            if n:
                parts.append(f"{n} {label}")
        issues.append(Issue(obj.name, ", ".join(parts) + " edges" + note, value=f"{total} edges",
                            target="0", element="EDGE" if idx else None, indices=idx))
    return issues


# ---------- flipped normals ----------

INSIDE_OUT = "Inside out"

def _pieces_with_parity(n_faces: int, face_a, face_b, disagree) -> tuple:
    """Connected pieces of faces, and each face's winding relative to its piece.

    face_a/face_b: the two faces on each shared edge; disagree: True where they walk
    that edge in the same direction, i.e. their windings disagree.
    Returns (piece of each face, parity of each face, set of pieces whose windings
    can't all agree, which happens on non-orientable or doubled-up geometry).
    """
    parent = list(range(n_faces))
    parity = [0] * n_faces  # winding relative to parent: 0 same, 1 opposite

    def find(x):
        path = []
        while parent[x] != x:
            path.append(x)
            x = parent[x]
        acc = 0
        for node in reversed(path):  # compress, keeping each node's parity to the root
            acc ^= parity[node]
            parity[node] = acc
            parent[node] = x
        return x

    conflicting = set()
    for a, b, d in zip(face_a.tolist(), face_b.tolist(), disagree.tolist()):
        ra, rb = find(a), find(b)
        pa, pb = (parity[a] if a != ra else 0), (parity[b] if b != rb else 0)
        if ra == rb:
            if pa ^ pb != d:
                conflicting.add(ra)
        else:
            parent[rb] = ra
            parity[rb] = pa ^ pb ^ d
    roots = np.array([find(f) for f in range(n_faces)], dtype=np.int64)
    rel = np.array([parity[f] if parent[f] != f else 0 for f in range(n_faces)], dtype=np.int64)
    return roots, rel, {find(r) for r in conflicting}


def _inward_faces(mesh) -> tuple:
    """Faces on closed parts of the mesh that point inwards, as two sorted lists.

    The first holds faces that disagree with most of their piece: clearly mistakes.
    The second holds the inward faces of pieces that mostly face inwards: inside
    out, or meant to be seen from inside, such as a room or a sky dome.

    For each closed piece (every edge shared by exactly two faces), neighbouring faces
    must walk their shared edge in opposite directions; that fixes every face's winding
    relative to the piece. The piece's signed volume then says which winding points
    out. Pieces with no volume (e.g. two copies of one face) or whose windings can't
    agree have no inside, so they're skipped. Everything is linear in the face count,
    so no mesh shape can make it slow.
    """
    n_faces, n_loops = len(mesh.polygons), len(mesh.loops)
    if not n_faces:
        return [], []
    starts = np.zeros(n_faces, dtype=np.int64)
    totals = np.zeros(n_faces, dtype=np.int64)
    loop_verts = np.zeros(n_loops, dtype=np.int64)
    loop_edges = np.zeros(n_loops, dtype=np.int64)
    co = np.zeros(len(mesh.vertices) * 3, dtype=np.float64)
    mesh.polygons.foreach_get("loop_start", starts)
    mesh.polygons.foreach_get("loop_total", totals)
    mesh.loops.foreach_get("vertex_index", loop_verts)
    mesh.loops.foreach_get("edge_index", loop_edges)
    mesh.vertices.foreach_get("co", co)
    co = co.reshape(-1, 3)
    face_of_loop = np.repeat(np.arange(n_faces), totals)
    nxt = np.arange(n_loops) + 1
    wrap = nxt == (starts + totals)[face_of_loop]
    nxt[wrap] = starts[face_of_loop[wrap]]

    # A piece is open if any of its edges isn't shared by exactly two faces.
    per_edge = np.bincount(loop_edges, minlength=len(mesh.edges))
    open_face = np.zeros(n_faces, dtype=bool)
    open_face[face_of_loop[per_edge[loop_edges] != 2]] = True

    order = np.argsort(loop_edges, kind="stable")
    shared = loop_edges[order][1:] == loop_edges[order][:-1]
    loop_a, loop_b = order[:-1][shared], order[1:][shared]
    disagree = loop_verts[loop_a] == loop_verts[loop_b]  # same start vertex: same direction
    piece, parity, conflicting = _pieces_with_parity(
        n_faces, face_of_loop[loop_a], face_of_loop[loop_b], disagree)

    is_open = np.zeros(n_faces, dtype=bool)  # indexed by piece root
    is_open[np.unique(piece[open_face])] = True
    if conflicting:
        is_open[list(conflicting)] = True
    closed = ~is_open[piece]
    if not closed.any():
        return [], []

    # Signed volume of each face as seen from its piece's centre (fan triangles).
    loop_piece = piece[face_of_loop]
    weight = np.bincount(loop_piece, minlength=n_faces)
    centre = np.column_stack([np.bincount(loop_piece, weights=co[loop_verts, k], minlength=n_faces)
                              for k in range(3)]) / np.maximum(weight, 1)[:, None]
    corner = np.arange(n_loops) - starts[face_of_loop]
    fan = (corner >= 1) & (corner <= totals[face_of_loop] - 2)
    p0 = co[loop_verts[starts[face_of_loop[fan]]]] - centre[loop_piece[fan]]
    p1 = co[loop_verts[fan]] - centre[loop_piece[fan]]
    p2 = co[loop_verts[nxt[fan]]] - centre[loop_piece[fan]]
    tri_volume = np.einsum("ij,ij->i", p0, np.cross(p1, p2)) / 6.0
    face_volume = np.bincount(face_of_loop[fan], weights=tri_volume, minlength=n_faces)

    sign = np.where(parity == 0, 1.0, -1.0)
    volume = np.bincount(piece, weights=sign * face_volume, minlength=n_faces)
    size = np.bincount(piece, weights=np.abs(face_volume), minlength=n_faces)
    has_inside = np.abs(volume) > 1e-6 * size
    # Faces whose winding disagrees with the one that encloses positive volume.
    outward_parity = np.where(volume > 0, 0, 1)
    inward = closed & has_inside[piece] & (parity != outward_parity[piece])
    if not inward.any():
        return [], []
    # A piece whose inward faces cover more than half its area is inside out as a whole.
    area = np.zeros(n_faces, dtype=np.float64)
    mesh.polygons.foreach_get("area", area)
    inward_area = np.bincount(piece, weights=area * inward, minlength=n_faces)
    total_area = np.bincount(piece, weights=area, minlength=n_faces)
    whole = inward & (inward_area[piece] > 0.5 * total_area[piece])
    return np.nonzero(inward & ~whole)[0].tolist(), np.nonzero(whole)[0].tolist()


@AgentTools.register_check(
    display_name="Detect Flipped Normals",
    category="Geometry",
    why="Faces pointing inwards are invisible in engine (backface culling) or shade "
        "dark, and they break normal map bakes.",
    severity="ERROR",
    pass_text="All outward",
    is_quick_action=True,
)
def detect_flipped_normals() -> list:
    """Finds faces whose normals point into the mesh instead of out of it.

    Only closed parts of a mesh are checked: on an open surface, such as a plane,
    neither side is "outside". Pieces that mostly face inwards are reported apart,
    as inside out: they may be rooms or sky domes.
    """
    issues = []
    for obj in current().meshes:
        flipped, inside_out = _inward_faces(obj.data)
        if flipped:
            issues.append(Issue(obj.name, f"{len(flipped)} faces point inwards", value=f"{len(flipped)} faces",
                                target="0", element="FACE", indices=flipped))
        if inside_out:
            issues.append(Issue(obj.name, f"{INSIDE_OUT}: {len(inside_out)} faces face inwards",
                                value=f"{len(inside_out)} faces", target="0", element="FACE",
                                indices=inside_out))
    return issues


def _normals_skip_reason(issue) -> str:
    if issue.message.startswith(INSIDE_OUT):
        return "most of the piece faces inwards: fine for rooms and sky domes, else flip it by hand"
    return ""


@AgentTools.register_fix(
    "detect_flipped_normals", display_name="Flip Normals Outward", is_quick_action=True, safe=True,
    skip_reason=_normals_skip_reason,
)
def flip_normals_outward(issues) -> str:
    """Flips faces that point the other way from the rest of their piece.

    Pieces that mostly face inwards are left: they may be meant to be seen from
    inside, like a room or a sky dome.
    """
    scene = current().scene
    total = 0
    for issue in issues:
        obj = scene.objects.get(issue.object_name)
        if not obj:
            continue
        bm = bmesh.new()
        bm.from_mesh(obj.data)
        bm.faces.ensure_lookup_table()
        faces = [bm.faces[i] for i in issue.indices if i < len(bm.faces)]
        bmesh.ops.reverse_faces(bm, faces=faces)
        bm.to_mesh(obj.data)
        bm.free()
        obj.data.update()
        total += len(faces)
    return f"Flipped {total} faces"


# ---------- vertex colours ----------

@AgentTools.register_check(
    display_name="Detect Vertex Colors",
    category="Geometry",
    why="Leftover vertex colours (Maya's colour sets) export with the mesh, add memory, "
        "and can tint or mask the material in engine.",
    pass_text="None",
)
def detect_color_attributes() -> list:
    """Finds meshes that still have vertex colour attributes (colour sets)."""
    issues = []
    for obj in current().meshes:
        names = [attr.name for attr in obj.data.color_attributes]
        if names:
            issues.append(Issue(obj.name, "Vertex colors: " + ", ".join(names),
                                value=f"{len(names)} attributes", target="0"))
    return issues


def _used_color_attributes(obj) -> dict:
    """Colour attributes the object's materials read, as {name: material name}.

    A Color Attribute node with no name reads the mesh's default colour attribute.
    """
    attrs = obj.data.color_attributes
    default = getattr(attrs, "default_color_name", "") or (attrs[0].name if len(attrs) else "")
    used = {}
    for slot in obj.material_slots:
        if slot.material is None:
            continue
        for node in material_nodes(slot.material):
            if node.type == "VERTEX_COLOR":
                name = node.layer_name or default
            elif node.type == "ATTRIBUTE" and node.attribute_type == "GEOMETRY":
                name = node.attribute_name
            else:
                continue
            if name in attrs:
                used.setdefault(name, slot.material.name)
    return used


def _color_skip_reason(issue) -> str:
    obj = current().scene.objects.get(issue.object_name)
    if obj is None:
        return "not in the scene"
    if any(m.type == "NODES" for m in obj.modifiers):
        return "geometry nodes may read them"
    used = _used_color_attributes(obj)
    if used and len(used) == len(obj.data.color_attributes):
        return "used by " + ", ".join(sorted(set(used.values())))
    return ""


@AgentTools.register_fix(
    "detect_color_attributes", display_name="Remove Vertex Colors", safe=True,
    skip_reason=_color_skip_reason,
)
def remove_color_attributes(issues) -> str:
    """Removes the vertex colour attributes no material on the mesh reads.

    Colours a material uses (Color Attribute or Attribute node, also inside node
    groups) are kept: removing them would change how the asset looks.
    """
    scene = current().scene
    removed, kept = 0, 0
    for issue in issues:
        obj = scene.objects.get(issue.object_name)
        if not obj:
            continue
        attrs = obj.data.color_attributes
        used = _used_color_attributes(obj)
        for name in [attr.name for attr in attrs]:
            if name in used:
                kept += 1
                continue
            attrs.remove(attrs[name])
            removed += 1
    msg = f"Removed {removed} vertex color attributes"
    return msg + (f", kept {kept} a material uses" if kept else "")


# ---------- unapplied modifiers ----------

def _modifier_types() -> set:
    return {item.identifier for item in bpy.types.Modifier.bl_rna.properties["type"].enum_items}


@AgentTools.register_check(
    display_name="Detect Unapplied Modifiers",
    category="Geometry",
    why="Modifiers are the mesh's construction history. Depending on export settings "
        "they're dropped or baked differently, so the delivered mesh isn't what you see.",
    pass_text="None",
)
def detect_unapplied_modifiers(ignore: list = ["ARMATURE"]) -> list:  # noqa: B006 - never mutated
    """Finds meshes with modifiers that haven't been applied.

    ignore: modifier types to allow, e.g. ["ARMATURE", "TRIANGULATE"]. Armature is
    allowed by default because skinned meshes need it.
    """
    allowed = {t.upper() for t in ignore}
    unknown = allowed - _modifier_types()
    if unknown:
        raise ValueError(f"unknown modifier types: {', '.join(sorted(unknown))}")
    issues = []
    for obj in current().meshes:
        names = [m.name for m in obj.modifiers if m.type not in allowed]
        if names:
            issues.append(Issue(obj.name, "Unapplied modifiers: " + ", ".join(names),
                                value=f"{len(names)} modifiers", target="0"))
    return issues


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


# ---------- triangle budget ----------

@AgentTools.register_check(
    display_name="Detect Over Triangle Budget",
    category="Geometry",
    why="Every platform has a performance budget. Going over it can get an asset "
        "rejected or force an artist to redo LODs late.",
    pass_text="Within budget",
)
def detect_over_triangle_budget(max_tris: int = 20000) -> list:
    """Finds meshes whose triangle count exceeds a budget.

    max_tris: the maximum number of triangles allowed per mesh, counted with
    modifiers applied, as exported.
    """
    issues = []
    for obj in current().meshes:
        with exported_mesh(obj) as mesh:
            tris = triangle_count(mesh)
        if tris > max_tris:
            own = triangle_count(obj.data)
            note = f" ({own:,} before modifiers)" if own != tris else ""
            issues.append(Issue(obj.name, "Over triangle budget" + note,
                                value=f"{tris:,} tris", target=f"{max_tris:,}"))
    return issues


# ---------- vertex budget ----------

@AgentTools.register_check(
    display_name="Detect Over Vertex Budget",
    category="Geometry",
    why="Work orders often set a vertex budget per asset. Going over it means the "
        "asset is sent back, or a lead has to approve the extra cost.",
    pass_text="Within budget",
)
def detect_over_vertex_budget(max_verts: int = 10000) -> list:
    """Finds meshes whose vertex count exceeds a budget.

    max_verts: the maximum number of vertices allowed per mesh, as counted in
    Blender with modifiers applied. Engines count more where UV seams and hard
    edges split vertices.
    """
    issues = []
    for obj in current().meshes:
        with exported_mesh(obj) as mesh:
            verts = len(mesh.vertices)
        if verts > max_verts:
            own = len(obj.data.vertices)
            note = f" ({own:,} before modifiers)" if own != verts else ""
            issues.append(Issue(obj.name, "Over vertex budget" + note,
                                value=f"{verts:,} verts", target=f"{max_verts:,}"))
    return issues
