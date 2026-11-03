"""Google Gemini (generativelanguage.googleapis.com) as an LLM provider."""

from typing import Any, Dict, List

from ..registry import ToolSpec
from .base import HttpRequest, LLMClient, LLMReply, ToolCall


def _gemini_types(schema: Any) -> Any:
    """Gemini's function declarations spell JSON Schema types in upper case."""
    if isinstance(schema, dict):
        return {k: (v.upper() if k == "type" and isinstance(v, str) else _gemini_types(v))
                for k, v in schema.items()}
    if isinstance(schema, list):
        return [_gemini_types(v) for v in schema]
    return schema


def function_declarations(tools: List[ToolSpec]) -> List[Dict[str, Any]]:
    """Tool specs in Gemini's FunctionDeclaration format."""
    return [{"name": t.name, "description": t.description, "parameters": _gemini_types(t.parameters)}
            for t in tools]


class GeminiClient(LLMClient):
    label = "Google Gemini"
    default_model = "gemini-2.5-flash"

    HOST = "generativelanguage.googleapis.com"

    def build_request(self, prompt: str, tools: List[ToolSpec]) -> HttpRequest:
        return HttpRequest(
            host=self.HOST,
            path=f"/v1beta/models/{self.model}:generateContent",
            # The key goes in a header, not the URL, so it never lands in logs or proxies.
            headers={"Content-Type": "application/json", "x-goog-api-key": self.api_key},
            body={
                "contents": [{"parts": [{"text": prompt}]}],
                "tools": [{"function_declarations": function_declarations(tools)}],
                "tool_config": {"function_calling_config": {"mode": "AUTO"}},
            },
        )

    def parse_response(self, data: Dict[str, Any]) -> LLMReply:
        candidates = data.get("candidates") or []
        if not candidates:
            return LLMReply()
        parts = (candidates[0].get("content") or {}).get("parts") or []
        for part in parts:
            call = part.get("functionCall")
            if call:
                return LLMReply(tool_call=ToolCall(call.get("name", ""), call.get("args") or {}))
        text = "".join(part.get("text", "") for part in parts)
        return LLMReply(text=text)
