"""Registry module for Vexa tools exposed to Gemini.

Every capability Vexa has is a registered tool, so the same function powers the
quick-action buttons (direct path) and Gemini function calling (inference path).

There are three kinds of tool:

* plain tools (`AgentTools.register`): one-off actions such as "Select Hard Edges".
* checks (`AgentTools.register_check`): find problems and return a list of
  `Issue`s. Keyword arguments with defaults are their settings (thresholds); presets
  override them by name, and the generated schema exposes them to Gemini.
* fixes (`AgentTools.register_fix`): safe one-click repairs for one check's issues.

When a check or fix is called as a tool (a quick action or by Gemini) it runs on the
selected meshes and returns a readable summary, like any other tool.
"""

import atexit
import functools
import inspect
import typing
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


@dataclass
class ToolMetadata:
    """Metadata for a registered tool."""

    display_name: str = ""
    is_quick_action: bool = False
    category: str = "General"
    description: str = ""
    kind: str = "tool"  # "tool", "check" or "fix"
    # Checks only:
    why: str = ""  # one sentence an artist understands: what breaks in engine
    default_severity: str = "WARNING"  # "ERROR", "WARNING" or "INFO"
    pass_text: str = "OK"  # shown in results when nothing is wrong
    fix_name: Optional[str] = None  # the registered fix for this check, if any
    # Fixes only:
    check_name: Optional[str] = None  # the check whose issues this fix repairs


@dataclass
class RegisteredTool:
    """A registered tool with its function, schema, and metadata.

    func: what quick actions and Gemini call. For checks and fixes this is a wrapper
          that runs on the selection and returns a summary string.
    impl: for checks and fixes, the underlying function the runner calls directly.
    """

    name: str
    func: Callable
    schema: Dict[str, Any]
    metadata: ToolMetadata = field(default_factory=ToolMetadata)
    impl: Optional[Callable] = None


