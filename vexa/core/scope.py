"""Which meshes a check looks at.

Checks never read the selection directly. They call `current()`, which returns the
scope the runner set up (Selected, Collection or Scene from the panel), or the
selected meshes when a check is called as a quick action or by the AI.
"""

import contextlib
import re
from dataclasses import dataclass, field
from typing import Iterable, List

import bpy

COLLISION_PREFIXES = ("UCX_", "UBX_", "UCP_", "USP_")


def is_collision_name(name: str) -> bool:
    """True for Unreal custom collision meshes (UCX_, UBX_, UCP_, USP_)."""
    return name.upper().startswith(COLLISION_PREFIXES)


def collision_base(name: str):
    """The render mesh a collision mesh belongs to: UCX_SM_Crate_01 -> SM_Crate.

    The trailing _NN index is optional. None if the name isn't a collision name.
    """
    for p in COLLISION_PREFIXES:
        if name.upper().startswith(p):
            rest = name[len(p):].split(".")[0]
            return re.sub(r"_\d+$", "", rest)
    return None


@dataclass
class CheckScope:
    """The objects a check runs on.

    meshes:    render meshes in scope (collision meshes excluded).
    collision: collision meshes in scope.
    scene:     the scene being checked (unit settings, object lookups).
    others:    objects in scope that aren't meshes (empties, cameras, lights, armatures...).
    """

    meshes: List
    collision: List
    scene: object
    others: List = field(default_factory=list)

    @property
    def all_meshes(self) -> List:
        return list(self.meshes) + list(self.collision)


def build_scope(objects: Iterable, scene=None) -> CheckScope:
    """Splits objects into render meshes, collision meshes and everything else."""
    # Make sure world matrices reflect transforms changed by scripts or fixes
    # (see the API docs, "Stale Data").
    try:
        bpy.context.view_layer.update()
    except Exception:  # noqa: BLE001 - no view layer in some background contexts
        pass
    meshes, collision, others = [], [], []
    for obj in objects:
        if obj.type != "MESH":
            others.append(obj)
        else:
            (collision if is_collision_name(obj.name) else meshes).append(obj)
    return CheckScope(meshes=meshes, collision=collision, scene=scene or bpy.context.scene, others=others)


_active: List[CheckScope] = []


@contextlib.contextmanager
def using(scope: CheckScope):
    """Makes `scope` what `current()` returns inside the `with` block."""
    _active.append(scope)
    try:
        yield scope
    finally:
        _active.pop()


def is_set() -> bool:
    """True inside `using()`, i.e. when the runner chose the scope."""
    return bool(_active)


def current() -> CheckScope:
    """The scope set by the runner, or the selected objects."""
    if _active:
        return _active[-1]
    return build_scope(bpy.context.selected_objects)
