"""UV checks: UV map present, no extra UV maps, UVs inside 0–1, no flipped UVs, lightmap channel."""

import numpy as np
from mathutils.bvhtree import BVHTree

from ..core.nodes import material_nodes
from ..core.registry import AgentTools
from ..core.results import Issue, plural
from ..core.scope import current


@AgentTools.register_check(
    display_name="Detect Missing UV Maps",
    category="UVs",
    why="A mesh with no UV map can't be textured or lightmapped, and most engines "
        "warn or fail on import.",
    severity="ERROR",
    pass_text="All meshes",
)
def detect_missing_uv_maps() -> list:
    """Finds meshes with no UV map at all."""
    return [Issue(o.name, "No UV map", value="0 UV maps", target="≥ 1")
            for o in current().meshes if len(o.data.uv_layers) == 0]


@AgentTools.register_check(
    display_name="Detect Extra UV Maps",
    category="UVs",
    why="Extra UV maps are exported as extra UV channels, which cost memory and can "
        "be picked up by the wrong material or lightmap setting in engine.",
    pass_text="None",
)
def detect_extra_uv_maps(max_uv_maps: int = 1) -> list:
    """Finds meshes with more UV maps than allowed.

    max_uv_maps: how many UV maps a mesh may have (1 means no second UV channel).
    """
    if max_uv_maps < 1:
        raise ValueError("max_uv_maps must be at least 1")
    issues = []
    for obj in current().meshes:
        layers = obj.data.uv_layers
        if len(layers) > max_uv_maps:
            extra = [layer.name for layer in layers[max_uv_maps:]]
            issues.append(Issue(obj.name, "Extra UV maps: " + ", ".join(extra),
                                value=f"{len(layers)} UV maps", target=f"≤ {max_uv_maps}"))
    return issues


def _protected_uv_maps(obj) -> dict:
    """UV maps that must stay, as {name: why}: the render map and maps a material reads."""
    layers = obj.data.uv_layers
    kept = {layer.name: "textures use it" for layer in layers if layer.active_render}
    for slot in obj.material_slots:
        if slot.material is None:
            continue
        for node in material_nodes(slot.material):
            name = ""
            if node.type in {"UVMAP", "NORMAL_MAP", "TANGENT"}:
                name = getattr(node, "uv_map", "")
            elif node.type == "ATTRIBUTE" and node.attribute_type == "GEOMETRY":
                name = node.attribute_name
            if name in layers:
                kept.setdefault(name, f"used by {slot.material.name}")
    return kept


def _removable_uv_maps(obj, max_uv_maps: int) -> list:
    kept = _protected_uv_maps(obj)
    return [layer.name for layer in obj.data.uv_layers[max_uv_maps:] if layer.name not in kept]


def _uv_maps_skip_reason(issue, max_uv_maps: int = 1) -> str:
    obj = current().scene.objects.get(issue.object_name)
    if obj is None:
        return "not in the scene"
    if any(m.type == "NODES" for m in obj.modifiers):
        return "geometry nodes may read them"
    if not _removable_uv_maps(obj, max_uv_maps):
        protected = _protected_uv_maps(obj)
        return "; ".join(f"{layer.name}: {protected[layer.name]}" for layer in obj.data.uv_layers[max_uv_maps:])
    return ""


@AgentTools.register_fix(
    "detect_extra_uv_maps", display_name="Remove Extra UV Maps", safe=True,
    skip_reason=_uv_maps_skip_reason,
)
def remove_extra_uv_maps(issues, max_uv_maps: int = 1) -> str:
    """Removes UV maps after the first max_uv_maps on each flagged mesh.

    Keeps the render UV map (the one textures use) and any map a material reads by
    name (UV Map, Normal Map, Tangent or Attribute node), so nothing changes look.
    """
    scene = current().scene
    removed, kept = 0, []
    for issue in issues:
        obj = scene.objects.get(issue.object_name)
        if not obj:
            continue
        layers = obj.data.uv_layers
        removable = _removable_uv_maps(obj, max_uv_maps)
        protected = _protected_uv_maps(obj)
        kept += [f"{layer.name} ({protected[layer.name]})" for layer in layers[max_uv_maps:]
                 if layer.name in protected]
        for name in removable:
            layers.remove(layers[name])
        removed += len(removable)
    msg = f"Removed {removed} UV maps"
    if kept:
        msg += ". Kept: " + ", ".join(kept)
    return msg


