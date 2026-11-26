"""Material and texture checks: missing or unwanted textures, colour space, texture size
and format, materials per mesh, material slots, unused materials."""

import os
import time
from contextlib import contextmanager

import bpy
import numpy as np

from ..core.meshes import exported_mesh
from ..core.nodes import material_nodes
from ..core.registry import AgentTools
from ..core.results import Issue
from ..core.scope import current


def _materials(obj):
    for slot in obj.material_slots:
        if slot.material is not None:
            yield slot.material


def _image_nodes(mat):
    """Every Image Texture node the material uses, including inside node groups."""
    for node in material_nodes(mat):
        if node.type == "TEX_IMAGE":
            yield node


def _missing_reason(image) -> str:
    """Why the engine won't get this image, or "" if it will."""
    if image is None:
        return "no image"
    if image.source == "GENERATED" and not image.packed_file:
        return "made in Blender and never saved"
    if image.source not in {"FILE", "SEQUENCE", "TILED"}:
        return ""
    if image.is_dirty:
        return "has unsaved changes"
    if image.packed_file:
        return ""
    # Pass the library so paths inside linked .blend files resolve correctly
    # (see the API docs, "File Paths & String Encoding").
    path = bpy.path.abspath(image.filepath, library=image.library)
    return "" if path and os.path.exists(path) else "file not found"


# ---------- missing textures ----------

@AgentTools.register_check(
    display_name="Detect Missing Textures",
    category="Texture",
    why="Image nodes with no image, pointing at a file that no longer exists, or "
        "holding a bake that was never saved, export as blank or pink materials.",
    severity="ERROR",
    pass_text="All found",
    is_quick_action=True,
)
def detect_missing_textures() -> list:
    """Finds Image Texture nodes with no image, a missing file, or an image that was
    made or changed in Blender and not saved (e.g. a bake). Looks inside node groups."""
    issues = []
    for obj in current().meshes:
        missing = []
        for mat in _materials(obj):
            for node in _image_nodes(mat):
                reason = _missing_reason(node.image)
                if reason == "no image":
                    missing.append(f"{mat.name}: no image")
                elif reason:
                    missing.append(f"{mat.name}: {node.image.name}"
                                   + ("" if reason == "file not found" else f" ({reason})"))
        if missing:
            more = "…" if len(missing) > 3 else ""
            issues.append(Issue(obj.name, "Missing: " + ", ".join(missing[:3]) + more,
                                value=f"{len(missing)} missing"))
    return issues


# Most files looked at when searching the project folder for a missing texture.
_SEARCH_LIMIT = 50_000


_INDEX_CACHE = {}  # root -> (time, index): one walk serves a whole check run


def _project_files(root: str) -> dict:
    """{file name: [paths]} under root, skipping hidden folders. Stops at _SEARCH_LIMIT
    files, and then says so with the key None. Reuses a walk up to 5 seconds old."""
    cached = _INDEX_CACHE.get(root)
    if cached and time.monotonic() - cached[0] < 5:
        return cached[1]
    index = _walk(root)
    _INDEX_CACHE.clear()
    _INDEX_CACHE[root] = (time.monotonic(), index)
    return index


def _walk(root: str) -> dict:
    index, seen = {}, 0
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if not d.startswith(".")]
        for name in filenames:
            index.setdefault(name, []).append(os.path.join(dirpath, name))
        seen += len(filenames)
        if seen > _SEARCH_LIMIT:
            index[None] = []
            break
    return index


def _missing_files(obj) -> list:
    """Images on the object's materials whose file isn't found: [(material, image)]."""
    out = []
    for mat in _materials(obj):
        for node in _image_nodes(mat):
            if node.image is not None and _missing_reason(node.image) == "file not found":
                out.append((mat, node.image))
    return out


def _relink_target(image, index) -> str:
    """The one file in the project with the image's file name, or ""."""
    matches = index.get(os.path.basename(bpy.path.abspath(image.filepath).replace("\\", "/")), [])
    return matches[0] if len(matches) == 1 else ""


