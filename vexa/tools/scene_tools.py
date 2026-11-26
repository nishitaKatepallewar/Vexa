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


NOT_FOR_EXPORT = "Not for export"


def _layer_collection(layer_collection, collection):
    if layer_collection.collection == collection:
        return layer_collection
    for child in layer_collection.children:
        found = _layer_collection(child, collection)
        if found:
            return found
    return None


def _unwanted_skip_reason(issue) -> str:
    obj = current().scene.objects.get(issue.object_name)
    if obj is None:
        return "not in the scene"
    if obj.library:
        return "linked from another file"
    if obj.children:
        return "has children, which would lose their parent in the export"
    return ""


@AgentTools.register_fix(
    "detect_unwanted_objects", display_name="Move Out of the Export", safe=True,
    skip_reason=_unwanted_skip_reason,
)
def move_unwanted_objects(issues) -> str:
    """Moves unwanted objects into a "Not for export" collection that is switched off.

    Nothing is deleted. FBX and glTF exports skip switched-off collections, and so
    do Vexa's checks. Tick the collection in the Outliner to bring them back.
    Objects with children stay where they are.
    """
    scope = current()
    scene, view_layer = scope.scene, bpy.context.view_layer
    target = bpy.data.collections.get(NOT_FOR_EXPORT)
    if target is None or target.library:
        target = bpy.data.collections.new(NOT_FOR_EXPORT)
    if target.name not in scene.collection.children:
        scene.collection.children.link(target)
    moved = []
    for issue in issues:
        obj = scene.objects.get(issue.object_name)
        if not obj:
            continue
        if target not in obj.users_collection:
            target.objects.link(obj)
        for collection in list(obj.users_collection):
            if collection != target:
                collection.objects.unlink(obj)
        moved.append(obj.name)
    layer = _layer_collection(view_layer.layer_collection, target)
    if layer:
        layer.exclude = True
    return (f"Moved {len(moved)} objects to '{target.name}', which is switched off. "
            "Tick it in the Outliner to bring them back")
