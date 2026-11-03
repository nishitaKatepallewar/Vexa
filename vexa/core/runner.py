"""Runs registered checks and fixes.

No UI code here, so the same functions power the panel, quick actions, the AI path,
reports and tests.
"""

import datetime
import inspect
import json
from typing import Dict, Iterable, List, Optional, Set

import bpy

from . import scope as scope_mod
from .presets import Preset
from .registry import AgentTools
from .results import PASS, CheckResult, Issue, overall_status, summarize


def check_settings(check_name: str, overrides: Optional[Dict] = None) -> Dict:
    """The check's default settings (its keyword arguments) with overrides applied.

    Raises ValueError for a setting the check doesn't have, so a typo in a preset is
    reported instead of silently ignored.
    """
    check = AgentTools.get_check(check_name)
    params = inspect.signature(check.func).parameters
    settings = {k: p.default for k, p in params.items() if p.default is not inspect.Parameter.empty}
    for key, value in (overrides or {}).items():
        if key not in params:
            raise ValueError(f"'{check_name}' has no setting '{key}'")
        settings[key] = value
    return settings


def run_check(check_name: str, overrides: Optional[Dict], scope: scope_mod.CheckScope,
              severity: Optional[str] = None) -> CheckResult:
    """Runs one check on a scope and wraps its issues in a CheckResult."""
    check = AgentTools.get_check(check_name)
    if check is None:
        return CheckResult(check_name, check_name, "INFO", "Unknown check (update Vexa?)")
    meta = check.metadata
    try:
        settings = check_settings(check_name, overrides)
        with scope_mod.using(scope):
            issues: List[Issue] = check.func(**settings) or []
    except Exception as e:  # noqa: BLE001 - one broken check must never stop a run
        return CheckResult(check_name, meta.display_name, "ERROR", f"Check failed: {e}", why=meta.why)
    return CheckResult(
        check_id=check_name,
        title=meta.display_name,
        status=(severity or meta.default_severity) if issues else PASS,
        summary=summarize(issues, meta.pass_text),
        why=meta.why,
        fixable=bool(meta.fix_name) and bool(issues),
        issues=issues,
    )


def run_preset(preset: Preset, objects: Iterable, scene=None,
               disabled: Optional[Set[str]] = None) -> List[CheckResult]:
    """Runs every enabled check in a preset over the given objects."""
    scope = scope_mod.build_scope(objects, scene)
    disabled = disabled or set()
    return [run_check(name, preset.settings(name), scope, preset.severity(name))
            for name in preset.checks if name not in disabled]


def apply_fix(result: CheckResult, overrides: Optional[Dict], scope: scope_mod.CheckScope) -> str:
    """Applies a check's registered fix to the issues in `result`."""
    check = AgentTools.get_check(result.check_id)
    if not (check and check.metadata.fix_name and result.issues):
        return "Nothing to fix"
    fix = AgentTools.get_registered(check.metadata.fix_name)
    settings = check_settings(result.check_id, overrides)
    accepted = inspect.signature(fix.func).parameters
    kwargs = {k: v for k, v in settings.items() if k in accepted}
    with scope_mod.using(scope):
        return fix.func(result.issues, **kwargs)


# ---------- checks and fixes called as tools (quick actions, Gemini) ----------

def run_check_as_tool(check_name: str, overrides: Optional[Dict] = None) -> str:
    """Runs a check on the current scope, selects what it found, and summarizes."""
    from .selection import select_result

    result = run_check(check_name, overrides, scope_mod.current())
    if result.issues and not scope_mod.is_set():
        select_result(result)
    return describe(result)


def run_fix_as_tool(fix_name: str) -> str:
    """Finds the issues for a fix's check on the current scope, then fixes them."""
    fix = AgentTools.get_registered(fix_name)
    scope = scope_mod.current()
    result = run_check(fix.metadata.check_name, None, scope)
    if not result.issues:
        return f"{result.title}: nothing to fix."
    return apply_fix(result, None, scope)


def describe(result: CheckResult, max_issues: int = 5) -> str:
    """A short multi-line summary for the panel's response box or the AI."""
    if result.status == PASS:
        return f"{result.title}: {result.summary}."
    lines = [f"{result.title}: {result.summary}"]
    for issue in result.issues[:max_issues]:
        who = f"{issue.object_name}: " if issue.object_name else ""
        lines.append(f"  - {who}{issue.message}")
    if len(result.issues) > max_issues:
        lines.append(f"  - …and {len(result.issues) - max_issues} more")
    return "\n".join(lines)


# ---------- reports ----------

def report_dict(preset: Preset, results: List[CheckResult], scope: str = "") -> dict:
    return {
        "tool": "Vexa",
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
    with open(path, "w", encoding="utf-8") as f:
        json.dump(report_dict(preset, results, scope), f, indent=2, ensure_ascii=False)
