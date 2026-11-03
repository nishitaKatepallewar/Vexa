# Vexa

Technical documentation for developers.

## Architecture

Everything Vexa can do is a function registered in one registry,
`AgentTools` (`core/registry.py`). Every other part of the add-on only routes to
those functions by name.

```
tools/*_tools.py        functions decorated with @register / @register_check / @register_fix
        │
core/registry.py        AgentTools: name → function + metadata. Pure data.
        │
        ├── core/dispatch.py     invoke(name, args): run any tool, check or fix by name
        │       ├── operators/quick_actions.py   Tools buttons             (direct path)
        │       └── operators/execute_prompt.py  Ask Vexa, via core/llm/   (inference path)
        │
        └── core/runner.py       run a preset's checks, apply fixes
                ├── core/report.py   save a run as a report
                └── operators/check_ops.py + ui/panel.py   Check Assets panel (preset path)
```

### Layering rules

Lower layers never import higher ones. `tests/test_architecture.py` enforces this.

| Layer | May import from Vexa |
| --- | --- |
| `core/registry.py` | nothing |
| `core/llm/` | `core/registry.py`, itself |
| rest of `core/` | `core/` |
| `tools/` | `core/` |
| `operators/` | `core/`, `operators/` |
| `ui/` | anything |

The registry never runs anything, `core/` has no UI, and nothing in `core/` knows
which LLM is in use.

## Layout

```
vexa/
  core/
    registry.py     AgentTools: every tool, check and fix, and their LLM tool specs
    dispatch.py     invoke(name, args): the one way to run something by name
    runner.py       runs checks with preset settings, applies fixes
    report.py       turns a run into a report and saves it
    results.py      Issue and CheckResult: what every check returns
    scope.py        which meshes a check looks at (selection, or the runner's scope)
    selection.py    selects the objects and faces a check flagged
    presets.py      loads preset .json files
    props.py        Blender properties: per-file (scene) and per-session (window manager)
    prefs.py        reads the add-on preferences and version
    llm/            LLM providers: base.py (interface), gemini.py, worker.py (HTTP in a subprocess)
  tools/            every tool, check and fix, one module per area
  presets/          built-in targets: general, unity_asset_store, fab, unreal
  operators/        quick actions, Ask Vexa, the check panel's operators, feedback.py
  ui/panel.py       the sidebar
```

## Kinds of entry

| Kind | Register with | Returns | Example |
| --- | --- | --- | --- |
| Tool | `AgentTools.register` | a message string | `select_hard_edges` |
| Check | `AgentTools.register_check` | a list of `Issue` | `detect_ngons` |
| Fix | `AgentTools.register_fix` | a message string | `triangulate_ngons` |

All three are offered to the LLM and can be quick actions. Run by name through
`dispatch.invoke`, a check runs on the selected meshes, selects what it found and
returns a summary; a fix finds its check's issues on the selection and fixes them.

Looking things up:

```python
AgentTools.get("detect_ngons")              # any entry, or None
AgentTools.get("detect_ngons", kind=CHECK)  # only if it's a check
AgentTools.all(CHECK)                       # every check, in registration order
AgentTools.fix_for("detect_ngons")          # the check's fix, or None
AgentTools.tool_specs()                     # provider-neutral specs for the LLM
```

Each entry is a `RegisteredTool` with `name`, `func`, `kind`, `display_name`,
`category`, `description`, `is_quick_action`, plus `check` (`why`, `severity`,
`pass_text`) for checks and `fix` (`check`) for fixes.

## Implemented

| Area | Module | Checks | Fixes |
| --- | --- | --- | --- |
| General | `general_tools.py` | – | `count_vertices`, `rename_object`, `select_hard_edges` (tools) |
| Geometry | `geometry_tools.py` | `detect_ngons`, `detect_nonplanar_faces`, `detect_intersecting_meshes`, `detect_over_triangle_budget` | `triangulate_ngons`, `triangulate_nonplanar_faces` |
| Transforms | `transform_tools.py` | `detect_unapplied_transforms`, `detect_negative_scale`, `detect_off_center_pivots`, `detect_wrong_unit_scale` | `apply_transforms`, `move_pivots_to_bottom_center`, `set_unit_scale` |
| UVs | `uv_tools.py` | `detect_missing_uv_maps`, `detect_missing_lightmap_uvs` | – |
| Texture | `texture_tools.py` | `detect_missing_textures`, `detect_color_space_issues`, `detect_invalid_texture_sizes`, `detect_unused_material_slots` | `fix_color_spaces`, `remove_unused_material_slots` |
| Naming | `naming_tools.py` | `detect_default_names`, `detect_invalid_name_characters`, `detect_missing_name_prefix` | `fix_invalid_names`, `add_name_prefix` |
| Collision | `collision_tools.py` | `detect_invalid_collision_meshes` | – |
| Rigging | `rigging_tools.py` | `detect_excess_bone_influences` | – |