def _relink_skip_reason(issue) -> str:
    if not bpy.data.filepath:
        return "save the .blend first, so Vexa knows which folder to search"
    obj = current().scene.objects.get(issue.object_name)
    missing = _missing_files(obj) if obj else []
    if not missing:
        return "no image files to look for (empty nodes or unsaved images)"
    index = _project_files(os.path.dirname(bpy.data.filepath))
    if not any(_relink_target(image, index) for _, image in missing):
        return "no single file with the same name in the .blend's folder"
    return ""


@AgentTools.register_fix(
    "detect_missing_textures", display_name="Relink Missing Textures", safe=True,
    skip_reason=_relink_skip_reason,
)
def relink_missing_textures(issues) -> str:
    """Points each missing image at the file with the same name in the .blend's folder
    or its subfolders, only when exactly one such file exists.

    A stricter Find Missing Files: an image is never relinked to one of two files with
    the same name. Images with no file (empty nodes, unsaved bakes) are left.
    """
    scene = current().scene
    index = _project_files(os.path.dirname(bpy.data.filepath))
    relinked, left = [], []
    for issue in issues:
        obj = scene.objects.get(issue.object_name)
        for _, image in _missing_files(obj) if obj else []:
            if image.name in relinked:
                continue
            target = _relink_target(image, index)
            if not target:
                left.append(image.name)
                continue
            image.filepath = bpy.path.relpath(target)
            image.reload()
            relinked.append(image.name)
    msg = f"Relinked {len(relinked)} images"
    if left:
        msg += ". Not found once in the project: " + ", ".join(sorted(set(left)))
    return msg


# ---------- colour space ----------

def _is_likely_normal_map(node, tree) -> bool:
    """Heuristic: check if node is likely a normal map based on connections."""
    for output_socket in node.outputs:
        if output_socket.is_linked:
            for link in output_socket.links:
                to_node = link.to_node
                if to_node.type == "NORMAL_MAP" or to_node.type == "BUMP":
                    return True
    return False


def _is_likely_roughness_map(node, tree) -> bool:
    """Heuristic: check if node is likely a roughness map based on connections."""
    for output_socket in node.outputs:
        if output_socket.is_linked:
            for link in output_socket.links:
                to_socket = link.to_socket
                if "Roughness" in to_socket.name or "Rough" in to_socket.name:
                    return True
    return False


def _is_likely_metallic_map(node, tree) -> bool:
    """Heuristic: check if node is likely a metallic map based on connections."""
    for output_socket in node.outputs:
        if output_socket.is_linked:
            for link in output_socket.links:
                to_socket = link.to_socket
                if "Metallic" in to_socket.name or "Metal" in to_socket.name:
                    return True
    return False


def _is_likely_albedo_map(node, tree) -> bool:
    """Heuristic: check if node is likely an albedo/diffuse map based on connections."""
    for output_socket in node.outputs:
        if output_socket.is_linked:
            for link in output_socket.links:
                to_socket = link.to_socket
                if (
                    "Base Color" in to_socket.name
                    or "Albedo" in to_socket.name
                    or "Diffuse" in to_socket.name
                ):
                    return True
    return False


def _expected_color_space(node, tree):
    """(role, expected colour space) for an image node, or (None, None) if unknown."""
    if _is_likely_normal_map(node, tree):
        return "Normal", "Non-Color"
    if _is_likely_roughness_map(node, tree):
        return "Roughness", "Non-Color"
    if _is_likely_metallic_map(node, tree):
        return "Metallic", "Non-Color"
    if _is_likely_albedo_map(node, tree):
        return "Albedo", "sRGB"
    return None, None


@AgentTools.register_check(
    display_name="Detect Color Space Issues",
    category="Texture",
    why="Normal, roughness and metallic maps set to sRGB (or colour maps set to "
        "Non-Color) look wrong in engine: shading turns washed out or too dark.",
    pass_text="Correct",
    is_quick_action=True,
)
def detect_color_space_issues() -> list:
    """Finds data maps (normal, roughness, metallic) set to sRGB, and colour maps set to Non-Color.

    Float images (EXR, HDR) are skipped: they're linear on purpose.
    """
    issues, seen = [], set()
    for obj in current().meshes:
        for mat in _materials(obj):
            for node in _image_nodes(mat):
                image = node.image
                if image is None or image.name in seen or image.is_float:
                    continue  # float images (EXR, HDR) hold linear values on purpose
                role, expected = _expected_color_space(node, mat.node_tree)
                actual = image.colorspace_settings.name
                if expected and actual != expected:
                    seen.add(image.name)
                    issues.append(Issue(obj.name, f"{image.name}: {role} map in {actual}",
                                        value=image.name, target=expected))
    return issues


