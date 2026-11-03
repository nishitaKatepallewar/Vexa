"""Vexa's sidebar UI.

Layout (top to bottom):
  Vexa                 target preset, scope, one Check button
    Results            after a check: the summary in its header, the results list
    Checks in preset   (collapsed) turn individual checks on/off, see thresholds
    Tools              (collapsed) one-off tools: select hard edges, triangulate…
    Ask Vexa           only when an API key is set
"""

import bpy

from ..core.prefs import has_ai_key
from ..core.presets import get_preset
from ..core.registry import CHECK, AgentTools
from ..core.results import overall_status, plural
from ..core.runner import check_settings
from ..operators.check_ops import STATE, disabled_checks
from ..operators.quick_actions import RUNNING


STATUS_ICON = {"ERROR": "CANCEL", "WARNING": "ERROR", "INFO": "INFO", "PASS": "CHECKMARK"}
OVERALL_TEXT = {
    "ERROR": "Not ready",
    "WARNING": "Ready, with warnings",
    "INFO": "Ready",
    "PASS": "Ready",
}



def _expanded_categories(wm) -> set:
    return {c for c in wm.vexa_expanded_categories.split(",") if c}


def _quick_actions_by_category() -> dict:
    groups = {}
    for tool in AgentTools.all():
        if tool.is_quick_action:
            groups.setdefault(tool.category, []).append(tool)
    return dict(sorted(groups.items()))


def _draw_response(layout, wm) -> None:
    if wm.vexa_last_response:
        box = layout.box()
        for line in wm.vexa_last_response.splitlines():
            box.label(text=line)


def _results_are_stale(scene) -> bool:
    return bool(STATE["preset_id"]) and (STATE["preset_id"] != scene.vexa_preset or STATE["scope"] != scene.vexa_scope)


# ---------------- results list ----------------

class VEXA_UL_results(bpy.types.UIList):
    """One row per check: status, name, measured value, and actions."""

    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        row = layout.row(align=True)
        row.alert = item.status == "ERROR"
        row.label(text=item.title, icon=STATUS_ICON.get(item.status, "DOT"))

        right = row.row(align=True)
        right.alignment = "RIGHT"
        if item.status != "PASS":
            right.label(text=item.summary)
        op = right.operator("vexa.explain_check", text="", icon="QUESTION", emboss=False)
        op.check_id = item.check_id
        if item.has_objects and item.status != "PASS":
            op = right.operator("vexa.select_issues", text="", icon="RESTRICT_SELECT_OFF")
            op.check_id = item.check_id
        if item.fixable:
            op = right.operator("vexa.fix_check", text="", icon="TOOL_SETTINGS")
            op.check_id = item.check_id

    def filter_items(self, context, data, propname):
        # Problems first (errors, then warnings, info), passes at the bottom.
        items = getattr(data, propname)
        order = {"ERROR": 0, "WARNING": 1, "INFO": 2, "PASS": 3}
        ranked = sorted(range(len(items)), key=lambda i: (order.get(items[i].status, 4), i))
        new_order = [0] * len(items)
        for new_pos, old_idx in enumerate(ranked):
            new_order[old_idx] = new_pos
        return [], new_order


# ---------------- panels ----------------

class VexaMainPanel(bpy.types.Panel):
    """Vexa: check assets against a target preset."""

    bl_label = "Vexa"
    bl_idname = "VEXA_PT_main_panel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Vexa"

    def draw(self, context):
        layout = self.layout
        scene = context.scene

        col = layout.column(align=True)
        col.label(text="Target")
        col.prop(scene, "vexa_preset", text="")
        layout.row(align=True).prop(scene, "vexa_scope", expand=True)

        big = layout.row()
        big.scale_y = 1.6
        big.operator("vexa.run_checks", text="Check Assets", icon="PLAY")


def _has_results(context) -> bool:
    # STATE is empty after a restart or re-enable, even if Blender kept the old list.
    return context.window_manager.vexa_has_run and bool(STATE["preset_id"])


def _summary(results) -> str:
    status = overall_status(results)
    errors = sum(1 for r in results if r.status == "ERROR")
    warnings = sum(1 for r in results if r.status == "WARNING")
    return f"{OVERALL_TEXT[status]} · {plural(errors, 'error')} · {plural(warnings, 'warning')}"


