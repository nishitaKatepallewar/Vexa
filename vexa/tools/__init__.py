"""Tool modules. Importing one registers its tools, checks and fixes with AgentTools."""

import importlib
import sys

MODULES = (
    "general_tools",
    "geometry_tools",
    "transform_tools",
    "uv_tools",
    "texture_tools",
    "naming_tools",
    "collision_tools",
    "rigging_tools",
)


def import_all() -> None:
    """Imports every tool module so its tools register with AgentTools.

    Modules that were already imported are reloaded: the add-on's unregister() clears
    the registry, and a plain import of a cached module wouldn't register them again.
    """
    for name in MODULES:
        module_name = f"{__name__}.{name}"
        if module_name in sys.modules:
            importlib.reload(sys.modules[module_name])
        else:
            importlib.import_module(module_name)
