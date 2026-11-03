"""Helpers for reading Vexa's add-on preferences."""

import sys

import bpy

# Root package name of the add-on ("vexa", or "bl_ext.<repo>.vexa" when installed
# as a Blender extension). Preferences are registered under this name.
ADDON_ID = __package__.rsplit(".", 1)[0]


def get_prefs(context: bpy.types.Context = None):
    """Returns Vexa's AddonPreferences, or None if the add-on isn't registered."""
    context = context or bpy.context
    addon = context.preferences.addons.get(ADDON_ID)
    return addon.preferences if addon else None


def addon_version() -> str:
    """The add-on's version from bl_info, e.g. "0.5.0", or "" if it isn't loaded."""
    module = sys.modules.get(ADDON_ID)
    version = getattr(module, "bl_info", {}).get("version", ())
    return ".".join(str(part) for part in version)


def has_ai_key(context: bpy.types.Context = None) -> bool:
    """True when the optional LLM API key has been entered."""
    prefs = get_prefs(context)
    return bool(prefs and prefs.api_key.strip())
