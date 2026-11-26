"""Transform checks: applied transforms, negative scale, pivot, scene units."""

import math

import bpy
from mathutils import Matrix, Vector

from ..core.registry import AgentTools
from ..core.results import Issue
from ..core.scope import current

TOL = 1e-4


def _fmt_vec(v) -> str:
    return "(" + ", ".join(f"{c:.3g}" for c in v) + ")"


def _unapplied(obj, check_rotation: bool, check_location: bool) -> list:
    """What's wrong with an object's transform, as (label, detail) pairs."""
    loc, rot, scale = obj.matrix_basis.decompose()
    problems = []
    if any(abs(s - 1.0) > TOL for s in scale):
        problems.append(("scale", f"scale {_fmt_vec(scale)}"))
    if check_rotation and rot.angle > TOL:
        degrees = [math.degrees(a) for a in rot.to_euler()]
        problems.append(("rotation", f"rotation {_fmt_vec(degrees)}°"))
    if check_location and loc.length > TOL:
        problems.append(("location", f"location {_fmt_vec(loc)}"))
    return problems


def _describe_unapplied(labels: list) -> str:
    """"Unapplied scale and rotation", "Not at world origin", or both."""
    parts = []
    applied = [label for label in labels if label != "location"]
    if applied:
        parts.append("Unapplied " + " and ".join(applied))
    if "location" in labels:
        parts.append("not at world origin" if parts else "Not at world origin")
    return "; ".join(parts)


# ---------- transforms applied ----------

@AgentTools.register_check(
    display_name="Detect Unapplied Transforms",
    category="Transforms",
    why="Unapplied scale or rotation is the most common reason assets import at the "
        "wrong size or rotated 90° in Unity and Unreal.",
    severity="ERROR",
    pass_text="Scale 1, rotation 0",
)
def detect_unapplied_transforms(check_rotation: bool = True, check_location: bool = False) -> list:
    """Finds meshes whose scale isn't 1, or whose rotation isn't 0.

    check_rotation: also require rotation to be applied, not just scale.
    check_location: also require the mesh to sit at the world origin (location 0, 0, 0).
    """
    issues = []
    for obj in current().all_meshes:
        problems = _unapplied(obj, check_rotation, check_location)
        if problems:
            issues.append(Issue(obj.name, _describe_unapplied([label for label, _ in problems]),
                                value="; ".join(detail for _, detail in problems), target="applied"))
    return issues


