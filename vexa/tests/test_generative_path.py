"""Unit tests for the catch-all generative path changes.

Run from the Vexa/ directory:
    python3 -c "import sys; sys.path.insert(0, 'vexa'); exec(open('vexa/tests/test_generative_path.py').read())"

Or standalone (from Vexa/ directory):
    PYTHONPATH=vexa python3 vexa/tests/test_generative_path.py
"""

import ast
import sys
import os
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class MockTool:
    def __call__(self, intent=None):
        return f"Found 3 floating vertices in TestMesh"


def test_syntax_check():
    """All modified files have valid Python syntax."""
    files = [
        "vexa/core/generator.py",
        "vexa/tools/general_tools.py",
        "vexa/operators/execute_prompt.py",
    ]
    for f in files:
        with open(f) as fh:
            ast.parse(fh.read())
    print("  PASS: All files have valid syntax")


def test_import_chain_no_cycles():
    """Import chain is acyclic: general_tools -> generator -> client."""
    with open("vexa/core/generator.py") as f:
        gen_code = f.read()
    with open("vexa/core/client.py") as f:
        client_code = f.read()
    with open("vexa/tools/general_tools.py") as f:
        tools_code = f.read()

    assert "generator" not in client_code, "client.py should not import generator"
    assert "registry" not in client_code, "client.py should not import registry"
    assert "client" in gen_code, "generator.py should import client"
    assert "AgentTools" in gen_code, "generator.py should import registry"
    assert "AgentTools" in tools_code, "general_tools should import registry"
    print("  PASS: Import chain is acyclic")


def test_run_generative_path_signature():
    """run_generative_path exists and has correct signature."""
    with open("vexa/core/generator.py") as f:
        code = f.read()
    assert "def run_generative_path(intent: str, prefs)" in code, \
        "run_generative_path should have signature (intent: str, prefs)"
    assert "tool_func(intent=intent)" in code, \
        "run_generative_path should call tool_func with intent argument"
    print("  PASS: run_generative_path signature is correct")


def test_analyze_custom_check_registered():
    """analyze_custom_check is registered in AgentTools."""
    with open("vexa/tools/general_tools.py") as f:
        code = f.read()
    assert "def analyze_custom_check" in code
    assert "@AgentTools.register" in code
    assert '"Custom"' in code or "'Custom'" in code
    print("  PASS: analyze_custom_check is registered")


def test_execute_prompt_uses_run_generative_path():
    """execute_prompt.py calls run_generative_path in _try_generative_path."""
    with open("vexa/operators/execute_prompt.py") as f:
        code = f.read()
    assert "run_generative_path" in code
    assert "ToolGenerator" not in code, "ToolGenerator should no longer be imported in execute_prompt"
    assert "is_feasible_check" not in code, "is_feasible_check should no longer be imported in execute_prompt"
    assert "hashlib" not in code, "hashlib should no longer be imported in execute_prompt"
    print("  PASS: execute_prompt.py correctly uses run_generative_path")


def test_schemas_include_analyze_custom_check():
    """analyze_custom_check is registered and has correct schema."""
    with open("vexa/tools/general_tools.py") as f:
        code = f.read()
    assert "def analyze_custom_check(intent: str)" in code, \
        "analyze_custom_check should accept 'intent' parameter"
    assert "@AgentTools.register" in code, \
        "analyze_custom_check should use @AgentTools.register decorator"
    assert '"Custom"' in code or "'Custom'" in code, \
        "analyze_custom_check should be in 'Custom' category"
    print("  PASS: analyze_custom_check is registered with correct signature")


def test_generated_tool_called_with_intent():
    """Generated tools are called with intent argument (not no args)."""
    with open("vexa/core/generator.py") as f:
        code = f.read()
    assert "tool_func(intent=intent)" in code, "Generated tool must be called with intent argument"
    print("  PASS: Generated tools are called with intent argument")


def test_deferred_import_in_analyze_custom_check():
    """analyze_custom_check imports run_generative_path inside the function body."""
    with open("vexa/tools/general_tools.py") as f:
        lines = f.readlines()

    in_func = False
    found_deferred_import = False
    for line in lines:
        if "def analyze_custom_check" in line:
            in_func = True
        if in_func and "from vexa.core.generator import run_generative_path" in line:
            found_deferred_import = True
        if in_func and line.strip().startswith("@AgentTools"):
            break

    assert found_deferred_import, "run_generative_path should be imported inside the function body"
    print("  PASS: Deferred import avoids circular dependency")


def run_all():
    print("\n=== Vexa Generative Path Tests ===\n")
    test_syntax_check()
    test_import_chain_no_cycles()
    test_run_generative_path_signature()
    test_analyze_custom_check_registered()
    test_execute_prompt_uses_run_generative_path()
    test_schemas_include_analyze_custom_check()
    test_generated_tool_called_with_intent()
    test_deferred_import_in_analyze_custom_check()
    print("\n  All tests passed!")


if __name__ == "__main__":
    run_all()