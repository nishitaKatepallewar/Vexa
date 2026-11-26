"""Operators behind the check panel: run, select, fix, explain, toggle, report."""

import os
import pathlib
import textwrap

import bpy
from bpy_extras.io_utils import ExportHelper

from ..core import report, runner
from ..core.prefs import get_prefs
from ..core.presets import get_preset, load_presets
from ..core.registry import CHECK, AgentTools
from ..core.results import plural
from ..core.scope import build_scope
from ..core.selection import select_result
from .feedback import redraw_3d_views

# The last run, kept in memory (not saved in the .blend). It holds names, never
# references to Blender data (see the API docs, "Troubleshooting Errors & Crashes").
# "warning" is set when a fix made another check worse: {"fix": name, "problems": [...]}.
STATE = {"preset_id": "", "scope": "", "results": [], "warning": None}


# ---------- helpers ----------

def scope_objects(context, scope: str) -> list:
    """Every object in scope. Checks look at meshes; a few also look at other objects."""
    if scope == "COLLECTION":
        return list(context.view_layer.active_layer_collection.collection.all_objects)
    if scope == "SCENE":
        return list(context.scene.objects)
    selected = getattr(context, "selected_objects", None)  # missing in timers
    if selected is None:
        selected = [o for o in context.view_layer.objects if o.select_get()]
    return list(selected)


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
        item.fix_safe = result.fix_safe
        item.has_objects = bool(result.objects)
    wm.vexa_has_run = bool(STATE["preset_id"])
    redraw_3d_views(context)


def check_now(context) -> list:
    """Runs the last check's target and scope again on the scene as it is now."""
    preset = get_preset(STATE["preset_id"])
    if not preset:
        return []
    objs = scope_objects(context, STATE["scope"])
    return runner.run_preset(preset, objs, context.scene, disabled_checks(context.scene))


def rerun(context) -> None:
    if not get_preset(STATE["preset_id"]):
        return
    STATE["results"] = check_now(context)
    sync_ui(context)


def reload_presets(context=None) -> None:
    prefs = get_prefs(context)
    extra = [bpy.path.abspath(prefs.presets_dir)] if prefs and prefs.presets_dir else []
    load_presets(extra)


def safe_fixes() -> list:
    """Checks whose fix Fix All runs: something to fix, and the fix is safe."""
    return [r.check_id for r in STATE["results"] if r.fixable and r.fix_safe]


def fixes_to_review() -> list:
    """Checks with a fix the artist must confirm on its own row first."""
    return [r.check_id for r in STATE["results"] if r.fixable and not r.fix_safe]


def confirm_dialog(operator, context, fix):
    """Shows a dialog with the fix's confirm text; the fix runs if the artist clicks it."""
    wm = context.window_manager
    try:
        return wm.invoke_props_dialog(operator, width=460, title=fix.display_name,
                                      confirm_text=fix.display_name)
    except TypeError:  # Blender 4.0 has no title or confirm_text
        return wm.invoke_props_dialog(operator, width=460)


def draw_confirm(layout, fix, objects=()) -> None:
    """The dialog's text: what the fix changes, what it affects, how to undo it."""
    col = layout.column(align=True)
    for line in textwrap.wrap(fix.fix.confirm, 70):
        col.label(text=line)
    if objects:
        col.separator()
        names = ", ".join(objects[:4]) + (f" and {len(objects) - 4} more" if len(objects) > 4 else "")
        col.label(text=f"Changes: {names}", icon="OBJECT_DATA")
    col.separator()
    col.label(text="Ctrl+Z undoes it.", icon="LOOP_BACK")


def fix_one(context, check_name: str, before=None):
    """Fixes one check's issues, checks again, and returns (message, results after).

    The issues come from `before`, results for the scene as it is now. Without it the
    check runs again first: the artist may have edited the scene since the last
    check, and a fix must never act on stale results (e.g. old face numbers).
    """
    preset = get_preset(STATE["preset_id"])
    if not preset:
        return "Nothing to fix", STATE["results"]
    if before is None:
        before = check_now(context)
    result = next((r for r in before if r.check_id == check_name), None)
    if not (result and result.fixable):
        STATE["results"] = before
        sync_ui(context)
        return "Nothing to fix", before
    scope = build_scope(scope_objects(context, STATE["scope"]), context.scene)
    message = runner.apply_fix(result, preset.settings(check_name), scope)
    STATE["results"] = check_now(context)
    worse = runner.new_problems(before, STATE["results"])
    if worse:
        fix = AgentTools.fix_for(check_name)
        STATE["warning"] = {"fix": fix.display_name, "problems": worse}
        message += f". It also caused: {'; '.join(worse)}. Undo it with Ctrl+Z"
    sync_ui(context)
    return message, STATE["results"]


@bpy.app.handlers.persistent
def _after_undo(*_args) -> None:
    """After undoing a fix that caused problems, show results for the restored scene."""
    if STATE["warning"]:
        STATE["warning"] = None
        bpy.app.timers.register(_rerun_from_timer, first_interval=0.0)


