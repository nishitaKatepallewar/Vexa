"""Registry module for Vexa tools exposed to Gemini."""

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


@dataclass
class RegisteredTool:
    """A registered tool with its function, schema, and metadata."""

    name: str
    func: Callable
    schema: Dict[str, Any]
    metadata: ToolMetadata = field(default_factory=ToolMetadata)


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
            name = func.__name__
            doc = inspect.getdoc(func) or "No description provided."
            sig = inspect.signature(func)

            metadata = ToolMetadata(
                display_name=display_name or name.replace("_", " ").title(),
                is_quick_action=is_quick_action,
                category=category,
                description=doc,
            )

            schema = cls._generate_schema(func)
            tool = RegisteredTool(
                name=name,
                func=func,
                schema=schema,
                metadata=metadata,
            )

            cls._tools[name] = tool
            cls._schemas.append(schema)

            return func

        return decorator

    @classmethod
    def get_tool(cls, name: str) -> Optional[Callable]:
        """Retrieves a registered function by name."""
        tool = cls._tools.get(name)
        return tool.func if tool else None

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
