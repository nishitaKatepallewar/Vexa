"""UV checks: UV map present, lightmap channel present and inside 0–1."""

import numpy as np

from ..core.registry import AgentTools
from ..core.results import Issue
from ..core.scope import current


@AgentTools.register_check(
    display_name="Detect Missing UV Maps",
    category="UVs",
    why="A mesh with no UV map can't be textured or lightmapped, and most engines "
        "warn or fail on import.",
    severity="ERROR",
    pass_text="All meshes",
)
def detect_missing_uv_maps() -> list:
    """Finds meshes with no UV map at all."""
    return [Issue(o.name, "No UV map", value="0 UV maps", target="≥ 1")
            for o in current().meshes if len(o.data.uv_layers) == 0]


@AgentTools.register_check(
    display_name="Detect Lightmap UV Issues",
    category="UVs",
    why="Unreal bakes lighting from the second UV channel. If it's missing or spills "
        "outside 0–1, lighting builds fail or bake black and blotchy.",
    severity="ERROR",
    pass_text="Present, in 0–1",
)
def detect_missing_lightmap_uvs(channel: int = 1) -> list:
    """Finds meshes without a lightmap UV channel, or whose lightmap UVs leave 0–1.

    channel: index of the lightmap UV map (Unreal uses 1, the second map).
    """
    issues = []
    for obj in current().meshes:
        layers = obj.data.uv_layers
        if len(layers) <= channel:
            issues.append(Issue(obj.name, f"No lightmap UV channel (UV{channel})",
                                value=f"{len(layers)} UV maps", target=f"≥ {channel + 1}"))
            continue
        uv = np.zeros(len(obj.data.loops) * 2, dtype=np.float32)
        layers[channel].data.foreach_get("uv", uv)
        if uv.size and (uv.min() < -1e-4 or uv.max() > 1 + 1e-4):
            issues.append(Issue(obj.name, f"Lightmap UVs (UV{channel}) outside 0–1",
                                value=f"range {uv.min():.2f}–{uv.max():.2f}", target="0–1"))
    return issues
