"""Scene checks: objects that shouldn't be delivered."""

import bpy

from ..core.registry import AgentTools
from ..core.results import Issue
from ..core.scope import current

# Unreal imports empties named SOCKET_<name> as sockets, so they're always allowed.
SOCKET_PREFIX = "SOCKET_"


def _object_types() -> set:
    return {item.identifier for item in bpy.types.Object.bl_rna.properties["type"].enum_items}


@AgentTools.register_check(
    display_name="Detect Unwanted Objects",
    category="Scene",
    why="Cameras, lights and stray empties get exported along with the asset and "
        "clutter or break the import in engine.",
    pass_text="None",
)
def detect_unwanted_objects(allowed_types: list = ["MESH", "ARMATURE"]) -> list:  # noqa: B006 - never mutated
    """Finds objects whose type isn't allowed, e.g. cameras, lights and empties.

    allowed_types: Blender object types to allow, e.g. ["MESH", "ARMATURE", "EMPTY"].
    Empties named SOCKET_<name> are always allowed (Unreal sockets).
    """
    allowed = {t.upper() for t in allowed_types}
    unknown = allowed - _object_types()
    if unknown:
        raise ValueError(f"unknown object types: {', '.join(sorted(unknown))}")
    scope = current()
    issues = []
    for obj in list(scope.meshes) + list(scope.collision) + list(scope.others):
        if obj.type in allowed or (obj.type == "EMPTY" and obj.name.upper().startswith(SOCKET_PREFIX)):
            continue
        kind = obj.type.replace("_", " ").lower()
        issues.append(Issue(obj.name, f"Unwanted {kind}", value=kind,
                            target=", ".join(t.lower() for t in sorted(allowed))))
    return issues
