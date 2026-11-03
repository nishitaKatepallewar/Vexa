"""Material and texture checks: missing textures, colour space, texture size, material slots."""

import os

import bpy

from ..core.registry import AgentTools
from ..core.results import Issue
from ..core.scope import current


def _materials(obj):
    for slot in obj.material_slots:
        if slot.material is not None:
            yield slot.material


def _image_nodes(mat):
    tree = getattr(mat, "node_tree", None)
    if not tree:
        return
    for node in tree.nodes:
        if node.type == "TEX_IMAGE":
            yield node


def _image_missing(image) -> bool:
    if image is None:
        return True
    if image.packed_file or image.source not in {"FILE", "SEQUENCE", "TILED"}:
        return False
    # Pass the library so paths inside linked .blend files resolve correctly
    # (see the API docs, "File Paths & String Encoding").
    path = bpy.path.abspath(image.filepath, library=image.library)
    return not (path and os.path.exists(path))


# ---------- missing textures ----------

@AgentTools.register_check(
    display_name="Detect Missing Textures",
    category="Texture",
    why="Image nodes with no image, or pointing at a file that no longer exists, "
        "export as blank or pink materials.",
    severity="ERROR",
    pass_text="All found",
    is_quick_action=True,
)
def detect_missing_textures() -> list:
    """Finds Image Texture nodes with no image assigned, or whose file is missing."""
    issues = []
    for obj in current().meshes:
        missing = []
        for mat in _materials(obj):
            for node in _image_nodes(mat):
                if _image_missing(node.image):
                    label = node.image.name if node.image else "no image"
                    missing.append(f"{mat.name}: {label}")
        if missing:
            more = "…" if len(missing) > 3 else ""
            issues.append(Issue(obj.name, "Missing: " + ", ".join(missing[:3]) + more,
                                value=f"{len(missing)} missing"))
    return issues


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
    """Finds data maps (normal, roughness, metallic) set to sRGB, and colour maps set to Non-Color."""
    issues, seen = [], set()
    for obj in current().meshes:
        for mat in _materials(obj):
            for node in _image_nodes(mat):
                image = node.image
                if image is None or image.name in seen:
                    continue
                role, expected = _expected_color_space(node, mat.node_tree)
                actual = image.colorspace_settings.name
                if expected and actual != expected:
                    seen.add(image.name)
                    issues.append(Issue(obj.name, f"{image.name}: {role} map in {actual}",
                                        value=image.name, target=expected))
    return issues


@AgentTools.register_fix("detect_color_space_issues", display_name="Fix Color Spaces")
def fix_color_spaces(issues) -> str:
    """Sets each flagged image to the colour space its role needs."""
    fixed = 0
    for issue in issues:
        image = bpy.data.images.get(issue.value)
        if image:
            image.colorspace_settings.name = issue.target
            fixed += 1
    return f"Fixed colour space on {fixed} images"


# ---------- texture size ----------

@AgentTools.register_check(
    display_name="Texture sizes",
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


# ---------- material slots ----------

@AgentTools.register_check(
    display_name="Empty material slots",
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
        used = {p.material_index for p in obj.data.polygons}
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


@AgentTools.register_fix("detect_unused_material_slots", display_name="Remove Unused Material Slots")
def remove_unused_material_slots(issues) -> str:
    """Removes slots no face uses. Empty slots that faces use need a material assigned by hand."""
    scene = current().scene
    removed = 0
    for issue in issues:
        obj = scene.objects.get(issue.object_name)
        if not obj:
            continue
        before = len(obj.material_slots)
        with bpy.context.temp_override(object=obj, active_object=obj,
                                       selected_objects=[obj], selected_editable_objects=[obj]):
            if not bpy.ops.object.material_slot_remove_unused.poll():
                continue
            bpy.ops.object.material_slot_remove_unused()
        removed += before - len(obj.material_slots)
    return f"Removed {removed} unused slots"
