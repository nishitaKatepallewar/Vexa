"""Vexa's sidebar UI.

Layout (top to bottom):
  Vexa                 target preset, scope, one Check button, results list
    Checks in preset   (collapsed) turn individual checks on/off, see thresholds
    Tools              (collapsed) one-off tools: select hard edges, triangulate…
    Ask Vexa           only when a Gemini key is set
"""

import bpy

from ..core.prefs import has_ai_key
from ..core.presets import get_preset
from ..core.registry import CHECK, AgentTools
from ..core.results import overall_status
from ..core.runner import check_settings
from ..operators.check_ops import STATE, disabled_checks

_CACHED_TOOLS_BY_CATEGORY = None
_CACHED_CATEGORIES = None

STATUS_ICON = {"ERROR": "CANCEL", "WARNING": "ERROR", "INFO": "INFO", "PASS": "CHECKMARK"}
OVERALL_TEXT = {
    "ERROR": "Not ready",
    "WARNING": "Ready, with warnings",
    "INFO": "Ready",
    "PASS": "Ready",
}


def _reset_tool_cache():
    """Resets the tool cache. Call this when tools are re-registered."""
    global _CACHED_TOOLS_BY_CATEGORY, _CACHED_CATEGORIES
    _CACHED_TOOLS_BY_CATEGORY = None
    _CACHED_CATEGORIES = None


def _get_tools_by_category():
    """Returns cached tools grouped by category."""
    global _CACHED_TOOLS_BY_CATEGORY, _CACHED_CATEGORIES
    if _CACHED_TOOLS_BY_CATEGORY is None:
        _CACHED_TOOLS_BY_CATEGORY = {}
        for tool in AgentTools.all():
            _CACHED_TOOLS_BY_CATEGORY.setdefault(tool.category, []).append(tool)
        _CACHED_CATEGORIES = sorted(_CACHED_TOOLS_BY_CATEGORY)
    return _CACHED_TOOLS_BY_CATEGORY, _CACHED_CATEGORIES


def _get_expansion_prop(category: str) -> str:
    return f"vexa_{category.lower().replace(' ', '_')}_expanded"


def _is_expanded(scene: bpy.types.Scene, category: str) -> bool:
    return scene.get(_get_expansion_prop(category), False)


def _plural(n: int, word: str) -> str:
    return f"{n} {word}" + ("" if n == 1 else "s")


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
        wm = context.window_manager

        col = layout.column(align=True)
        col.label(text="Target")
        col.prop(scene, "vexa_preset", text="")
        layout.row(align=True).prop(scene, "vexa_scope", expand=True)

        big = layout.row()
        big.scale_y = 1.6
        big.operator("vexa.run_checks", text="Check Assets", icon="PLAY")

        # STATE is empty after a restart or re-enable, even if Blender kept the old list.
        if not wm.vexa_has_run or not STATE["preset_id"]:
            box = layout.box()
            box.label(text="Pick a target, select your meshes,", icon="INFO")
            box.label(text="then click Check Assets.")
            return

        results = STATE["results"]
        status = overall_status(results)
        counts = {s: sum(1 for r in results if r.status == s) for s in ("ERROR", "WARNING")}

        box = layout.box()
        head = box.row()
        head.alert = status == "ERROR"
        head.label(
            text=f"{OVERALL_TEXT[status]} · {_plural(counts['ERROR'], 'error')} · {_plural(counts['WARNING'], 'warning')}",
            icon=STATUS_ICON[status],
        )
        if _results_are_stale(scene):
            box.label(text="Target or scope changed. Check again to update.", icon="FILE_REFRESH")

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
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        layout = self.layout
        scene = context.scene
        tools_by_cat, categories = _get_tools_by_category()

        for cat in categories:
            category_tools = [t for t in tools_by_cat.get(cat, []) if t.is_quick_action]
            if not category_tools:
                continue
            expanded = _is_expanded(scene, cat)
            box = layout.box()
            row = box.row(align=True)
            op = row.operator("vexa.toggle_category", text="", emboss=False,
                              icon="DOWNARROW_HLT" if expanded else "RIGHTARROW")
            op.category = cat
            row.label(text=cat)
            if expanded:
                for tool in category_tools:
                    loading = scene.get("vexa_is_loading", False) and scene.get("vexa_loading_tool", "") == tool.name
                    r = box.row(align=True)
                    op = r.operator("vexa.quick_action", text="", icon="TIME" if loading else "PLAY", emboss=False)
                    op.tool_name = tool.name
                    r.label(text=tool.display_name)

        response = scene.get("vexa_last_response", "")
        if response:
            box = layout.box()
            for line in str(response).splitlines() or [""]:
                box.label(text=line)


class VEXA_PT_ai(bpy.types.Panel):
    bl_label = "Ask Vexa"
    bl_idname = "VEXA_PT_ai"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Vexa"
    bl_parent_id = "VEXA_PT_main_panel"
    bl_options = {"DEFAULT_CLOSED"}

    @classmethod
    def poll(cls, context):
        return has_ai_key(context)

    def draw(self, context):
        layout = self.layout
        scene = context.scene
        row = layout.row(align=True)
        row.prop(scene, "vexa_prompt", text="")
        row.operator("vexa.execute_prompt", text="", icon="PLAY")
        response = scene.get("vexa_last_response", "")
        if response:
            box = layout.box()
            for line in str(response).splitlines() or [""]:
                box.label(text=line)


class VexaToggleCategory(bpy.types.Operator):
    """Toggles a category expansion state."""

    bl_idname = "vexa.toggle_category"
    bl_label = "Toggle Category"

    category: bpy.props.StringProperty(name="Category", default="")

    def execute(self, context):
        scene = context.scene
        prop = _get_expansion_prop(self.category)
        scene[prop] = not scene.get(prop, False)
        return {"FINISHED"}


PANEL_CLASSES = (VEXA_UL_results, VexaMainPanel, VEXA_PT_preset_checks, VEXA_PT_tools, VEXA_PT_ai)
