"""Naming checks: default names, allowed characters, required prefix."""

import re

import bpy

from ..core.registry import AgentTools
from ..core.results import Issue
from ..core.scope import collision_base, current, is_collision_name, is_skeletal

# Names nobody chose: Blender's primitives, Maya's (pCube1, polySurface12), 3ds Max's
# (Box001) and what importers make up (geometry_0, Object_12).
DEFAULT_NAME = re.compile(
    r"^(Cube|Sphere|Icosphere|Cylinder|Plane|Cone|Torus|Circle|Grid|Monkey|Suzanne|Mesh|Object)(\.\d+)?$"
    r"|^(p(Cube|Sphere|Cylinder|Cone|Plane|Torus|Pipe|Prism|Pyramid|Helix|Disc|Platonic|SolidBox)"
    r"|polySurface|polyMesh)\d+$"
    r"|^(Box|Sphere|GeoSphere|Cylinder|Cone|Plane|Torus|Teapot|Tube|Pyramid|ChamferBox)\d{3}$"
    r"|^(geometry|mesh|Mesh|object|Object|node|Node)_?\d+(\.\d+)?$"
)
# Materials nobody named: Blender's, Maya's and 3ds Max's defaults.
DEFAULT_MATERIAL_NAME = re.compile(
    r"^(Material(\.\d+)?|(lambert|blinn|phong|phongE|standardSurface|aiStandardSurface)\d+"
    r"|Material #\d+|\d+ - Default|DefaultMaterial|default)$"
)


# ---------- default names ----------

@AgentTools.register_check(
    display_name="Detect Default Names",
    category="Naming",
    why="Names like Cube.003 or Material.001 become asset and material names in engine. "
        "Reviewers and teammates can't tell what anything is.",
    pass_text="None",
)
def detect_default_names() -> list:
    """Finds meshes and materials still using default names: Cube.001, pCube1, Box001,
    geometry_0, Material.001, lambert1…"""
    issues, seen = [], set()
    for obj in current().meshes:
        if DEFAULT_NAME.match(obj.name):
            issues.append(Issue(obj.name, "Default name", value=obj.name, target="descriptive name"))
        for slot in obj.material_slots:
            mat = slot.material
            if mat and mat.name not in seen and DEFAULT_MATERIAL_NAME.match(mat.name):
                seen.add(mat.name)
                issues.append(Issue(obj.name, f"Material '{mat.name}' has a default name", value=mat.name,
                                    target="descriptive name"))
    return issues


# ---------- allowed characters ----------

@AgentTools.register_check(
    display_name="Detect Invalid Name Characters",
    category="Naming",
    why="Some marketplaces and pipelines only accept letters, digits and underscores. "
        "Spaces, dots and accents break paths and get submissions rejected.",
    pass_text="All valid",
)
def detect_invalid_name_characters(pattern: str = "^[A-Za-z0-9_]+$") -> list:
    """Finds object and material names with characters the target doesn't allow.

    pattern: regular expression every name must match.
    """
    regex = re.compile(pattern)
    issues, seen_materials = [], set()
    for obj in current().all_meshes:
        if not regex.match(obj.name):
            issues.append(Issue(obj.name, "Object name has invalid characters",
                                value=obj.name, target="A–Z, 0–9, _"))
        for slot in obj.material_slots:
            mat = slot.material
            if mat and mat.name not in seen_materials and not regex.match(mat.name):
                seen_materials.add(mat.name)
                issues.append(Issue(obj.name, f"Material '{mat.name}' has invalid characters",
                                    value=mat.name, target="A–Z, 0–9, _"))
    return issues


def _sanitize(name: str, taken) -> str:
    """A valid name that isn't already used. Blender would otherwise append '.001',
    which reintroduces a dot (see the API docs, "Naming Limitations")."""
    clean = re.sub(r"[^A-Za-z0-9_]", "_", name)
    clean = re.sub(r"_+", "_", clean).strip("_") or "Unnamed"
    candidate, n = clean, 1
    while candidate in taken and candidate != name:
        candidate = f"{clean}_{n}"
        n += 1
    return candidate


def _collision_name(prefix: str, base: str, index: int, taken, keep: str = "") -> str:
    """UCX_<base>_NN with the first free NN from index, so it keeps matching its mesh."""
    n = max(index, 1)
    while f"{prefix}{base}_{n:02d}" in taken and f"{prefix}{base}_{n:02d}" != keep:
        n += 1
    return f"{prefix}{base}_{n:02d}"