# ---------- UVs outside 0–1 ----------

@AgentTools.register_check(
    display_name="Detect UVs Outside 0–1",
    category="UVs",
    why="Some engines and stores require every UV inside the 0–1 square. Outside it, "
        "textures tile or clamp, so the asset looks different from your bake.",
    pass_text="Inside 0–1",
)
def detect_uvs_outside_0_1() -> list:
    """Finds meshes whose render UV map goes outside the 0–1 square. Selects those faces."""
    issues = []
    for obj in current().meshes:
        mesh = obj.data
        layer = _render_uv_layer(mesh)
        if layer is None or not len(mesh.loops):
            continue
        uv = np.zeros(len(mesh.loops) * 2, dtype=np.float32)
        layer.data.foreach_get("uv", uv)
        uv = uv.reshape(-1, 2)
        outside_loop = np.any((uv < -1e-4) | (uv > 1 + 1e-4), axis=1)
        if not outside_loop.any():
            continue
        starts = np.zeros(len(mesh.polygons), dtype=np.int64)
        totals = np.zeros(len(mesh.polygons), dtype=np.int64)
        mesh.polygons.foreach_get("loop_start", starts)
        mesh.polygons.foreach_get("loop_total", totals)
        face_of_loop = np.repeat(np.arange(len(starts)), totals)
        idx = np.unique(face_of_loop[outside_loop]).tolist()
        issues.append(Issue(obj.name, f"UVs outside 0–1 on {plural(len(idx), 'face')} ({layer.name})",
                            value=f"range {uv.min():.2f}–{uv.max():.2f}", target="0–1",
                            element="FACE", indices=idx))
    return issues


# ---------- flipped UVs ----------

def _render_uv_layer(mesh):
    """The UV map textures render with, or None."""
    layers = mesh.uv_layers
    return next((layer for layer in layers if layer.active_render), layers[0] if len(layers) else None)


def _face_loops(mesh):
    """Each face's first loop and loop count, and the face each loop belongs to."""
    starts = np.zeros(len(mesh.polygons), dtype=np.int64)
    totals = np.zeros(len(mesh.polygons), dtype=np.int64)
    mesh.polygons.foreach_get("loop_start", starts)
    mesh.polygons.foreach_get("loop_total", totals)
    return starts, totals, np.repeat(np.arange(len(starts)), totals)


def _uv_signed_areas(uv: np.ndarray, starts, totals, face_of_loop) -> np.ndarray:
    """Signed area of every face in UV space. Negative means mirrored (flipped)."""
    nxt = np.arange(len(uv)) + 1
    wrap = nxt == (starts + totals)[face_of_loop]
    nxt[wrap] = starts[face_of_loop[wrap]]
    cross = uv[:, 0] * uv[nxt, 1] - uv[nxt, 0] * uv[:, 1]
    return 0.5 * np.bincount(face_of_loop, weights=cross, minlength=len(starts))


def _distinct_uv_faces(uv: np.ndarray, starts, totals, faces) -> np.ndarray:
    """`faces` without exact duplicates in UV space.

    Repeated parts joined into one mesh (bolts, rivets) share one UV layout, so
    thousands of identical faces stack on one spot. They cover the same space, so
    one of each is enough, and each lookup no longer has to wade through the stack.
    """
    keep = []
    for size in np.unique(totals[faces]).tolist():
        same_size = faces[totals[faces] == size]
        loops = starts[same_size][:, None] + np.arange(size)
        coords = np.round(uv[loops].reshape(len(same_size), -1), 6)
        _, first = np.unique(coords, axis=0, return_index=True)
        keep.append(same_size[np.sort(first)])
    return np.sort(np.concatenate(keep))


