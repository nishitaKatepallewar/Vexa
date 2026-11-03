"""Tests for the LLM provider layer.

The golden file pins exactly what Gemini is offered. If you add, rename or change a
tool on purpose, regenerate it and review the diff:

    python tests/test_llm.py --update-golden
    blender -b --factory-startup -P tests/test_llm.py -- --update-golden
"""

import json
import os
import sys

# Repo root first, so tests always import this checkout's vexa (not an installed copy).
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from vexa.core.llm import PROVIDERS, LLMClient, create_client  # noqa: E402
from vexa.core.llm.gemini import GeminiClient, function_declarations  # noqa: E402
from vexa.core.registry import AgentTools  # noqa: E402
from helpers import main, test  # noqa: E402

GOLDEN = os.path.join(os.path.dirname(os.path.abspath(__file__)), "golden", "gemini_function_declarations.json")


@test
def gemini_is_offered_exactly_the_golden_tools():
    actual = function_declarations(AgentTools.tool_specs())
    with open(GOLDEN, encoding="utf-8") as f:
        expected = json.load(f)
    assert [d["name"] for d in actual] == [d["name"] for d in expected], "tool list changed (see module docstring)"
    for a, e in zip(actual, expected):
        assert a == e, f"{a['name']} changed (see module docstring)\nexpected {e}\nactual   {a}"


@test
def gemini_request_shape():
    client = GeminiClient("secret", "")
    request = client.build_request("find ngons", AgentTools.tool_specs())
    assert client.model == GeminiClient.default_model
    assert request.host == "generativelanguage.googleapis.com"
    assert request.path == f"/v1beta/models/{GeminiClient.default_model}:generateContent"
    assert request.headers["x-goog-api-key"] == "secret" and "secret" not in request.path
    assert request.body["contents"] == [{"parts": [{"text": "find ngons"}]}]
    assert request.body["tool_config"] == {"function_calling_config": {"mode": "AUTO"}}
    assert json.loads(json.dumps(request.to_dict()))["host"] == request.host  # plain JSON for the worker


@test
def gemini_reply_with_a_tool_call():
    reply = GeminiClient("k").parse_response({"candidates": [{"content": {"parts": [
        {"functionCall": {"name": "detect_ngons", "args": {"x": 1}}}]}}]})
    assert reply.tool_call.name == "detect_ngons" and reply.tool_call.args == {"x": 1} and reply.text == ""


@test
def gemini_reply_with_text_or_nothing():
    reply = GeminiClient("k").parse_response({"candidates": [{"content": {"parts": [{"text": "Hello"}]}}]})
    assert reply.tool_call is None and reply.text == "Hello"
    assert GeminiClient("k").parse_response({}).tool_call is None
    assert GeminiClient("k").parse_response({"candidates": []}).text == ""


@test
def providers_implement_the_interface():
    for key, cls in PROVIDERS.items():
        assert issubclass(cls, LLMClient) and cls.label and cls.default_model, key
        assert isinstance(create_client(key, "k"), cls)
    try:
        create_client("no-such-provider", "k")
    except ValueError:
        return
    raise AssertionError("expected ValueError")


def update_golden() -> None:
    with open(GOLDEN, "w", encoding="utf-8") as f:
        json.dump(function_declarations(AgentTools.tool_specs()), f, indent=2)
        f.write("\n")
    print(f"Wrote {GOLDEN}")


if __name__ == "__main__":
    if "--update-golden" in sys.argv:
        update_golden()
        from helpers import finish
        finish(0)
    main(globals())
