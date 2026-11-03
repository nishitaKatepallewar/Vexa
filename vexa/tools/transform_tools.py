"""Transform checks: applied rotation and scale, negative scale, pivot, unit scale."""

import math

import bpy
from mathutils import Matrix, Vector

from ..core.registry import AgentTools
from ..core.results import Issue
from ..core.scope import current

TOL = 1e-4


def _fmt_vec(v) -> str:
    return "(" + ", ".join(f"{c:.3g}" for c in v) + ")"


def _unapplied(obj, check_rotation: bool) -> list:
    _loc, rot, scale = obj.matrix_basis.decompose()
    problems = []
    if any(abs(s - 1.0) > TOL for s in scale):
        problems.append(f"scale {_fmt_vec(scale)}")
    if check_rotation and rot.angle > TOL:
        degrees = [math.degrees(a) for a in rot.to_euler()]
        problems.append(f"rotation {_fmt_vec(degrees)}°")
    return problems


# ---------- transforms applied ----------

@AgentTools.register_check(
    display_name="Detect Unapplied Transforms",
    category="Transforms",
    why="Unapplied scale or rotation is the most common reason assets import at the "
        "wrong size or rotated 90° in Unity and Unreal.",
    severity="ERROR",
    pass_text="Scale 1, rotation 0",
)
def detect_unapplied_transforms(check_rotation: bool = True) -> list:
    """Finds meshes whose scale isn't 1, or whose rotation isn't 0.

    check_rotation: also require rotation to be applied, not just scale.
    """
    issues = []
    for obj in current().all_meshes:
        problems = _unapplied(obj, check_rotation)
        if problems:
            issues.append(Issue(obj.name, "Unapplied " + " and ".join(p.split()[0] for p in problems),
                                value="; ".join(problems), target="applied"))
    return issues


@AgentTools.register_fix("detect_unapplied_transforms", display_name="Apply Transforms")
def apply_transforms(issues, check_rotation: bool = True) -> str:
    """Applies scale (and rotation) on meshes with unapplied transforms.

    Skips mirrored meshes and meshes that share data with other objects.
    """
    scene = current().scene
    targets, skipped = [], []
    for issue in issues:
        obj = scene.objects.get(issue.object_name)
        if not obj:
            continue
        if any(s < 0 for s in obj.scale):
            skipped.append(f"{obj.name} (negative scale)")
        elif obj.data.users > 1:
            skipped.append(f"{obj.name} (shared mesh data)")
        else:
            targets.append(obj)
    if targets:
        with bpy.context.temp_override(
            selected_editable_objects=targets, selected_objects=targets,
            active_object=targets[0], object=targets[0],
        ):
            if not bpy.ops.object.transform_apply.poll():
                return "Couldn't apply transforms here. Switch to Object Mode and try again."
            bpy.ops.object.transform_apply(location=False, rotation=check_rotation, scale=True)
    msg = f"Applied transforms on {len(targets)} objects"
    if skipped:
        msg += ". Skipped: " + ", ".join(skipped)
    return msg


# ---------- negative scale ----------

@AgentTools.register_check(
    display_name="Detect Negative Scale",
    category="Transforms",
    why="Mirroring with negative scale flips normals in engine, so faces turn invisible "
        "or inside-out and normal maps light the wrong way.",
    severity="ERROR",
    pass_text="None",
)
def detect_negative_scale() -> list:
    """Finds meshes mirrored with a negative scale.

    To fix by hand: apply scale, then Mesh > Normals > Recalculate Outside.
    """
    return [Issue(obj.name, "Negative scale", value=f"scale {_fmt_vec(obj.scale)}", target="all positive")
            for obj in current().all_meshes if any(s < 0 for s in obj.scale)]


# ---------- pivot ----------

def _local_bounds(obj):
    verts = obj.data.vertices
    if not len(verts):
        return None
    xs = [v.co.x for v in verts]
    ys = [v.co.y for v in verts]
    zs = [v.co.z for v in verts]
    return Vector((min(xs), min(ys), min(zs))), Vector((max(xs), max(ys), max(zs)))


def _bottom_center(obj):
    lo, hi = _local_bounds(obj)
    return Vector(((lo.x + hi.x) / 2, (lo.y + hi.y) / 2, lo.z))


@AgentTools.register_check(
    display_name="Detect Off-Center Pivots",
    category="Transforms",
    why="Marketplaces expect props to sit on the ground when dropped into a scene. "
        "A pivot off the bottom centre makes every placement need manual nudging.",
    pass_text="Bottom centre",
)
def detect_off_center_pivots(tolerance_m: float = 0.01) -> list:
    """Finds meshes whose origin isn't at the bottom centre of their bounds.

    tolerance_m: how far (in metres) the origin may be from the bottom centre.
    """
    issues = []
    for obj in current().meshes:
        if not _local_bounds(obj):
            continue
        offset = obj.matrix_world.to_3x3() @ _bottom_center(obj)
        if offset.length > tolerance_m:
            issues.append(Issue(obj.name, "Pivot is not at bottom centre",
                                value=f"off by {offset.length:.3f} m", target=f"≤ {tolerance_m:g} m"))
    return issues


@AgentTools.register_fix("detect_off_center_pivots", display_name="Move Pivots to Bottom Centre")
def move_pivots_to_bottom_center(issues) -> str:
    """Moves each flagged mesh's origin to the bottom centre without moving the mesh.

    Skips meshes with children or shared mesh data.
    """
    scene = current().scene
    moved, skipped = 0, []
    for issue in issues:
        obj = scene.objects.get(issue.object_name)
        if not obj:
            continue
        if obj.children or obj.data.users > 1:
            skipped.append(obj.name)
            continue
        target = _bottom_center(obj)
        obj.data.transform(Matrix.Translation(-target))
        obj.matrix_world = obj.matrix_world @ Matrix.Translation(target)
        obj.data.update()
        moved += 1
    msg = f"Moved pivot on {moved} objects"
    if skipped:
        msg += ". Skipped (has children or shared mesh): " + ", ".join(skipped)
    return msg


# ---------- unit scale ----------

@AgentTools.register_check(
    display_name="Detect Wrong Unit Scale",
    category="Transforms",
    why="If the scene's unit scale doesn't match what the engine expects, everything "
        "exported from this file imports at the wrong size.",
    pass_text="Matches",
)
def detect_wrong_unit_scale(scale_length: float = 1.0) -> list:
    """Checks the scene's unit scale against what the target engine expects.

    scale_length: the expected Unit Scale (1.0 means 1 Blender unit = 1 metre).
    """
    units = current().scene.unit_settings
    if abs(units.scale_length - scale_length) > 1e-6:
        return [Issue(None, "Scene unit scale doesn't match the target engine",
                      value=f"{units.scale_length:g}", target=f"{scale_length:g}")]
    return []


@AgentTools.register_fix("detect_wrong_unit_scale", display_name="Set Unit Scale")
def set_unit_scale(issues, scale_length: float = 1.0) -> str:
    """Sets the scene's unit scale to the expected value."""
    current().scene.unit_settings.scale_length = scale_length
    return f"Set scene unit scale to {scale_length:g}"