def _color_space_skip_reason(issue) -> str:
    """An image used both as colour and as data can't have one right colour space."""
    wanted = set()
    for mat in bpy.data.materials:
        for node in _image_nodes(mat):
            if node.image is not None and node.image.name == issue.value:
                wanted.add(_expected_color_space(node, mat.node_tree)[1])
    wanted.discard(None)
    if len(wanted) > 1:
        return "used both as a colour map and as a data map"
    return ""


@AgentTools.register_fix(
    "detect_color_space_issues", display_name="Fix Color Spaces", safe=True,
    skip_reason=_color_space_skip_reason,
)
def fix_color_spaces(issues) -> str:
    """Sets each flagged image to the colour space its role needs.

    The role comes from the socket the image is plugged into directly: Base Color
    means sRGB; Normal Map, Bump, Roughness and Metallic mean Non-Color.
    """
    fixed = 0
    for issue in issues:
        image = bpy.data.images.get(issue.value)
        if image:
            image.colorspace_settings.name = issue.target
            fixed += 1
    return f"Fixed colour space on {fixed} images"


# ---------- texture size ----------

@AgentTools.register_check(
    display_name="Detect Invalid Texture Sizes",
    category="Texture",
    why="Engines and marketplaces expect power-of-two textures within a maximum size "
        "so they compress and mipmap correctly.",
    pass_text="Power of two",
)
def detect_invalid_texture_sizes(power_of_two: bool = True, max_size: int = 8192) -> list:
    """Finds textures that aren't power-of-two sized, or exceed a maximum size.

    power_of_two: require both dimensions to be powers of two.
    max_size: the largest allowed width or height, in pixels.
    """
    issues, seen = [], set()
    for obj in current().meshes:
        for mat in _materials(obj):
            for node in _image_nodes(mat):
                image = node.image
                if image is None or image.name in seen:
                    continue
                w, h = image.size[:]
                if w == 0 or h == 0:
                    continue
                seen.add(image.name)
                problems = []
                if power_of_two and (w & (w - 1) or h & (h - 1)):
                    problems.append("not power of two")
                if max(w, h) > max_size:
                    problems.append(f"over {max_size}px")
                if problems:
                    issues.append(Issue(obj.name, f"{image.name}: " + ", ".join(problems),
                                        value=f"{image.name} {w}×{h}", target=f"2ⁿ ≤ {max_size}"))
    return issues


# ---------- texture format ----------

# File extensions and Blender's image format names, mapped to one short name.
_FORMATS = {
    "png": "PNG", "jpg": "JPEG", "jpeg": "JPEG", "tga": "TGA", "targa": "TGA",
    "tif": "TIFF", "tiff": "TIFF", "exr": "EXR", "open_exr": "EXR", "bmp": "BMP",
    "hdr": "HDR", "webp": "WEBP", "dds": "DDS", "psd": "PSD",
}


def _image_format(image) -> str:
    """The image's file format as a short name, e.g. "PNG", or "" if it has no file."""
    ext = os.path.splitext(image.filepath)[1].lstrip(".").lower()
    if ext:
        return _FORMATS.get(ext, ext.upper())
    if image.packed_file:
        return _FORMATS.get(image.file_format.lower(), image.file_format)
    return ""  # generated in Blender, never saved


@AgentTools.register_check(
    display_name="Detect Wrong Texture Format",
    category="Texture",
    why="Pipelines and engines expect specific file formats. Anything else is rejected "
        "on delivery or imports with the wrong compression or alpha.",
    pass_text="Correct",
)
def detect_wrong_texture_format(formats: list = ["PNG"]) -> list:  # noqa: B006 - never mutated
    """Finds textures saved in a file format that isn't allowed.

    formats: allowed formats, e.g. ["PNG"] or ["PNG", "TGA"]. Images generated in
    Blender and never saved are skipped.
    """
    allowed = {_FORMATS.get(f.lower(), f.upper()) for f in formats}
    unknown = allowed - set(_FORMATS.values())
    if unknown:
        raise ValueError(f"unknown formats: {', '.join(sorted(unknown))}")
    issues, seen = [], set()
    for obj in current().meshes:
        for mat in _materials(obj):
            for node in _image_nodes(mat):
                image = node.image
                if image is None or image.name in seen:
                    continue
                seen.add(image.name)
                fmt = _image_format(image)
                if fmt and fmt not in allowed:
                    issues.append(Issue(obj.name, f"{image.name}: {fmt}", value=f"{image.name} {fmt}",
                                        target=" or ".join(sorted(allowed))))
    return issues


