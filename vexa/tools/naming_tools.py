"""Naming checks: default names, allowed characters, required prefix."""

import re

import bpy

from ..core.registry import AgentTools
from ..core.results import Issue
from ..core.scope import COLLISION_PREFIXES, current

DEFAULT_NAME = re.compile(
    r"^(Cube|Sphere|Icosphere|Cylinder|Plane|Cone|Torus|Circle|Grid|Monkey|Suzanne|Mesh|Object)(\.\d+)?$"
)


# ---------- default names ----------

@AgentTools.register_check(
    display_name="Default object names",
    category="Naming",
    why="Names like Cube.003 become asset names in engine. Reviewers and teammates "
        "can't tell what anything is.",
    pass_text="None",
)
def detect_default_names() -> list:
    """Finds meshes still using Blender's default names (Cube.001, Plane, …)."""
    return [Issue(o.name, "Default name", value=o.name, target="descriptive name")
            for o in current().meshes if DEFAULT_NAME.match(o.name)]


# ---------- allowed characters ----------

@AgentTools.register_check(
    display_name="Allowed name characters",
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


@AgentTools.register_fix("detect_invalid_name_characters", display_name="Fix Invalid Names")
def fix_invalid_names(issues) -> str:
    """Replaces invalid characters in flagged object and material names with underscores."""
    scene = current().scene
    renamed = 0
    for issue in issues:
        if issue.message.startswith("Material"):
            mat = bpy.data.materials.get(issue.value)
            if mat:
                mat.name = _sanitize(mat.name, bpy.data.materials)
                renamed += 1
        else:
            obj = scene.objects.get(issue.value)
            if obj:
                obj.name = _sanitize(obj.name, bpy.data.objects)
                renamed += 1
    return f"Renamed {renamed} items"


# ---------- required prefix ----------

@AgentTools.register_check(
    display_name="Asset name prefix",
    category="Naming",
    why="Studios and Unreal's style guide use prefixes like SM_ for static meshes so "
        "assets sort and filter correctly in the content browser.",
    pass_text="All prefixed",
)
def detect_missing_name_prefix(prefix: str = "SM_") -> list:
    """Finds render meshes missing a required name prefix. Collision meshes are ignored.

    prefix: the prefix every render mesh name must start with.
    """
    return [Issue(o.name, f"Missing {prefix} prefix", value=o.name, target=f"{prefix}…")
            for o in current().meshes if not o.name.startswith(prefix)]


@AgentTools.register_fix("detect_missing_name_prefix", display_name="Add Name Prefix")
def add_name_prefix(issues, prefix: str = "SM_") -> str:
    """Adds the prefix to flagged meshes and renames their collision meshes to match."""
    scope = current()
    renamed = 0
    for issue in issues:
        obj = scope.scene.objects.get(issue.object_name)
        if obj and not obj.name.startswith(prefix):
            old = obj.name
            obj.name = prefix + old
            for col in scope.collision:
                for p in COLLISION_PREFIXES:
                    if col.name.startswith(p + old):
                        col.name = p + prefix + col.name[len(p):]
            renamed += 1
    return f"Added {prefix} to {renamed} objects"
