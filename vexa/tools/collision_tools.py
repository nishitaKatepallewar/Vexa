"""Collision checks for Unreal custom collision meshes (UCX_, UBX_, UCP_, USP_)."""

import re

from ..core.registry import AgentTools
from ..core.results import Issue
from ..core.scope import COLLISION_PREFIXES, current


def _collision_base(name: str):
    """UCX_SM_Crate_01 -> SM_Crate. The trailing _NN index is optional."""
    for p in COLLISION_PREFIXES:
        if name.upper().startswith(p):
            rest = name[len(p):].split(".")[0]
            return re.sub(r"_\d+$", "", rest)
    return None


def _is_convex(obj, tol: float = 1e-4) -> bool:
    verts = [v.co for v in obj.data.vertices]
    for poly in obj.data.polygons:
        normal = poly.normal
        if normal.length < 1e-8:
            continue
        center = poly.center
        for v in verts:
            if (v - center).dot(normal) > tol * max(1.0, (v - center).length):
                return False
    return True


@AgentTools.register_check(
    display_name="Collision meshes",
    category="Collision",
    why="Unreal only imports custom collision named UCX_<MeshName>_NN, and it must be "
        "convex. Anything else is silently ignored or replaced.",
    severity="ERROR",
    pass_text="Valid",
)
def detect_invalid_collision_meshes() -> list:
    """Finds UCX_ collision meshes that don't match a render mesh name, or aren't convex."""
    scope = current()
    render_names = {o.name for o in scope.meshes}
    issues = []
    for col in scope.collision:
        base = _collision_base(col.name)
        if base not in render_names and col.name.split(".")[0][4:] not in render_names:
            issues.append(Issue(col.name, "Collision name doesn't match any mesh",
                                value=col.name, target="UCX_<MeshName>_01"))
        if col.name.upper().startswith("UCX_") and not _is_convex(col):
            issues.append(Issue(col.name, "Collision mesh isn't convex", value="concave", target="convex"))
    return issues
