"""Reports: a check run as data, saved to a file."""

import datetime
import json
from typing import List

import bpy

from .prefs import addon_version
from .presets import Preset
from .results import CheckResult, overall_status


def report_dict(preset: Preset, results: List[CheckResult], scope: str = "") -> dict:
    """Everything a report shows, as JSON-safe data."""
    return {
        "tool": "Vexa",
        "vexa": addon_version(),
        "preset": {"id": preset.id, "name": preset.name, "source": preset.source},
        "file": bpy.data.filepath or "(unsaved)",
        "scope": scope,
        "blender": bpy.app.version_string,
        "created": datetime.datetime.now().isoformat(timespec="seconds"),
        "status": overall_status(results),
        "counts": {s: sum(1 for r in results if r.status == s) for s in ("ERROR", "WARNING", "INFO", "PASS")},
        "results": [r.to_dict() for r in results],
    }


def write_report(path: str, preset: Preset, results: List[CheckResult], scope: str = "") -> None:
    """Saves the report as JSON."""
    with open(path, "w", encoding="utf-8") as f:
        json.dump(report_dict(preset, results, scope), f, indent=2, ensure_ascii=False)
