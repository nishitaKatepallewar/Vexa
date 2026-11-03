"""The interface every LLM provider implements.

A provider only decides two things: how to turn a prompt and the registered tools
into an HTTP request, and how to read the reply. Sending the request (worker.py),
running the chosen tool (core/dispatch.py) and the UI are shared by all providers.
"""

from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

from ..registry import ToolSpec


@dataclass
class HttpRequest:
    """One HTTPS POST, as plain data, so a separate process can send it."""

    host: str
    path: str
    headers: Dict[str, str]
    body: Dict[str, Any]
    timeout: int = 30

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ToolCall:
    """The LLM asked to run one registered tool with these arguments."""

    name: str
    args: Dict[str, Any] = field(default_factory=dict)


@dataclass
class LLMReply:
    """What the LLM answered: a tool call, plain text, or neither."""

    tool_call: Optional[ToolCall] = None
    text: str = ""


class LLMClient(ABC):
    """Base class for LLM providers. Subclasses set the class attributes and
    implement build_request and parse_response."""

    #: Shown in the provider dropdown in Preferences.
    label: str = ""
    #: Used when the model field in Preferences is left empty.
    default_model: str = ""

    def __init__(self, api_key: str, model: str = ""):
        self.api_key = api_key
        self.model = model or self.default_model

    @abstractmethod
    def build_request(self, prompt: str, tools: List[ToolSpec]) -> HttpRequest:
        """The HTTP request that sends `prompt` and offers `tools` for function calling."""

    @abstractmethod
    def parse_response(self, data: Dict[str, Any]) -> LLMReply:
        """Reads the provider's JSON reply. Unrecognised replies return an empty LLMReply."""