def _collision_index(name: str) -> int:
    match = re.search(r"_(\d+)(\.\d+)?$", name)
    return int(match.group(1)) if match else 1


def _names_skip_reason(issue) -> str:
    """A collision mesh can't be renamed on its own if its mesh needs renaming too."""
    if issue.message.startswith("Material"):
        return ""
    scope = current()
    obj = scope.scene.objects.get(issue.value)
    if obj is None or not is_collision_name(obj.name):
        return ""
    mesh = scope.scene.objects.get(collision_base(obj.name))
    if mesh and mesh not in scope.meshes and _sanitize(mesh.name, ()) != mesh.name:
        return f"its mesh {mesh.name} isn't being checked: check them together"
    return ""


@AgentTools.register_fix(
    "detect_invalid_name_characters", display_name="Fix Invalid Names", safe=True,
    skip_reason=_names_skip_reason,
)
def fix_invalid_names(issues) -> str:
    """Replaces invalid characters in flagged object and material names with underscores.

    Collision meshes are renamed with their mesh (UCX_<new name>_NN), even if they
    aren't part of the check, so the link between them never breaks.
    """
    scene = current().scene
    renamed, mesh_names = 0, {}
    flagged = {i.value for i in issues if not i.message.startswith("Material")}
    for issue in issues:
        if issue.message.startswith("Material"):
            mat = bpy.data.materials.get(issue.value)
            if mat:
                mat.name = _sanitize(mat.name, bpy.data.materials)
                renamed += 1
            continue
        obj = scene.objects.get(issue.value)
        if obj and not is_collision_name(obj.name):
            old = obj.name
            obj.name = _sanitize(old, bpy.data.objects)
            mesh_names[old] = obj.name
            renamed += 1
    for col in [o for o in scene.objects if o.type == "MESH" and is_collision_name(o.name)]:
        old, base = col.name, collision_base(col.name)
        if base not in mesh_names and old not in flagged:
            continue
        new_base = mesh_names.get(base, base)
        if new_base in bpy.data.objects:  # keep it matching its mesh
            col.name = _collision_name(old[:4], new_base, _collision_index(old), bpy.data.objects, keep=old)
        else:
            col.name = _sanitize(old, bpy.data.objects)
        renamed += col.name != old
    return f"Renamed {renamed} items"


# ---------- required prefix ----------

@AgentTools.register_check(
    display_name="Detect Missing Name Prefix",
    category="Naming",
    why="Studios and Unreal's style guide use prefixes like SM_ for static meshes and SK_ "
        "for skeletal meshes, so assets sort and filter correctly in the content browser.",
    pass_text="All prefixed",
)
def detect_missing_name_prefix(prefix: str = "SM_", skeletal_prefix: str = "SK_") -> list:
    """Finds render meshes missing a required name prefix. Collision meshes are ignored.

    prefix: the prefix every static mesh name must start with.
    skeletal_prefix: the prefix for skinned (skeletal) meshes. Empty: not checked.
    """
    issues = []
    for obj in current().meshes:
        want = skeletal_prefix if is_skeletal(obj) else prefix
        if want and not obj.name.startswith(want):
            kind = "skeletal mesh" if is_skeletal(obj) else "mesh"
            issues.append(Issue(obj.name, f"Missing {want} prefix ({kind})", value=obj.name, target=f"{want}…"))
    return issues


@AgentTools.register_fix("detect_missing_name_prefix", display_name="Add Name Prefix", safe=True)
def add_name_prefix(issues, prefix: str = "SM_", skeletal_prefix: str = "SK_") -> str:
    """Adds the prefix to flagged meshes (SK_ for skeletal ones) and renames their
    collision meshes to match, wherever they are in the scene."""
    scene = current().scene
    renamed = 0
    for issue in issues:
        obj = scene.objects.get(issue.object_name)
        want = (skeletal_prefix if obj and is_skeletal(obj) else prefix) if obj else ""
        if not want or obj.name.startswith(want):
            continue
        old = obj.name
        obj.name = want + old
        for col in [o for o in scene.objects if is_collision_name(o.name) and collision_base(o.name) == old]:
            col.name = col.name[:4] + want + col.name[4:]
        renamed += 1
    return f"Added a prefix to {renamed} objects"