class VEXA_PT_results(bpy.types.Panel):
    """The last check's results. Collapsible; the header keeps the summary visible."""

    bl_label = ""
    bl_idname = "VEXA_PT_results"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Vexa"
    bl_parent_id = "VEXA_PT_main_panel"
    bl_order = 0

    @classmethod
    def poll(cls, context):
        return _has_results(context)

    def draw_header(self, context):
        status = overall_status(STATE["results"])
        row = self.layout.row()
        row.alert = status == "ERROR"
        row.label(text=_summary(STATE["results"]), icon=STATUS_ICON[status])

    def draw(self, context):
        layout = self.layout
        wm = context.window_manager
        results = STATE["results"]

        if _results_are_stale(context.scene):
            layout.label(text="Target or scope changed. Check again to update.", icon="FILE_REFRESH")

        layout.template_list(
            "VEXA_UL_results", "", wm, "vexa_results", wm, "vexa_results_index",
            rows=min(max(len(results), 3), 10),
        )

        row = layout.row(align=True)
        row.operator("vexa.fix_all", text="Fix All Safe Issues", icon="TOOL_SETTINGS")
        row.operator("vexa.export_report", text="", icon="EXPORT")


class VEXA_PT_preset_checks(bpy.types.Panel):
    bl_label = "Checks in This Target"
    bl_idname = "VEXA_PT_preset_checks"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Vexa"
    bl_parent_id = "VEXA_PT_main_panel"
    bl_order = 1
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        layout = self.layout
        scene = context.scene
        preset = get_preset(scene.vexa_preset)
        if not preset:
            layout.label(text="No target selected")
            return

        if preset.description:
            layout.label(text=preset.description)
        if preset.source:
            op = layout.operator("wm.url_open", text="Open source requirements", icon="URL")
            op.url = preset.source

        off = disabled_checks(scene)
        col = layout.column(align=True)
        for check_id in preset.checks:
            check = AgentTools.get(check_id, kind=CHECK)
            if not check:
                continue
            row = col.row(align=True)
            enabled = check_id not in off
            op = row.operator("vexa.toggle_check", text="", icon="CHECKBOX_HLT" if enabled else "CHECKBOX_DEHLT",
                              emboss=False)
            op.check_id = check_id
            sub = row.row()
            sub.active = enabled
            sub.label(text=check.display_name)
            try:
                params = check_settings(check_id, preset.settings(check_id))
            except ValueError:
                params = {}
            detail = ", ".join(f"{k.replace('_', ' ')} {v}" for k, v in params.items() if k != "pattern")
            sub.label(text=(preset.severity(check_id).title() + (f" · {detail}" if detail else "")))

        layout.operator("vexa.reload_presets", icon="FILE_REFRESH")


class VEXA_PT_tools(bpy.types.Panel):
    bl_label = "Tools"
    bl_idname = "VEXA_PT_tools"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Vexa"
    bl_parent_id = "VEXA_PT_main_panel"
    bl_order = 2
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        layout = self.layout
        wm = context.window_manager
        expanded_categories = _expanded_categories(wm)

        for cat, category_tools in _quick_actions_by_category().items():
            expanded = cat in expanded_categories
            box = layout.box()
            row = box.row(align=True)
            op = row.operator("vexa.toggle_category", text="", emboss=False,
                              icon="DOWNARROW_HLT" if expanded else "RIGHTARROW")
            op.category = cat
            row.label(text=cat)
            if expanded:
                for tool in category_tools:
                    loading = RUNNING["tool"] == tool.name
                    r = box.row(align=True)
                    op = r.operator("vexa.quick_action", text="", icon="TIME" if loading else "PLAY", emboss=False)
                    op.tool_name = tool.name
                    r.label(text=tool.display_name)

        _draw_response(layout, wm)


class VEXA_PT_ai(bpy.types.Panel):
    bl_label = "Ask Vexa"
    bl_idname = "VEXA_PT_ai"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Vexa"
    bl_parent_id = "VEXA_PT_main_panel"
    bl_order = 3
    bl_options = {"DEFAULT_CLOSED"}

    @classmethod
    def poll(cls, context):
        return has_ai_key(context)

    def draw(self, context):
        layout = self.layout
        wm = context.window_manager
        row = layout.row(align=True)
        row.prop(wm, "vexa_prompt", text="")
        row.operator("vexa.execute_prompt", text="", icon="PLAY")
        _draw_response(layout, wm)


class VexaToggleCategory(bpy.types.Operator):
    """Toggles a category expansion state."""

    bl_idname = "vexa.toggle_category"
    bl_label = "Toggle Category"

    category: bpy.props.StringProperty(name="Category", default="")

    def execute(self, context):
        wm = context.window_manager
        expanded = _expanded_categories(wm)
        expanded.symmetric_difference_update({self.category})
        wm.vexa_expanded_categories = ",".join(sorted(expanded))
        return {"FINISHED"}


PANEL_CLASSES = (VEXA_UL_results, VexaMainPanel, VEXA_PT_results, VEXA_PT_preset_checks, VEXA_PT_tools, VEXA_PT_ai)
