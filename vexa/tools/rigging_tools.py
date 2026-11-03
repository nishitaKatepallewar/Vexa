"""Rigging checks: bone influences per vertex."""

from ..core.registry import AgentTools
from ..core.results import Issue
from ..core.scope import current


@AgentTools.register_check(
    display_name="Detect Excess Bone Influences",
    category="Rigging",
    why="Engines cap how many bones can move one vertex (Unity 4 by default, Unreal 8). "
        "Extra weights are dropped on import and deformation changes.",
    pass_text="Within limit",
)
def detect_excess_bone_influences(max_influences: int = 4) -> list:
    """Finds vertices weighted to more deforming bones than the engine supports.

    max_influences: the most bones allowed to influence one vertex.
    """
    issues = []
    for obj in current().meshes:
        armatures = [m.object for m in obj.modifiers if m.type == "ARMATURE" and m.object]
        if not armatures or not obj.vertex_groups:
            continue
        bone_names = {b.name for arm in armatures for b in arm.data.bones if b.use_deform}
        bone_groups = {vg.index for vg in obj.vertex_groups if vg.name in bone_names}
        bad = [v.index for v in obj.data.vertices
               if sum(1 for g in v.groups if g.group in bone_groups and g.weight > 1e-4) > max_influences]
        if bad:
            issues.append(Issue(obj.name, f"{len(bad)} vertices over {max_influences} influences",
                                value=f"{len(bad)} verts", target=f"≤ {max_influences}",
                                element="VERT", indices=bad))
    return issues
