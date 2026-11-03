"""LLM providers for the AI assistant.

To add a provider: subclass LLMClient in a new module (see gemini.py) and add it to
PROVIDERS. Nothing else in Vexa needs to change.
"""

import os
from typing import Dict, Type

from .base import HttpRequest, LLMClient, LLMReply, ToolCall
from .gemini import GeminiClient

PROVIDERS: Dict[str, Type[LLMClient]] = {
    "gemini": GeminiClient,
}

#: The script that sends a request in a separate process (see worker.py).
WORKER_SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "worker.py")


def create_client(provider: str, api_key: str, model: str = "") -> LLMClient:
    """Returns a client for `provider` (a key of PROVIDERS)."""
    try:
        cls = PROVIDERS[provider]
    except KeyError:
        raise ValueError(f"Unknown LLM provider: {provider}") from None
    return cls(api_key, model)


__all__ = ["HttpRequest", "LLMClient", "LLMReply", "PROVIDERS", "ToolCall", "WORKER_SCRIPT", "create_client"]
