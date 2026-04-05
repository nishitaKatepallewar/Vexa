"""Abstract LLM client and implementations."""

import http.client
import json
import logging
import ssl
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class LLMClient(ABC):
    """Abstract base class for LLM clients."""

    @abstractmethod
    def generate_content(
        self, prompt: str, tools_schema: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Sends a prompt and tool definitions to the LLM."""
        pass

    @abstractmethod
    def parse_function_call(
        self, response_json: Dict[str, Any]
    ) -> Tuple[Optional[str], Optional[Dict[str, Any]]]:
        """Extracts function name and args from LLM response."""
        pass


class GeminiClient(LLMClient):
    """Google Gemini REST API client."""

    DEFAULT_MODEL = "gemini-2.5-flash"
    TIMEOUT_SECONDS = 10

    def __init__(self, api_key: str, model_name: str = DEFAULT_MODEL):
        self.api_key = api_key
        self.host = "generativelanguage.googleapis.com"
        self.model = model_name

    def generate_content(
        self, prompt: str, tools_schema: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        path = f"/v1beta/models/{self.model}:generateContent?key={self.api_key}"

        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "tools": [{"function_declarations": tools_schema}],
            "tool_config": {"function_calling_config": {"mode": "AUTO"}},
        }

        headers = {"Content-Type": "application/json"}
        context = ssl.create_default_context()

        try:
            conn = http.client.HTTPSConnection(
                self.host, context=context, timeout=self.TIMEOUT_SECONDS
            )
            conn.request("POST", path, json.dumps(payload), headers)
            response = conn.getresponse()
            data = response.read()
            conn.close()

            if response.status != 200:
                return {"error": f"HTTP {response.status}: {data.decode('utf-8')}"}

            return json.loads(data)

        except Exception as e:
            logger.error(f"Gemini API error: {e}")
            return {"error": str(e)}

    def parse_function_call(
        self, response_json: Dict[str, Any]
    ) -> Tuple[Optional[str], Optional[Dict[str, Any]]]:
        try:
            candidates = response_json.get("candidates", [])
            if not candidates:
                return None, None

            content = candidates[0].get("content", {})
            parts = content.get("parts", [])

            for part in parts:
                fn_call = part.get("functionCall")
                if fn_call:
                    return fn_call.get("name"), fn_call.get("args", {})

            return None, None

        except Exception as e:
            logger.error(f"Error parsing Gemini response: {e}")
            return None, None


def create_llm_client(provider: str, api_key: str, model_name: str = "") -> LLMClient:
    """Factory function to create LLM clients."""
    if provider.lower() == "gemini":
        return GeminiClient(api_key, model_name or GeminiClient.DEFAULT_MODEL)
    raise ValueError(f"Unknown LLM provider: {provider}")
