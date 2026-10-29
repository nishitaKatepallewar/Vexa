"""Runs one HTTPS request in a separate process and saves the JSON response.

Blender's Python API docs ("Python Threads are Not Supported") recommend a separate
process rather than a background thread for work that outlives the calling script.
This file is executed by Blender's bundled Python as a standalone script; it never
imports bpy. It reads a request spec as JSON on stdin and writes the result to the
file path given as its first argument (a file, not stdout, so a large response can
never fill a pipe and stall the process).
"""

import http.client
import json
import ssl
import sys


def main() -> None:
    try:
        spec = json.load(sys.stdin)
        conn = http.client.HTTPSConnection(
            spec["host"], context=ssl.create_default_context(), timeout=spec.get("timeout", 30)
        )
        conn.request("POST", spec["path"], json.dumps(spec["body"]), spec["headers"])
        response = conn.getresponse()
        data = response.read().decode("utf-8", "replace")
        conn.close()
        if response.status != 200:
            result = {"error": f"HTTP {response.status}: {data[:500]}"}
        else:
            result = json.loads(data)
    except Exception as e:  # noqa: BLE001 - report any failure back to Blender
        result = {"error": str(e)}
    with open(sys.argv[1], "w", encoding="utf-8") as f:
        json.dump(result, f)


if __name__ == "__main__":
    main()