@AgentTools.register_fix(
    "detect_unapplied_transforms", display_name="Apply Transforms",
    confirm=(
        "Applies scale and rotation so they become 1 and 0 without moving the mesh. Modifiers "
        "such as Bevel or Solidify can look different afterwards. With 'at the world origin' "
        "on, each object also moves to the origin, so the parts of an assembly end up on top "
        "of each other."
    ),
)
def apply_transforms(issues, check_rotation: bool = True, check_location: bool = False) -> str:
    """Applies scale (and rotation) on meshes with unapplied transforms.

    With check_location, also moves each mesh to the world origin. The mesh moves
    with its pivot, so the pivot stays where it is on the mesh.
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
        if check_location:
            for obj in targets:
                obj.location = (0.0, 0.0, 0.0)
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


@AgentTools.register_fix(
    "detect_off_center_pivots", display_name="Move Pivots to Bottom Centre",
    confirm=(
        "Moves each flagged mesh's origin to the bottom centre of its bounds. Right for props "
        "that stand on the floor. Wrong for doors and lids that turn on a hinge, and for "
        "modular pieces that snap at a corner."
    ),
)
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


# ---------- units ----------

METRIC_UNITS = ("ADAPTIVE", "KILOMETERS", "METERS", "CENTIMETERS", "MILLIMETERS", "MICROMETERS")
IMPERIAL_UNITS = ("ADAPTIVE", "MILES", "FEET", "INCHES", "THOU")
ROTATION_UNITS = ("DEGREES", "RADIANS")


UNIT_SCALE_MESSAGE = "Scene unit scale doesn't match the target engine"


def _validate_units(length_unit: str, rotation_unit: str) -> None:
    if length_unit and length_unit not in METRIC_UNITS + IMPERIAL_UNITS:
        raise ValueError(f"length_unit must be one of {', '.join(dict.fromkeys(METRIC_UNITS + IMPERIAL_UNITS))}")
    if rotation_unit and rotation_unit not in ROTATION_UNITS:
        raise ValueError(f"rotation_unit must be {' or '.join(ROTATION_UNITS)}")


@AgentTools.register_check(
    display_name="Detect Wrong Units",
    category="Transforms",
    why="If the scene's units don't match what the engine or studio expects, everything "
        "exported from this file imports at the wrong size, and typed values mean something else.",
    pass_text="Matches",
)
def detect_wrong_unit_scale(scale_length: float = 1.0, length_unit: str = "", rotation_unit: str = "") -> list:
    """Checks the scene's unit scale, and optionally its length and rotation units.

    scale_length: the expected Unit Scale (1.0 means 1 Blender unit = 1 metre).
    length_unit: the expected length unit, e.g. "METERS" or "CENTIMETERS". Empty: not checked.
    rotation_unit: the expected rotation unit, "DEGREES" or "RADIANS". Empty: not checked.
    """
    _validate_units(length_unit, rotation_unit)
    units = current().scene.unit_settings
    issues = []
    if abs(units.scale_length - scale_length) > 1e-6:
        issues.append(Issue(None, UNIT_SCALE_MESSAGE,
                            value=f"{units.scale_length:g}", target=f"{scale_length:g}"))
    if length_unit and units.length_unit != length_unit:
        issues.append(Issue(None, "Scene length unit doesn't match",
                            value=units.length_unit.lower(), target=length_unit.lower()))
    if rotation_unit and units.system_rotation != rotation_unit:
        issues.append(Issue(None, "Scene rotation unit doesn't match",
                            value=units.system_rotation.lower(), target=rotation_unit.lower()))
    return issues


def _transform_animated(obj) -> bool:
    action = obj.animation_data.action if obj.animation_data else None
    if action is None:
        return False
    fcurves = getattr(action, "fcurves", None)
    if fcurves is None:  # Blender 5 layered actions: read the channels the object uses
        try:
            fcurves = [fc for layer in action.layers for strip in layer.strips
                       for bag in strip.channelbags for fc in bag.fcurves]
        except AttributeError:
            return True  # can't tell: assume it is
    return any(fc.data_path in {"location", "rotation_euler", "rotation_quaternion", "scale"} for fc in fcurves)


def _unit_skip_reason(issue) -> str:
    if issue.message != UNIT_SCALE_MESSAGE:
        return ""
    animated = [o.name for o in current().scene.objects if o.parent is None and _transform_animated(o)]
    if animated:
        return f"{animated[0]} has animated transforms, so the scene can't be rescaled to match"
    return ""


@AgentTools.register_fix(
    "detect_wrong_unit_scale", display_name="Set Units",
    confirm=(
        "Changes the scene's units. If the unit scale changes, every object in the scene is "
        "scaled about the world origin to match, so FBX exports keep their real size (a 2 m "
        "crate stays 2 m). Objects get a scale such as 100 that Apply Transforms can apply "
        "afterwards. glTF ignores the unit scale: if you export glTF, don't use this."
    ),
    skip_reason=_unit_skip_reason,
)
def set_unit_scale(issues, scale_length: float = 1.0, length_unit: str = "", rotation_unit: str = "") -> str:
    """Sets the scene's unit scale, and the length and rotation units if given.

    When the unit scale changes, every top-level object is scaled about the world
    origin by old / new scale, so real-world (and FBX export) sizes stay the same.
    Children follow their parents. Object scale is changed, not mesh data, so
    modifiers such as Bevel keep their look.
    """
    _validate_units(length_unit, rotation_unit)
    scene = current().scene
    units = scene.unit_settings
    done = []
    if any(i.message == UNIT_SCALE_MESSAGE for i in issues):
        factor = units.scale_length / scale_length
        roots = [o for o in scene.objects if o.parent is None]
        if abs(factor - 1.0) > 1e-9:
            grow = Matrix.Scale(factor, 4)
            for obj in roots:
                obj.matrix_world = grow @ obj.matrix_world
        units.scale_length = scale_length
        done.append(f"scale {scale_length:g}" + (f" (scaled {len(roots)} objects by {factor:g})" if roots else ""))
    if length_unit and units.length_unit != length_unit:
        if length_unit != "ADAPTIVE":
            units.system = "METRIC" if length_unit in METRIC_UNITS else "IMPERIAL"
        units.length_unit = length_unit
        done.append(length_unit.lower())
    if rotation_unit and units.system_rotation != rotation_unit:
        units.system_rotation = rotation_unit
        done.append(rotation_unit.lower())
    return "Set scene units: " + ", ".join(done) if done else "Nothing to change"
