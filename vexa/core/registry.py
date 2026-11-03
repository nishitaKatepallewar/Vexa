"""The registry of everything Vexa can do: tools, checks and fixes.

Every capability is a registered function, so the same entry powers the quick-action
buttons (direct path), LLM function calling (inference path) and presets.

There are three kinds:

* tools (`AgentTools.register`): actions such as "Select Hard Edges". Return a message.
* checks (`AgentTools.register_check`): find problems and return a list of `Issue`s.
  Keyword arguments with defaults are their settings (thresholds); presets override
  them by name, and the tool spec exposes them to the LLM.
* fixes (`AgentTools.register_fix`): safe one-click repairs for one check's issues.

The registry only stores functions and their metadata, and imports nothing else from
Vexa. It never runs anything: core/dispatch.py runs a tool by name, and core/runner.py
runs checks for presets.
"""

import atexit
import inspect
import typing
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

TOOL = "tool"
CHECK = "check"
FIX = "fix"


@dataclass(frozen=True)
class CheckInfo:
    """What only checks have.

    why:       one sentence an artist understands: what breaks in engine if this fails.
    severity:  default severity when the check finds issues: "ERROR", "WARNING" or "INFO".
    pass_text: short text shown in results when nothing is wrong.
    """

    why: str
    severity: str
    pass_text: str


@dataclass(frozen=True)
class FixInfo:
    """What only fixes have: the name of the check whose issues this fix repairs."""

    check: str


@dataclass(frozen=True)
class RegisteredTool:
    """One registry entry: the decorated function, unchanged, and its metadata.

    `check` is set only for checks, and `fix` only for fixes.
    """

    name: str
    func: Callable
    kind: str
    display_name: str
    category: str
    description: str
    is_quick_action: bool = False
    check: Optional[CheckInfo] = None
    fix: Optional[FixInfo] = None


@dataclass(frozen=True)
class ToolSpec:
    """A provider-neutral description of a tool for LLM function calling.

    parameters: a standard JSON Schema object (lowercase types, e.g. "integer").
    Each LLM client converts specs into its provider's request format.
    """

    name: str
    description: str
    parameters: Dict[str, Any]


class AgentTools:
    """Registry of every tool, check and fix, keyed by function name."""

    _tools: Dict[str, RegisteredTool] = {}

    # ---------- registering ----------

    @classmethod
    def register(
        cls,
        display_name: str = "",
        is_quick_action: bool = False,
        category: str = "General",
    ) -> Callable:
        """Decorator to register a tool: an action that returns a message.

        Args:
            display_name: Human-readable name for UI display.
            is_quick_action: Whether to show as a button under Tools.
            category: Category for grouping in UI.
        """

        def decorator(func: Callable) -> Callable:
            cls._add(func, TOOL, display_name, category, is_quick_action)
            return func

        return decorator

    @classmethod
    def register_check(
        cls,
        display_name: str = "",
        category: str = "General",
        why: str = "",
        severity: str = "WARNING",
        pass_text: str = "OK",
        is_quick_action: bool = False,
    ) -> Callable:
        """Decorator to register a check.

        The decorated function takes only keyword settings with defaults, reads the
        meshes to inspect from `core.scope.current()`, and returns a list of
        `core.results.Issue` (empty when everything passes).

        Args:
            display_name: Name shown in results and quick actions.
            category: Category for grouping in UI.
            why: One sentence on what goes wrong in engine if this fails.
            severity: Default severity when the check finds issues.
            pass_text: Short text shown when nothing is wrong.
            is_quick_action: Whether to show as a button under Tools.
        """

        def decorator(func: Callable) -> Callable:
            cls._add(func, CHECK, display_name, category, is_quick_action,
                     check=CheckInfo(why=why, severity=severity.upper(), pass_text=pass_text))
            return func

        return decorator

    @classmethod
    def register_fix(
        cls,
        check_name: str,
        display_name: str = "",
        category: str = "",
        is_quick_action: bool = False,
    ) -> Callable:
        """Decorator to register a safe fix for an already registered check.

        The decorated function receives the check's issues as its first argument,
        plus any of the check's settings it names, and returns a summary string.
        A check has at most one fix.
        """

        def decorator(func: Callable) -> Callable:
            check = cls.get(check_name, kind=CHECK)
            if check is None:
                raise ValueError(f"register_fix: '{check_name}' is not a registered check")
            cls._add(func, FIX, display_name, category or check.category, is_quick_action,
                     fix=FixInfo(check=check_name))
            return func

        return decorator

    @classmethod
    def _add(cls, func: Callable, kind: str, display_name: str, category: str,
             is_quick_action: bool, check: Optional[CheckInfo] = None,
             fix: Optional[FixInfo] = None) -> None:
        name = func.__name__
        # Re-registering (e.g. a module reloaded) replaces the old entry.
        cls._tools.pop(name, None)
        cls._tools[name] = RegisteredTool(
            name=name,
            func=func,
            kind=kind,
            display_name=display_name or _title(name),
            category=category,
            description=inspect.getdoc(func) or "No description provided.",
            is_quick_action=is_quick_action,
            check=check,
            fix=fix,
        )

    @classmethod
    def clear(cls) -> None:
        """Removes every registered entry."""
        cls._tools.clear()

    # ---------- looking up ----------

    @classmethod
    def get(cls, name: str, kind: Optional[str] = None) -> Optional[RegisteredTool]:
        """The entry registered under `name`, or None. With `kind`, only an entry of that kind."""
        entry = cls._tools.get(name)
        if entry is None or (kind is not None and entry.kind != kind):
            return None
        return entry

    @classmethod
    def all(cls, kind: Optional[str] = None) -> List[RegisteredTool]:
        """Every entry in registration order. With `kind`, only entries of that kind."""
        return [e for e in cls._tools.values() if kind is None or e.kind == kind]

    @classmethod
    def fix_for(cls, check_name: str) -> Optional[RegisteredTool]:
        """The fix registered for a check, or None."""
        return next((e for e in cls.all(FIX) if e.fix.check == check_name), None)

    @classmethod
    def tool_specs(cls) -> List[ToolSpec]:
        """Provider-neutral specs for every entry, in registration order."""
        return [_spec(entry) for entry in cls.all()]


_JSON_TYPES = {int: "integer", float: "number", bool: "boolean"}


def _spec(entry: RegisteredTool) -> ToolSpec:
    """Builds a ToolSpec from an entry's signature and docstring.

    Parameters without a default are required. Annotations map to JSON Schema
    types: int, float, bool and list; anything else is a string. A fix is offered
    without parameters: when called by name it finds its check's issues itself.
    """
    params = {} if entry.kind == FIX else inspect.signature(entry.func).parameters
    properties: Dict[str, Any] = {}
    required: List[str] = []
    for name, param in params.items():
        annotation = param.annotation
        if annotation is list or typing.get_origin(annotation) is list:
            prop = {"type": "array", "items": {"type": "string"}}
        else:
            prop = {"type": _JSON_TYPES.get(annotation, "string")}
        prop["description"] = f"Parameter {name}"
        properties[name] = prop
        if param.default is inspect.Parameter.empty:
            required.append(name)
    return ToolSpec(
        name=entry.name,
        description=entry.description,
        parameters={"type": "object", "properties": properties, "required": required},
    )


def _title(name: str) -> str:
    return name.replace("_", " ").title()


# Drop registered functions before the interpreter shuts down. Holding them (and so
# the modules that import bpy) until finalization can crash Blender's Python module
# on exit; the API docs advise against long-lived references to Blender data.
atexit.register(AgentTools.clear)