# ---------- material slots ----------

def _used_material_indices(obj) -> set:
    """Material slots the exported mesh's faces use, modifiers included (e.g. a
    Solidify rim material)."""
    with exported_mesh(obj) as mesh:
        indices = np.zeros(len(mesh.polygons), dtype=np.int32)
        mesh.polygons.foreach_get("material_index", indices)
    return set(np.unique(indices).tolist())


@AgentTools.register_check(
    display_name="Detect Unused Material Slots",
    category="Texture",
    why="Empty or unused slots create extra material elements on import, which cost "
        "draw calls and confuse whoever sets up materials in engine.",
    pass_text="None",
)
def detect_unused_material_slots() -> list:
    """Finds material slots no face uses, and empty slots that faces do use."""
    issues = []
    for obj in current().meshes:
        if not obj.material_slots:
            continue
        used = _used_material_indices(obj)
        unused = [i for i in range(len(obj.material_slots)) if i not in used]
        empty = [i for i, s in enumerate(obj.material_slots) if s.material is None and i in used]
        parts = []
        if unused:
            parts.append(f"{len(unused)} unused")
        if empty:
            parts.append(f"{len(empty)} empty but assigned to faces")
        if parts:
            issues.append(Issue(obj.name, "Material slots: " + ", ".join(parts),
                                value=f"{len(unused) + len(empty)} slots"))
    return issues


@contextmanager
def _selected_alone(obj):
    """Makes obj the only selected and active object, then restores the artist's selection.

    Blender's "remove unused slots" operator acts on the view layer's real selection
    and ignores a context override, so the object has to be selected for real.
    """
    view_layer = bpy.context.view_layer
    was_selected = [o for o in view_layer.objects if o.select_get()]
    was_active = view_layer.objects.active
    for o in was_selected:
        o.select_set(False)
    obj.select_set(True)
    view_layer.objects.active = obj
    try:
        yield
    finally:
        obj.select_set(False)
        for o in was_selected:
            o.select_set(True)
        view_layer.objects.active = was_active


# Modifiers that never add faces with other materials. Any other modifier may, e.g.
# Solidify's rim and shell offsets, Bevel's material, Boolean, Array caps, Geometry
# Nodes, so a slot no face of the mesh uses can still be used in the export.
_MATERIAL_NEUTRAL_MODIFIERS = {
    "ARMATURE", "SUBSURF", "MULTIRES", "TRIANGULATE", "MIRROR", "WEIGHTED_NORMAL", "EDGE_SPLIT",
    "DECIMATE", "SMOOTH", "LAPLACIANSMOOTH", "CORRECTIVE_SMOOTH", "DISPLACE", "SHRINKWRAP", "CAST",
    "SIMPLE_DEFORM", "LATTICE", "CURVE", "HOOK", "WARP", "WAVE", "MESH_DEFORM", "SURFACE_DEFORM",
    "UV_PROJECT", "UV_WARP", "NORMAL_EDIT", "WELD",
}


def _slots_skip_reason(issue) -> str:
    obj = current().scene.objects.get(issue.object_name)
    if obj is None:
        return "not in the scene"
    if obj.name not in bpy.context.view_layer.objects:
        return "not in the view layer"
    if "unused" not in issue.message:
        return "empty slots used by faces need a material assigned by hand"
    others = [m.name for m in obj.modifiers if m.type not in _MATERIAL_NEUTRAL_MODIFIERS]
    if others:
        return f"modifiers may use the slots ({', '.join(others[:3])})"
    return ""


