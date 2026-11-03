"""Runs registered checks and fixes.

No UI code here, so the same functions power the panel, quick actions, the AI path
and tests. Saving results to a file lives in core/report.py.
"""

import inspect
from typing import Dict, Iterable, List, Optional, Set

from . import scope as scope_mod
from .presets import Preset
from .registry import CHECK, AgentTools
from .results import PASS, CheckResult, Issue, summarize


def check_settings(check_name: str, overrides: Optional[Dict] = None) -> Dict:
    """The check's default settings (its keyword arguments) with overrides applied.

    Raises ValueError for a setting the check doesn't have, so a typo in a preset is
    reported instead of silently ignored.
    """
    check = AgentTools.get(check_name, kind=CHECK)
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
    check = AgentTools.get(check_name, kind=CHECK)
    if check is None:
        return CheckResult(check_name, check_name, "INFO", "Unknown check (update Vexa?)")
    try:
        settings = check_settings(check_name, overrides)
        with scope_mod.using(scope):
            issues: List[Issue] = check.func(**settings) or []
    except Exception as e:  # noqa: BLE001 - one broken check must never stop a run
        return CheckResult(check_name, check.display_name, "ERROR", f"Check failed: {e}", why=check.check.why)
    return CheckResult(
        check_id=check_name,
        title=check.display_name,
        status=(severity or check.check.severity) if issues else PASS,
        summary=summarize(issues, check.check.pass_text),
        why=check.check.why,
        fixable=bool(issues) and AgentTools.fix_for(check_name) is not None,
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
    fix = AgentTools.fix_for(result.check_id)
    if not (fix and result.issues):
        return "Nothing to fix"
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
    fix = AgentTools.get(fix_name)
    scope = scope_mod.current()
    result = run_check(fix.fix.check, None, scope)
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