Naming: check functions start with `detect_` and their labels with "Detect "
("Detect N-gons"); results and reports show the label without it ("N-gons").
Tools and fixes start with a verb.

## Adding a tool

```python
from ..core.registry import AgentTools

@AgentTools.register(display_name="My Tool", is_quick_action=True, category="Geometry")
def my_tool() -> str:
    """Description shown to the LLM."""
    return "Result message"
```

## Adding a check

A check reads its meshes from `current()`, takes its settings as keyword arguments
with defaults, and returns issues. Presets override settings by name, and the tool
spec offers them to the LLM.

```python
from ..core.registry import AgentTools
from ..core.results import Issue
from ..core.scope import current

@AgentTools.register_check(
    display_name="Detect My Problem",
    category="Geometry",
    why="One sentence an artist understands: what breaks in engine if this is wrong.",
    severity="WARNING",
)
def detect_my_problem(limit: int = 10) -> list:
    """Description shown to the LLM."""
    return [Issue(obj.name, "What's wrong", value="measured", target="expected")
            for obj in current().meshes if too_many(obj, limit)]

@AgentTools.register_fix("detect_my_problem", display_name="Fix My Problem")  # only if always safe
def fix_my_problem(issues, limit: int = 10) -> str:
    ...
    return "Fixed N things"
```

Put it in the matching `tools/<area>_tools.py` (a new module also goes in `MODULES`
in `tools/__init__.py`), add it to a preset, add a test in
`tests/test_<area>_tools.py`, and update the LLM golden file (see Tests).

## Adding an LLM provider

A provider decides only how to build the HTTP request and how to read the reply.
Sending the request (`core/llm/worker.py`, in a separate process), running the tool
the LLM picks (`core/dispatch.py`) and the UI are shared.

```python
# core/llm/myprovider.py
from ..registry import ToolSpec
from .base import HttpRequest, LLMClient, LLMReply, ToolCall

class MyProviderClient(LLMClient):
    label = "My Provider"
    default_model = "my-model-1"

    def build_request(self, prompt: str, tools: list[ToolSpec]) -> HttpRequest:
        # ToolSpec.parameters is standard JSON Schema; convert if the provider needs to.
        ...

    def parse_response(self, data: dict) -> LLMReply:
        # Return LLMReply(tool_call=ToolCall(name, args)) or LLMReply(text=...).
        ...
```

Then add it to `PROVIDERS` in `core/llm/__init__.py`. It appears in the provider
dropdown in Preferences; nothing else changes. Add request and reply tests next to
the Gemini ones in `tests/test_llm.py`.

## Presets

A preset is a JSON file choosing checks, severities and settings:

```json
{
  "id": "acme",
  "name": "Acme Studio",
  "description": "Our outsourcing spec",
  "checks": {
    "detect_unapplied_transforms": {"severity": "ERROR"},
    "detect_over_triangle_budget": {"severity": "WARNING", "max_tris": 15000},
    "detect_missing_name_prefix": {"severity": "WARNING", "prefix": "SM_"}
  }
}
```

Built-in presets live in `vexa/presets/`. Teams can point **Preferences → Team
presets folder** at a shared folder of their own. An unknown setting name is
reported as an error rather than ignored.

## State

- **Per file** (saved in the `.blend`, on the scene): target, scope, checks turned off.
- **Per session** (window manager, or module variables): results list, Ask Vexa
  prompt and response, expanded Tools categories, the running quick action.

## Tests

```bash
# with Blender
blender -b --factory-startup -P tests/run_all.py

# or with the bpy module (pip install bpy, matching Python version)
python tests/run_all.py
```

Each `tests/test_*.py` file also runs on its own. `run_all.py` exits non-zero on
failure, and CI runs it on every push (see `.github/workflows/ci.yml`).

`tests/golden/gemini_function_declarations.json` pins exactly what Gemini is
offered. After adding, renaming or changing a tool on purpose, regenerate it and
review the diff:

```bash
blender -b --factory-startup -P tests/test_llm.py -- --update-golden
```

## Releases

Push a tag like `v0.5.0` and `.github/workflows/release.yml` builds `vexa.zip` and
attaches it to a GitHub release. The website links to
`releases/latest/download/vexa.zip`, so it always serves the newest release.
