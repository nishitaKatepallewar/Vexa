"""Helpers for reading Vexa's add-on preferences."""

import bpy

# Root package name of the add-on ("vexa", or "bl_ext.<repo>.vexa" when installed
# as a Blender extension). Preferences are registered under this name.
ADDON_ID = __package__.rsplit(".", 1)[0]


def get_prefs(context: bpy.types.Context = None):
    """Returns Vexa's AddonPreferences, or None if the add-on isn't registered."""
    context = context or bpy.context
    addon = context.preferences.addons.get(ADDON_ID)
    return addon.preferences if addon else None


def has_ai_key(context: bpy.types.Context = None) -> bool:
    """True when the optional Gemini key has been entered."""
    prefs = get_prefs(context)
    return bool(prefs and prefs.api_key.strip())
