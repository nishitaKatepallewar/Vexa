"""Operators behind the check panel: run, select, fix, explain, toggle, report."""

import textwrap

import bpy
from bpy_extras.io_utils import ExportHelper

from ..core import runner
from ..core.prefs import get_prefs
from ..core.presets import get_preset, load_presets
from ..core.registry import CHECK, AgentTools
from ..core.results import plural
from ..core.scope import build_scope
from ..core.selection import select_result
from .feedback import redraw_3d_views

# The last run, kept in memory (not saved in the .blend). It holds names, never
# references to Blender data (see the API docs, "Troubleshooting Errors & Crashes").
STATE = {"preset_id": "", "scope": "", "results": []}


# ---------- helpers ----------

def scope_objects(context, scope: str) -> list:
    if scope == "COLLECTION":
        objs = list(context.view_layer.active_layer_collection.collection.all_objects)
    elif scope == "SCENE":
        objs = list(context.scene.objects)
    else:
        objs = list(context.selected_objects)
    return [o for o in objs if o.type == "MESH"]


def disabled_checks(scene) -> set:
    return {c for c in scene.vexa_disabled_checks.split(",") if c}


def ensure_object_mode(context) -> None:
    # Edit Mode keeps its own copy of mesh data (see the API docs, "Modes and Mesh Access").
    if context.object and context.object.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")


def find_result(check_name: str):
    for result in STATE["results"]:
        if result.check_id == check_name:
            return result
    return None


def sync_ui(context) -> None:
    wm = context.window_manager
    wm.vexa_results.clear()
    for result in STATE["results"]:
        item = wm.vexa_results.add()
        item.check_id = result.check_id
        item.title = result.title
        item.status = result.status
        item.summary = result.summary
        item.fixable = result.fixable
        item.has_objects = bool(result.objects)
    wm.vexa_has_run = bool(STATE["preset_id"])
    redraw_3d_views(context)


def rerun(context) -> None:
    preset = get_preset(STATE["preset_id"])
    if not preset:
        return
    objs = scope_objects(context, STATE["scope"])
    STATE["results"] = runner.run_preset(preset, objs, context.scene, disabled_checks(context.scene))
    sync_ui(context)


def reload_presets(context=None) -> None:
    prefs = get_prefs(context)
    extra = [bpy.path.abspath(prefs.presets_dir)] if prefs and prefs.presets_dir else []
    load_presets(extra)


def fix_one(context, check_name: str) -> str:
    result = find_result(check_name)
    preset = get_preset(STATE["preset_id"])
    if not (result and preset and result.fixable):
        return "Nothing to fix"
    scope = build_scope(scope_objects(context, STATE["scope"]), context.scene)
    message = runner.apply_fix(result, preset.settings(check_name), scope)
    rerun(context)
    return message


# ---------- operators ----------

class VEXA_OT_run_checks(bpy.types.Operator):
    """Check the assets in scope against the selected target"""

    bl_idname = "vexa.run_checks"
    bl_label = "Check Assets"
    bl_options = {"REGISTER"}

    def execute(self, context):
        scene = context.scene
        preset = get_preset(scene.vexa_preset)
        if not preset:
            self.report({"ERROR"}, "Pick a target first")
            return {"CANCELLED"}
        objs = scope_objects(context, scene.vexa_scope)
        if not objs:
            where = {
                "SELECTED": "Select one or more meshes",
                "COLLECTION": "The active collection has no meshes",
                "SCENE": "The scene has no meshes",
            }[scene.vexa_scope]
            self.report({"WARNING"}, where)
            return {"CANCELLED"}
        ensure_object_mode(context)
        STATE.update(preset_id=preset.id, scope=scene.vexa_scope)
        STATE["results"] = runner.run_preset(preset, objs, scene, disabled_checks(scene))
        sync_ui(context)
        errors = sum(1 for r in STATE["results"] if r.status == "ERROR")
        warnings = sum(1 for r in STATE["results"] if r.status == "WARNING")
        self.report({"INFO"}, f"{preset.name}: {plural(errors, 'error')}, {plural(warnings, 'warning')}")
        return {"FINISHED"}


class VEXA_OT_select_issues(bpy.types.Operator):
    """Select the objects (and faces, edges or vertices) this check flagged"""

    bl_idname = "vexa.select_issues"
    bl_label = "Select Problems"
    bl_options = {"REGISTER", "UNDO"}

    check_id: bpy.props.StringProperty()

    def execute(self, context):
        result = find_result(self.check_id)
        if not result or not result.objects:
            self.report({"INFO"}, "Nothing to select")
            return {"CANCELLED"}
        count = select_result(result, context)
        if not count:
            return {"CANCELLED"}
        self.report({"INFO"}, f"Selected {plural(count, 'object')}")
        return {"FINISHED"}


