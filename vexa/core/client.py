"""Gemini REST Client for Vexa."""

import http.client
import json
import ssl
from typing import Any, Dict, List, Optional, Tuple, Union

DEFAULT_MODEL = "gemini-2.5-flash"
TIMEOUT_SECONDS = 10


class GeminiClient:
    """Handles communication with the Google Gemini REST API."""

    def __init__(self, api_key: str, model_name: str = DEFAULT_MODEL):
        """Initializes the client.

        Args:
            api_key: The Google Gemini API key.
            model_name: The model identifier (e.g., 'gemini-1.5-flash').
        """
        self.api_key = api_key
        self.host = "generativelanguage.googleapis.com"
        self.model = model_name

    def generate_content(
        self, prompt: str, tools_schema: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Sends a prompt and tool definitions to Gemini.

        Args:
            prompt: The user instruction.
            tools_schema: A list of function declarations for Gemini tools.

        Returns:
            The raw parsed JSON response from the API.
        """
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
                self.host, context=context, timeout=TIMEOUT_SECONDS
            )
            conn.request("POST", path, json.dumps(payload), headers)
            response = conn.getresponse()
            data = response.read()
            conn.close()

            if response.status != 200:
                print(f"Error from Gemini: {response.status} - {data}")
                return {
                    "error": f"HTTP {response.status}: {data.decode('utf-8')}"
                }

            return json.loads(data)

        except Exception as error:  # pylint: disable=broad-except
            return {"error": str(error)}

    def parse_function_call(
        self, response_json: Dict[str, Any]
    ) -> Tuple[Optional[str], Optional[Dict[str, Any]]]:
        """Extracts function name and args from Gemini response.

        Args:
            response_json: The JSON response from generate_content.

        Returns:
            A tuple of (function_name, arguments_dict). Both are None if
            no function call is found.
        """
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

        except Exception as error:  # pylint: disable=broad-except
            print(f"Error parsing response: {error}")
            return None, None
