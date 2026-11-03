"""Selects the objects and mesh elements a check flagged, so artists can see them."""

import bpy

from .results import CheckResult


def select_result(result: CheckResult, context=None) -> int:
    """Selects every flagged object and, where issues name faces, edges or vertices,
    enters Edit Mode with exactly those selected. Returns the number of objects selected.
    """
    context = context or bpy.context
    if context.object and context.object.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")

    objs, element = [], None
    for issue in result.issues:
        obj = context.scene.objects.get(issue.object_name or "")
        if obj is None:
            continue
        if obj not in objs:
            objs.append(obj)
            if obj.type == "MESH":
                mesh = obj.data
                for elements in (mesh.polygons, mesh.edges, mesh.vertices):
                    elements.foreach_set("select", [False] * len(elements))
        if issue.element and issue.indices and obj.type == "MESH":
            element = issue.element
            elements = {"FACE": obj.data.polygons, "EDGE": obj.data.edges, "VERT": obj.data.vertices}[element]
            for i in issue.indices:
                if i < len(elements):
                    elements[i].select = True

    if not objs:
        return 0

    for obj in context.view_layer.objects:
        obj.select_set(obj in objs)
    context.view_layer.objects.active = objs[0]
    if element:
        bpy.ops.object.mode_set(mode="EDIT")
        bpy.ops.mesh.select_mode(type=element)
    return len(objs)
