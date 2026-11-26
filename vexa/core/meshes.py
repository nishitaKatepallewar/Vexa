"""The mesh as it will be exported: with modifiers applied.

Exporters for game engines apply modifiers by default (FBX's Apply Modifiers is
on), and the viewport shows the result, so checks that count or inspect faces
look at that mesh. Checks only read: nothing here changes the scene.
"""

import contextlib

import bpy


def has_shape_modifiers(obj) -> bool:
    """True if a modifier other than Armature is on, so the exported mesh differs.

    Armature only poses the mesh; its faces, edges and vertices stay the same.
    """
    return any(m.show_viewport and m.type != "ARMATURE" for m in obj.modifiers)


@contextlib.contextmanager
def exported_mesh(obj):
    """Yields the object's mesh with its modifiers applied (or its own mesh if none).

    The evaluated copy is freed when the block ends, so don't keep references to it.
    """
    if not has_shape_modifiers(obj):
        yield obj.data
        return
    evaluated = obj.evaluated_get(bpy.context.evaluated_depsgraph_get())
    mesh = evaluated.to_mesh()
    try:
        yield mesh
    finally:
        evaluated.to_mesh_clear()
