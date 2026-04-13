"""Texture-related QC tools for Vexa."""

import bpy

from vexa.core.registry import AgentTools


def _get_selected_meshes():
    """Yields mesh objects from current selection."""
    for obj in bpy.context.selected_objects:
        if obj.type == "MESH":
            yield obj


@AgentTools.register(
    display_name="Detect Missing Textures",
    is_quick_action=True,
    category="Texture",
)
def detect_missing_textures() -> str:
    """Detects missing texture references in selected objects' materials.

    Scans shader nodes for Image Textures with no image assigned.
    """
    meshes = list(_get_selected_meshes())
    if not meshes:
        return "No mesh objects selected."

    objects_with_missing = []
    total_missing = 0

    for obj in meshes:
        if not obj.data.materials:
            continue

        obj_missing = []

        for mat in obj.data.materials:
            if not mat.use_nodes:
                continue

            tree = mat.node_tree
            for node in tree.nodes:
                if node.type == "TEX_IMAGE":
                    if node.image is None:
                        node_name = node.name if node.name else "Unnamed Image"
                        obj_missing.append(f"{mat.name}: {node_name}")
                        total_missing += 1

        if obj_missing:
            objects_with_missing.append(f"{obj.name} ({len(obj_missing)})")

    if total_missing == 0:
        return "No missing textures found. All texture references are valid."

    return f"Found {total_missing} missing textures in {len(objects_with_missing)} objects: {', '.join(objects_with_missing)}"


@AgentTools.register(
    display_name="Detect Color Space Issues",
    is_quick_action=True,
    category="Texture",
)
def detect_color_space_issues() -> str:
    """Detects incorrect color space settings on textures.

    Checks for common issues:
    - Normal/Roughness/Metallic maps in sRGB (should be Non-Color)
    - Albedo/Diffuse in Non-Color (should be sRGB)
    """
    meshes = list(_get_selected_meshes())
    if not meshes:
        return "No mesh objects selected."

    issues = []

    for obj in meshes:
        if not obj.data.materials:
            continue

        for mat in obj.data.materials:
            if not mat.use_nodes:
                continue

            tree = mat.node_tree

            for node in tree.nodes:
                if node.type == "TEX_IMAGE" and node.image:
                    image = node.image
                    color_space = image.colorspace_settings.name
                    node_name = node.name if node.name else "Unnamed"

                    is_normal = _is_likely_normal_map(node, tree)
                    is_roughness = _is_likely_roughness_map(node, tree)
                    is_metallic = _is_likely_metallic_map(node, tree)
                    is_albedo = _is_likely_albedo_map(node, tree)

                    if is_normal and color_space == "sRGB":
                        issues.append(
                            f"{mat.name}: {node_name} (Normal in sRGB - should be Non-Color)"
                        )
                    elif is_roughness and color_space == "sRGB":
                        issues.append(
                            f"{mat.name}: {node_name} (Roughness in sRGB - should be Non-Color)"
                        )
                    elif is_metallic and color_space == "sRGB":
                        issues.append(
                            f"{mat.name}: {node_name} (Metallic in sRGB - should be Non-Color)"
                        )
                    elif is_albedo and color_space == "Non-Color":
                        issues.append(
                            f"{mat.name}: {node_name} (Albedo in Non-Color - should be sRGB)"
                        )

    if not issues:
        return "No color space issues found. All textures use correct color spaces."

    return f"Found {len(issues)} color space issues:\n" + "\n".join(
        f"  - {issue}" for issue in issues
    )


def _is_likely_normal_map(node, tree) -> bool:
    """Heuristic: check if node is likely a normal map based on connections."""
    for input_socket in node.inputs:
        if input_socket.is_linked:
            for link in input_socket.links:
                from_node = link.from_node
                if from_node.type == "NORMAL_MAP" or from_node.type == "BUMP":
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