def _flipped_uv_faces(mesh, allow_overlapping: bool) -> list:
    layer = _render_uv_layer(mesh)
    if layer is None or not len(mesh.polygons):
        return []
    uv = np.zeros(len(mesh.loops) * 2, dtype=np.float32)
    layer.data.foreach_get("uv", uv)
    uv = uv.reshape(-1, 2).astype(np.float64)
    starts, totals, face_of_loop = _face_loops(mesh)
    areas = _uv_signed_areas(uv, starts, totals, face_of_loop)
    flipped = np.nonzero(areas < -1e-12)[0]
    unflipped = np.nonzero(areas > 1e-12)[0]
    if not (len(flipped) and allow_overlapping and len(unflipped)):
        return flipped.tolist()
    # A mirrored shell stacked on top of an unflipped one is fine (shared texture
    # space). Keep only flipped faces whose centre isn't covered by an unflipped face.
    loops_of = np.split(np.arange(len(uv)), starts[1:])
    points = np.column_stack([uv, np.zeros(len(uv))]).tolist()
    covering = _distinct_uv_faces(uv, starts, totals, unflipped)
    tree = BVHTree.FromPolygons(points, [loops_of[i].tolist() for i in covering.tolist()])
    centres = np.column_stack([np.bincount(face_of_loop, weights=uv[:, k], minlength=len(starts)) / totals
                               for k in (0, 1)])
    ray_cast, down = tree.ray_cast, (0.0, 0.0, -1.0)
    return [index for index, (cu, cv) in zip(flipped.tolist(), centres[flipped].tolist())
            if ray_cast((cu, cv, 1.0), down)[0] is None]


@AgentTools.register_check(
    display_name="Detect Flipped UVs",
    category="UVs",
    why="Mirrored UVs make normal maps light the wrong way and break baking, unless "
        "they're a mirrored copy stacked on the original to share texture space.",
    pass_text="None",
)
def detect_flipped_uvs(allow_overlapping: bool = True) -> list:
    """Finds faces whose UVs are mirrored (shown red in Maya's UV editor).

    allow_overlapping: allow a mirrored face that sits on top of an unflipped one,
    e.g. a symmetric shell stacked onto its other half.
    """
    issues = []
    for obj in current().meshes:
        idx = _flipped_uv_faces(obj.data, allow_overlapping)
        if idx:
            issues.append(Issue(obj.name, f"{len(idx)} faces have flipped UVs", value=f"{len(idx)} faces",
                                target="0", element="FACE", indices=idx))
    return issues


# ---------- lightmap ----------

@AgentTools.register_check(
    display_name="Detect Lightmap UV Issues",
    category="UVs",
    why="Unreal bakes lighting from the second UV channel. If it's missing or spills "
        "outside 0–1, lighting builds fail or bake black and blotchy.",
    severity="ERROR",
    pass_text="Present, in 0–1",
)
def detect_missing_lightmap_uvs(channel: int = 1) -> list:
    """Finds meshes without a lightmap UV channel, or whose lightmap UVs leave 0–1.

    channel: index of the lightmap UV map (Unreal uses 1, the second map).
    """
    issues = []
    for obj in current().meshes:
        layers = obj.data.uv_layers
        if len(layers) <= channel:
            issues.append(Issue(obj.name, f"No lightmap UV channel (UV{channel})",
                                value=f"{len(layers)} UV maps", target=f"≥ {channel + 1}"))
            continue
        uv = np.zeros(len(obj.data.loops) * 2, dtype=np.float32)
        layers[channel].data.foreach_get("uv", uv)
        if uv.size and (uv.min() < -1e-4 or uv.max() > 1 + 1e-4):
            issues.append(Issue(obj.name, f"Lightmap UVs (UV{channel}) outside 0–1",
                                value=f"range {uv.min():.2f}–{uv.max():.2f}", target="0–1"))
    return issues