@AgentTools.register_fix(
    "detect_unused_material_slots", display_name="Remove Unused Material Slots", safe=True,
    skip_reason=_slots_skip_reason,
)
def remove_unused_material_slots(issues) -> str:
    """Removes slots no face uses, with Blender's Remove Unused Slots.

    Objects with modifiers that may add faces with other materials (Solidify,
    Bevel, Boolean, Geometry Nodes…) are left: Blender's operator only looks at
    the mesh's own faces, so it would remove slots those modifiers use.
    """
    scene = current().scene
    removed = 0
    for issue in issues:
        obj = scene.objects.get(issue.object_name)
        if not obj:
            continue
        before = len(obj.material_slots)
        with _selected_alone(obj), bpy.context.temp_override(object=obj, active_object=obj):
            if not bpy.ops.object.material_slot_remove_unused.poll():
                continue
            bpy.ops.object.material_slot_remove_unused()
        removed += before - len(obj.material_slots)
    return f"Removed {removed} unused slots"


# ---------- textured materials ----------

@AgentTools.register_check(
    display_name="Detect Textured Materials",
    category="Texture",
    why="When textures are set up in engine, images left on the delivered material "
        "add weight to the export and can override the engine-side material.",
    pass_text="None",
)
def detect_textured_materials() -> list:
    """Finds meshes whose materials use image textures, for deliveries that must have none."""
    issues = []
    for obj in current().meshes:
        textured = {}
        for mat in _materials(obj):
            count = sum(1 for _ in _image_nodes(mat))
            if count:
                textured[mat.name] = count
        if textured:
            total = sum(textured.values())
            issues.append(Issue(obj.name, "Textures on " + ", ".join(sorted(textured)),
                                value=f"{total} image nodes", target="0"))
    return issues


# ---------- materials per mesh ----------

@AgentTools.register_check(
    display_name="Detect Too Many Materials",
    category="Texture",
    why="Each extra material is an extra draw call, and some platforms (Roblox, for "
        "one) allow only one material per mesh.",
    pass_text="Within limit",
)
def detect_too_many_materials(max_materials: int = 1) -> list:
    """Finds meshes whose faces use more materials than allowed.

    max_materials: how many different materials a mesh's faces may use.
    Slots no face uses don't count (Detect Unused Material Slots finds those).
    """
    if max_materials < 1:
        raise ValueError("max_materials must be at least 1")
    issues = []
    for obj in current().meshes:
        used = _used_material_indices(obj)
        names = sorted({obj.material_slots[i].material.name for i in used
                        if i < len(obj.material_slots) and obj.material_slots[i].material})
        if len(names) > max_materials:
            issues.append(Issue(obj.name, f"{len(names)} materials: " + ", ".join(names),
                                value=f"{len(names)} materials", target=f"≤ {max_materials}"))
    return issues


# ---------- unused materials ----------

def _unused_materials() -> list:
    """Local mesh materials nothing uses.

    Materials with a fake user (the shield icon) were kept on purpose, so they count
    as used, as in Blender's Purge. Grease Pencil materials are skipped: they're
    never part of a mesh delivery, and Blender's default file ships one with no users.
    """
    return [m for m in bpy.data.materials
            if m.library is None and not m.is_grease_pencil and m.users == 0]


@AgentTools.register_check(
    display_name="Detect Unused Materials",
    category="Texture",
    why="Materials nothing uses are leftovers that clutter the delivered file and "
        "can end up imported into the engine as extra assets.",
    pass_text="None",
)
def detect_unused_materials() -> list:
    """Finds materials in the file that no object uses. Checks the whole file, not just
    the selection, and ignores Grease Pencil materials and ones with a fake user."""
    names = sorted(m.name for m in _unused_materials())
    if not names:
        return []
    more = "…" if len(names) > 5 else ""
    return [Issue(None, "Unused materials: " + ", ".join(names[:5]) + more,
                  value=f"{len(names)} materials", target="0")]


@AgentTools.register_fix("detect_unused_materials", display_name="Remove Unused Materials", safe=True)
def remove_unused_materials(issues) -> str:
    """Deletes every material in the file that nothing uses, as Purge does.

    These have no users, so Blender would drop them when saving anyway. Materials
    with a fake user are kept.
    """
    unused = _unused_materials()
    for mat in unused:
        bpy.data.materials.remove(mat)
    return f"Removed {len(unused)} unused materials"