class VEXA_OT_fix_check(bpy.types.Operator):
    """Apply this check's safe fix, then check again"""

    bl_idname = "vexa.fix_check"
    bl_label = "Fix"
    bl_options = {"REGISTER", "UNDO"}

    check_id: bpy.props.StringProperty()

    @classmethod
    def description(cls, context, properties):
        fix = AgentTools.fix_for(properties.check_id)
        return f"{fix.display_name}, then check again" if fix else cls.__doc__

    def execute(self, context):
        ensure_object_mode(context)
        self.report({"INFO"}, fix_one(context, self.check_id))
        return {"FINISHED"}


class VEXA_OT_fix_all(bpy.types.Operator):
    """Apply every available safe fix in order, checking again after each"""

    bl_idname = "vexa.fix_all"
    bl_label = "Fix All Safe Issues"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return any(r.fixable for r in STATE["results"])

    def execute(self, context):
        ensure_object_mode(context)
        messages = [fix_one(context, name) for name in [r.check_id for r in STATE["results"] if r.fixable]]
        self.report({"INFO"}, "; ".join(m for m in messages if m != "Nothing to fix") or "Nothing to fix")
        return {"FINISHED"}


class VEXA_OT_explain_check(bpy.types.Operator):
    """Why this check matters"""

    bl_idname = "vexa.explain_check"
    bl_label = "Why This Matters"

    check_id: bpy.props.StringProperty()

    @classmethod
    def description(cls, context, properties):
        check = AgentTools.get(properties.check_id, kind=CHECK)
        return check.check.why if check else ""

    def execute(self, context):
        check = AgentTools.get(self.check_id, kind=CHECK)
        result = find_result(self.check_id)
        if not check:
            return {"CANCELLED"}

        def draw(menu, _context):
            col = menu.layout.column(align=True)
            for line in textwrap.wrap(check.check.why, 60):
                col.label(text=line)
            if result and result.issues:
                col.separator()
                for issue in result.issues[:8]:
                    who = f"{issue.object_name}: " if issue.object_name else ""
                    col.label(text=f"• {who}{issue.message}")
                if len(result.issues) > 8:
                    col.label(text=f"…and {len(result.issues) - 8} more")

        context.window_manager.popup_menu(draw, title=check.display_name, icon="QUESTION")
        return {"FINISHED"}


class VEXA_OT_toggle_check(bpy.types.Operator):
    """Turn this check on or off for this file"""

    bl_idname = "vexa.toggle_check"
    bl_label = "Toggle Check"
    bl_options = {"REGISTER", "UNDO"}

    check_id: bpy.props.StringProperty()

    def execute(self, context):
        scene = context.scene
        disabled = disabled_checks(scene)
        disabled.symmetric_difference_update({self.check_id})
        scene.vexa_disabled_checks = ",".join(sorted(disabled))
        if STATE["preset_id"]:
            rerun(context)
        return {"FINISHED"}


class VEXA_OT_export_report(bpy.types.Operator, ExportHelper):
    """Save the last check as a JSON report"""

    bl_idname = "vexa.export_report"
    bl_label = "Export Report"

    filename_ext = ".json"
    filter_glob: bpy.props.StringProperty(default="*.json", options={"HIDDEN"})

    @classmethod
    def poll(cls, context):
        return bool(STATE["results"])

    def execute(self, context):
        preset = get_preset(STATE["preset_id"])
        runner.write_report(self.filepath, preset, STATE["results"], STATE["scope"])
        self.report({"INFO"}, f"Report saved: {self.filepath}")
        return {"FINISHED"}


class VEXA_OT_reload_presets(bpy.types.Operator):
    """Reload preset files (built-in and your team presets folder)"""

    bl_idname = "vexa.reload_presets"
    bl_label = "Reload Presets"

    def execute(self, context):
        reload_presets(context)
        self.report({"INFO"}, "Presets reloaded")
        return {"FINISHED"}


CLASSES = (
    VEXA_OT_run_checks,
    VEXA_OT_select_issues,
    VEXA_OT_fix_check,
    VEXA_OT_fix_all,
    VEXA_OT_explain_check,
    VEXA_OT_toggle_check,
    VEXA_OT_export_report,
    VEXA_OT_reload_presets,
)
