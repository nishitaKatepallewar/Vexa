"""Runs every Vexa test in one Blender process.

    blender -b --factory-startup -P tests/run_all.py
    python tests/run_all.py            (with the `bpy` module from PyPI installed)

Exits non-zero if any test fails, so it can gate CI.
"""

import glob
import importlib
import os
import sys

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, TESTS_DIR)

from helpers import collect, finish, run_tests  # noqa: E402


def main() -> None:
    tests = []
    for path in sorted(glob.glob(os.path.join(TESTS_DIR, "test_*.py"))):
        name = os.path.splitext(os.path.basename(path))[0]
        if name == "test_ui":
            continue  # registers the whole add-on, so it runs last on its own
        tests.extend(collect(vars(importlib.import_module(name))))
    failed = run_tests(tests)

    if os.path.exists(os.path.join(TESTS_DIR, "test_ui.py")):
        import test_ui
        failed += test_ui.run()

    finish(failed)


if __name__ == "__main__":
    main()
