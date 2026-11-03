"""Properties Vexa stores on the scene (saved per .blend) and window manager (session only)."""

import bpy

from .presets import all_presets

# Blender needs the enum items list kept alive while it's displayed.
_PRESET_ITEMS = []


def _preset_items(self, context):
    _PRESET_ITEMS.clear()
    for p in all_presets():
        _PRESET_ITEMS.append((p.id, p.name, p.description or p.name))
    if not _PRESET_ITEMS:
        _PRESET_ITEMS.append(("NONE", "No presets found", ""))
    return _PRESET_ITEMS


class VexaResultItem(bpy.types.PropertyGroup):
    check_id: bpy.props.StringProperty()
    title: bpy.props.StringProperty()
    status: bpy.props.StringProperty()
    summary: bpy.props.StringProperty()
    fixable: bpy.props.BoolProperty()
    has_objects: bpy.props.BoolProperty()


CLASSES = (VexaResultItem,)


def register_props():
    S = bpy.types.Scene
    S.vexa_preset = bpy.props.EnumProperty(
        name="Target", description="What these assets need to pass", items=_preset_items
    )
    S.vexa_scope = bpy.props.EnumProperty(
        name="Check",
        items=[
            ("SELECTED", "Selected", "Check the selected meshes"),
            ("COLLECTION", "Collection", "Check every mesh in the active collection"),
            ("SCENE", "Scene", "Check every mesh in the scene"),
        ],
        default="SELECTED",
    )
    S.vexa_disabled_checks = bpy.props.StringProperty(
        name="Disabled Checks", description="Checks turned off for this file", default=""
    )

    WM = bpy.types.WindowManager
    WM.vexa_results = bpy.props.CollectionProperty(type=VexaResultItem)
    WM.vexa_results_index = bpy.props.IntProperty(default=-1)
    WM.vexa_has_run = bpy.props.BoolProperty(default=False)


def unregister_props():
    for owner, names in (
        (bpy.types.Scene, ("vexa_preset", "vexa_scope", "vexa_disabled_checks")),
        (bpy.types.WindowManager, ("vexa_results", "vexa_results_index", "vexa_has_run")),
    ):
        for name in names:
            if hasattr(owner, name):
                delattr(owner, name)
