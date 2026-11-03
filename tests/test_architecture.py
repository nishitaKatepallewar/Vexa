"""Enforces the layering described in vexa/README.md by reading import statements.

Lower layers never import higher ones:

    registry  <-  llm, results, scope, presets, ...  (core)  <-  tools  <-  operators  <-  ui

It only parses source files; nothing is imported or run.
"""

import ast
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from helpers import main, test  # noqa: E402

VEXA = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "vexa")


def _module_name(path: str) -> str:
    rel = os.path.relpath(path, os.path.dirname(VEXA))[:-3].replace(os.sep, ".")
    return rel[: -len(".__init__")] if rel.endswith(".__init__") else rel


def vexa_imports(module_path: str) -> set:
    """Names of vexa modules a file imports, resolved to absolute dotted names."""
    name = _module_name(module_path)
    package = name if module_path.endswith("__init__.py") else name.rsplit(".", 1)[0]
    with open(module_path, encoding="utf-8") as f:
        tree = ast.parse(f.read())
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.level:
                base = package.rsplit(".", node.level - 1)[0] if node.level > 1 else package
                target = f"{base}.{node.module}" if node.module else base
            else:
                target = node.module or ""
            if target.startswith("vexa"):
                found.add(target)
                found.update(f"{target}.{alias.name}" for alias in node.names)
        elif isinstance(node, ast.Import):
            found.update(a.name for a in node.names if a.name.startswith("vexa"))
    return found


def modules(subdir: str):
    for root, _, files in os.walk(os.path.join(VEXA, subdir)):
        for fn in files:
            if fn.endswith(".py"):
                path = os.path.join(root, fn)
                yield _module_name(path), vexa_imports(path)


def _violations(subdir: str, forbidden: tuple) -> list:
    return [(mod, imp) for mod, imports in modules(subdir) for imp in imports
            if imp.startswith(forbidden)]


@test
def registry_imports_nothing_from_vexa():
    imports = vexa_imports(os.path.join(VEXA, "core", "registry.py"))
    assert not imports, imports


@test
def llm_providers_only_use_the_registry():
    bad = [(m, i) for m, imports in modules(os.path.join("core", "llm")) for i in imports
           if not i.startswith(("vexa.core.llm", "vexa.core.registry"))]
    assert not bad, bad


@test
def core_never_imports_tools_operators_or_ui():
    bad = _violations("core", ("vexa.tools", "vexa.operators", "vexa.ui"))
    assert not bad, bad


@test
def tools_only_import_core():
    bad = _violations("tools", ("vexa.operators", "vexa.ui"))
    assert not bad, bad


@test
def operators_never_import_ui():
    bad = _violations("operators", ("vexa.ui",))
    assert not bad, bad


if __name__ == "__main__":
    main(globals())
