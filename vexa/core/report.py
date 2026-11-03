"""Reports: a check run as data, saved as an HTML page or as JSON.

The HTML report is vexa/templates/report.html with the report data embedded, so one
self-contained file is both readable and machine-readable.
"""

import datetime
import json
import os
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
        "file": bpy.data.filepath,  # empty for an unsaved file
        "scope": scope,
        "blender": bpy.app.version_string,
        "created": datetime.datetime.now().isoformat(timespec="seconds"),
        "status": overall_status(results),
        "counts": {s: sum(1 for r in results if r.status == s) for s in ("ERROR", "WARNING", "INFO", "PASS")},
        "results": [r.to_dict() for r in results],
    }


TEMPLATE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "templates", "report.html")
PLACEHOLDER = "/*VEXA_REPORT_JSON*/"

# Characters that could end the <script> block or start an HTML comment if they
# appeared raw inside it (an object named "</script>", say). JSON allows them escaped.
_SCRIPT_SAFE = {"<": "\\u003c", ">": "\\u003e", "&": "\\u0026", "\u2028": "\\u2028", "\u2029": "\\u2029"}


def render_html(data: dict) -> str:
    """The HTML report for `data` (from report_dict)."""
    payload = json.dumps(data, ensure_ascii=False)
    for char, escaped in _SCRIPT_SAFE.items():
        payload = payload.replace(char, escaped)
    with open(TEMPLATE, encoding="utf-8") as f:
        template = f.read()
    return template.replace(PLACEHOLDER, payload, 1)


def write_report(path: str, preset: Preset, results: List[CheckResult], scope: str = "") -> str:
    """Saves the report: HTML for a .html or .htm path, JSON otherwise. Returns the path."""
    data = report_dict(preset, results, scope)
    if path.lower().endswith((".html", ".htm")):
        text = render_html(data)
    else:
        text = json.dumps(data, indent=2, ensure_ascii=False)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    return path
