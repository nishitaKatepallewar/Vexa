"""Registry module for Vexa tools exposed to Gemini."""

import inspect
import typing
from typing import Any, Callable, Dict, List, Optional


class AgentTools:
    """Registry for AI-exposed functions."""

    _registry: Dict[str, Callable] = {}
    _schemas: List[Dict[str, Any]] = []

    @classmethod
    def register(cls, func: Callable) -> Callable:
        """Decorator to register a function as an AI tool.

        Args:
            func: The function to register.

        Returns:
            The original function, unmodified.
        """
        cls._registry[func.__name__] = func
        cls._schemas.append(cls._generate_schema(func))
        return func

    @classmethod
    def get_tool(cls, name: str) -> Optional[Callable]:
        """Retrieves a registered function by name."""
        return cls._registry.get(name)

    @classmethod
    def get_schemas(cls) -> List[Dict[str, Any]]:
        """Returns the list of generated tool schemas."""
        return cls._schemas

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

            # Check for List types
            is_list = (
                param.annotation == list
                or typing.get_origin(param.annotation) == list
            )

            if is_list:
                param_type = "ARRAY"
                # Gemini requires 'items' for ARRAY type.
                # For MVP, we assume lists are lists of strings.
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
