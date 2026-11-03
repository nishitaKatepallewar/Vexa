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