class AgentTools:
    """Registry for AI-exposed functions."""

    _tools: Dict[str, RegisteredTool] = {}
    _schemas: List[Dict[str, Any]] = []

    @classmethod
    def register(
        cls,
        display_name: str = "",
        is_quick_action: bool = False,
        category: str = "General",
    ) -> Callable:
        """Decorator to register a function as an AI tool.

        Args:
            display_name: Human-readable name for UI display.
            is_quick_action: Whether to show as a button in the UI.
            category: Category for grouping in UI.

        Returns:
            A decorator function.
        """

        def decorator(func: Callable) -> Callable:
            cls._add(func, ToolMetadata(
                display_name=display_name or _title(func.__name__),
                is_quick_action=is_quick_action,
                category=category,
                description=inspect.getdoc(func) or "No description provided.",
            ))
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
            name = func.__name__

            @functools.wraps(func)
            def as_tool(**settings) -> str:
                from .runner import run_check_as_tool

                return run_check_as_tool(name, settings)

            cls._add(as_tool, ToolMetadata(
                display_name=display_name or _title(name),
                is_quick_action=is_quick_action,
                category=category,
                description=inspect.getdoc(func) or "No description provided.",
                kind="check",
                why=why,
                default_severity=severity.upper(),
                pass_text=pass_text,
            ), impl=func)
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
        """

        def decorator(func: Callable) -> Callable:
            check = cls._tools.get(check_name)
            if check is None or check.metadata.kind != "check":
                raise ValueError(f"register_fix: '{check_name}' is not a registered check")
            name = func.__name__

            def as_tool() -> str:
                from .runner import run_fix_as_tool

                return run_fix_as_tool(name)

            # The tool takes no arguments (it finds the issues itself), so it gets its
            # own name and docstring rather than the fix's signature.
            as_tool.__name__ = name
            as_tool.__doc__ = inspect.getdoc(func)

            cls._add(as_tool, ToolMetadata(
                display_name=display_name or _title(name),
                is_quick_action=is_quick_action,
                category=category or check.metadata.category,
                description=inspect.getdoc(func) or "No description provided.",
                kind="fix",
                check_name=check_name,
            ), impl=func)
            check.metadata.fix_name = name
            return func

        return decorator

    @classmethod
    def _add(cls, func: Callable, metadata: ToolMetadata, impl: Optional[Callable] = None) -> None:
        name = func.__name__
        schema = cls._generate_schema(func)
        # Re-registering (e.g. a module reloaded) replaces the old entry.
        cls._schemas[:] = [s for s in cls._schemas if s["name"] != name]
        cls._tools[name] = RegisteredTool(name=name, func=func, schema=schema, metadata=metadata, impl=impl)
        cls._schemas.append(schema)

    @classmethod
    def clear(cls) -> None:
        """Removes every registered tool."""
        cls._tools.clear()
        cls._schemas.clear()

    @classmethod
    def get_tool(cls, name: str) -> Optional[Callable]:
        """Retrieves a registered function by name."""
        tool = cls._tools.get(name)
        return tool.func if tool else None

    @classmethod
    def get_registered(cls, name: str) -> Optional[RegisteredTool]:
        """Retrieves the full registry entry for a tool, check or fix."""
        return cls._tools.get(name)

    @classmethod
    def get_check(cls, name: str) -> Optional[RegisteredTool]:
        """Retrieves a registered check by name."""
        tool = cls._tools.get(name)
        return tool if tool and tool.metadata.kind == "check" else None

    @classmethod
    def get_checks(cls) -> List[RegisteredTool]:
        """Returns every registered check."""
        return [t for t in cls._tools.values() if t.metadata.kind == "check"]

    @classmethod
    def get_tool_metadata(cls, name: str) -> Optional[ToolMetadata]:
        """Retrieves metadata for a registered tool."""
        tool = cls._tools.get(name)
        return tool.metadata if tool else None

    @classmethod
    def get_schemas(cls) -> List[Dict[str, Any]]:
        """Returns the list of generated tool schemas."""
        return cls._schemas

    @classmethod
    def get_categories(cls) -> List[str]:
        """Returns all unique categories from registered tools."""
        return sorted(set(t.metadata.category for t in cls._tools.values()))

    @classmethod
    def get_tools_by_category(cls) -> Dict[str, List[RegisteredTool]]:
        """Returns tools grouped by category."""
        result: Dict[str, List[RegisteredTool]] = {}
        for tool in cls._tools.values():
            cat = tool.metadata.category
            if cat not in result:
                result[cat] = []
            result[cat].append(tool)
        return result

    @staticmethod
    def _generate_schema(func: Callable) -> Dict[str, Any]:
        """Generates a Gemini Function Declaration from a Python function.

        Args:
            func: The function to inspect.

        Returns:
            A dictionary matching the Gemini `FunctionDeclaration` schema.
        """
        sig = inspect.signature(func)
        doc = inspect.getdoc(func) or "No description provided."

        parameters = {
            "type": "OBJECT",
            "properties": {},
            "required": [],
        }

        for name, param in sig.parameters.items():
            param_type = "STRING"  # Default
            prop_def = {}

            if param.annotation == int:
                param_type = "INTEGER"
            elif param.annotation == float:
                param_type = "NUMBER"
            elif param.annotation == bool:
                param_type = "BOOLEAN"

            is_list = (
                param.annotation == list or typing.get_origin(param.annotation) == list
            )

            if is_list:
                param_type = "ARRAY"
                prop_def = {
                    "type": param_type,
                    "items": {"type": "STRING"},
                    "description": f"Parameter {name}",
                }
            else:
                prop_def = {
                    "type": param_type,
                    "description": f"Parameter {name}",
                }

            parameters["properties"][name] = prop_def

            if param.default == inspect.Parameter.empty:
                parameters["required"].append(name)

        return {
            "name": func.__name__,
            "description": doc,
            "parameters": parameters,
        }


def _title(name: str) -> str:
    return name.replace("_", " ").title()


# Drop registered functions before the interpreter shuts down. Holding them (and so
# the modules that import bpy) until finalization can crash Blender's Python module
# on exit; the API docs advise against long-lived references to Blender data.
atexit.register(AgentTools.clear)