def _rerun_from_timer():
    try:
        rerun(bpy.context)
    except Exception:  # noqa: BLE001 - results stay as they were; Check Assets refreshes them
        pass
    return None


def register_handlers() -> None:
    if _after_undo not in bpy.app.handlers.undo_post:
        bpy.app.handlers.undo_post.append(_after_undo)


def unregister_handlers() -> None:
    if _after_undo in bpy.app.handlers.undo_post:
        bpy.app.handlers.undo_post.remove(_after_undo)


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
        if not any(o.type == "MESH" for o in objs):
            where = {
                "SELECTED": "Select one or more meshes",
                "COLLECTION": "The active collection has no meshes",
                "SCENE": "The scene has no meshes",
            }[scene.vexa_scope]
            self.report({"WARNING"}, where)
            return {"CANCELLED"}
        ensure_object_mode(context)
        STATE.update(preset_id=preset.id, scope=scene.vexa_scope, warning=None)
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
    """Apply this check's fix, then check again"""

    bl_idname = "vexa.fix_check"
    bl_label = "Fix"
    bl_options = {"REGISTER", "UNDO"}

    check_id: bpy.props.StringProperty()

    @classmethod
    def description(cls, context, properties):
        fix = AgentTools.fix_for(properties.check_id)
        if not fix:
            return cls.__doc__
        if fix.fix.safe:
            return f"{fix.display_name}, then check again"
        return f"{fix.display_name}: shows what it will change before it runs"

    def invoke(self, context, event):
        fix = AgentTools.fix_for(self.check_id)
        if fix and not fix.fix.safe:
            return confirm_dialog(self, context, fix)
        return self.execute(context)

    def draw(self, context):
        fix = AgentTools.fix_for(self.check_id)
        result = find_result(self.check_id)
        if fix:
            draw_confirm(self.layout, fix, [i.object_name for i in result.issues if i.object_name and not i.no_fix]
                         if result else [])

    def execute(self, context):
        ensure_object_mode(context)
        self.report({"INFO"}, fix_one(context, self.check_id)[0])
        return {"FINISHED"}


class VEXA_OT_fix_all(bpy.types.Operator):
    """Apply every safe fix in order, checking again after each. Fixes that need a look first are left for their own row"""

    bl_idname = "vexa.fix_all"
    bl_label = "Fix All Safe"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return bool(safe_fixes())

    def execute(self, context):
        ensure_object_mode(context)
        results, messages = check_now(context), []
        for name in [r.check_id for r in results if r.fixable and r.fix_safe]:
            message, results = fix_one(context, name, results)
            messages.append(message)
            if STATE["warning"]:  # stop here: one Ctrl+Z undoes this whole Fix All
                STATE["warning"]["undo"] = "Undo Fix All"
                messages.append("Stopped there")
                break
        text = "; ".join(m for m in messages if m != "Nothing to fix") or "Nothing to fix"
        review = fixes_to_review()
        if review:
            text += f". {len(review)} more to review on their own rows"
        self.report({"INFO"}, text)
        return {"FINISHED"}


class VEXA_OT_dismiss_warning(bpy.types.Operator):
    """Keep the fix and hide this message"""

    bl_idname = "vexa.dismiss_warning"
    bl_label = "Keep"

    def execute(self, context):
        STATE["warning"] = None
        redraw_3d_views(context)
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
    """Save the last check as a report: an HTML page to read and share, or JSON data"""

    bl_idname = "vexa.export_report"
    bl_label = "Export Report"

    filename_ext = ".html"
    check_extension = False  # keep .json if the user types it
    filter_glob: bpy.props.StringProperty(default="*.html;*.json", options={"HIDDEN"})
    open_after: bpy.props.BoolProperty(
        name="Open after saving",
        description="Open the HTML report in your web browser",
        default=True,
    )

    @classmethod
    def poll(cls, context):
        return bool(STATE["results"])

    def invoke(self, context, event):
        if not self.filepath:  # next to the .blend file, like Blender's own exporters
            stem = os.path.splitext(bpy.data.filepath)[0] if bpy.data.filepath else "untitled"
            self.filepath = f"{stem}_vexa_report{self.filename_ext}"
        return super().invoke(context, event)

    def execute(self, context):
        path = self.filepath
        if not path.lower().endswith((".html", ".htm", ".json")):
            path += self.filename_ext
        preset = get_preset(STATE["preset_id"])
        report.write_report(path, preset, STATE["results"], STATE["scope"])
        self.report({"INFO"}, f"Report saved: {path}")
        if self.open_after and path.lower().endswith((".html", ".htm")):
            bpy.ops.wm.url_open(url=pathlib.Path(path).resolve().as_uri())
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
    VEXA_OT_dismiss_warning,
    VEXA_OT_explain_check,
    VEXA_OT_toggle_check,
    VEXA_OT_export_report,
    VEXA_OT_reload_presets,
)
