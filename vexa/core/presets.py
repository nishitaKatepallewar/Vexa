"""Presets: named targets such as "Unreal project", stored as JSON.

A preset picks which checks run, how severe each one is, and any settings:

    {
      "id": "unreal",
      "name": "Unreal project",
      "checks": {
        "detect_missing_lightmap_uvs": {"severity": "ERROR", "channel": 1},
        "detect_over_triangle_budget":  {"severity": "WARNING", "max_tris": 20000}
      }
    }

Check names are registered check names; settings are the check function's keyword
arguments. Built-in presets live in vexa/presets/. Teams can add their own .json
files in an extra folder (see `extra_dirs`) to share a studio spec.
"""

import json
import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .registry import AgentTools

BUILTIN_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "presets")


@dataclass
class Preset:
    id: str
    name: str
    description: str = ""
    source: str = ""
    order: int = 100
    checks: Dict[str, Dict] = field(default_factory=dict)
    path: str = ""

    def settings(self, check_name: str) -> Dict:
        """This preset's settings for one check, without the severity."""
        return {k: v for k, v in self.checks.get(check_name, {}).items() if k != "severity"}

    def severity(self, check_name: str) -> str:
        check = AgentTools.get_check(check_name)
        default = check.metadata.default_severity if check else "WARNING"
        return str(self.checks.get(check_name, {}).get("severity", default)).upper()


_cache: Dict[str, Preset] = {}
_loaded = False


def _load_file(path: str) -> Optional[Preset]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError) as e:
        print(f"Vexa: couldn't read preset {path}: {e}")
        return None
    pid = data.get("id") or os.path.splitext(os.path.basename(path))[0]
    return Preset(
        id=pid,
        name=data.get("name", pid),
        description=data.get("description", ""),
        source=data.get("source", ""),
        order=int(data.get("order", 100)),
        checks=dict(data.get("checks", {})),
        path=path,
    )


def load_presets(extra_dirs: Optional[List[str]] = None) -> List[Preset]:
    """(Re)loads built-in presets plus any in extra_dirs. Later files override earlier ids."""
    global _loaded
    _cache.clear()
    _loaded = True
    for folder in [BUILTIN_DIR] + list(extra_dirs or []):
        if not folder or not os.path.isdir(folder):
            continue
        for fn in sorted(os.listdir(folder)):
            if fn.endswith(".json"):
                preset = _load_file(os.path.join(folder, fn))
                if preset:
                    _cache[preset.id] = preset
    return all_presets()


def all_presets() -> List[Preset]:
    if not _loaded:
        load_presets()
    return sorted(_cache.values(), key=lambda p: (p.order, p.name))


def get_preset(preset_id: str) -> Optional[Preset]:
    if not _loaded:
        load_presets()
    return _cache.get(preset_id)
