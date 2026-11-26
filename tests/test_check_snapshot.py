"""Snapshot of what every check and fix reports today.

Runs every check (with default and stricter settings) and every fix on a set of
scenes, and compares the results with tests/golden/check_results.json: status,
summary, each issue's object, message, value, target, selected elements and why the
fix leaves it (if it does), and what each fix changed. Refactors must reproduce it exactly.

If you change a check's behaviour on purpose, regenerate it and review the diff:

    python tests/test_check_snapshot.py --update-golden
    blender -b --factory-startup -P tests/test_check_snapshot.py -- --update-golden
"""

import json
import os
import sys

# Repo root first, so tests always import this checkout's vexa (not an installed copy).
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import bpy  # noqa: E402
import bmesh  # noqa: E402  (after bpy: the pip bpy module provides bmesh)
from mathutils import Matrix  # noqa: E402

from helpers import cube, fresh, mesh_from, run, main, test  # noqa: E402
from vexa.core import runner  # noqa: E402
from vexa.core.registry import CHECK, AgentTools  # noqa: E402
from vexa.core.scope import build_scope  # noqa: E402

GOLDEN = os.path.join(os.path.dirname(os.path.abspath(__file__)), "golden", "check_results.json")

# Stricter settings, so code paths that are off by default are covered too.
STRICT = {
    "detect_nonplanar_faces": {"threshold_deg": 0.0001},
    "detect_over_triangle_budget": {"max_tris": 50},
    "detect_unapplied_transforms": {"check_rotation": False, "check_location": True},
    "detect_off_center_pivots": {"tolerance_m": 0.5},
    "detect_wrong_unit_scale": {"scale_length": 0.01, "length_unit": "CENTIMETERS", "rotation_unit": "RADIANS"},
    "detect_missing_lightmap_uvs": {"channel": 0},
    "detect_invalid_texture_sizes": {"power_of_two": False, "max_size": 512},
    "detect_invalid_name_characters": {"pattern": "^[A-Z][A-Za-z0-9]+$"},
    "detect_missing_name_prefix": {"prefix": "SK_"},
    "detect_excess_bone_influences": {"max_influences": 2},
    "detect_unwanted_objects": {"allowed_types": ["MESH", "EMPTY"]},
    "detect_extra_uv_maps": {"max_uv_maps": 2},
    "detect_flipped_uvs": {"allow_overlapping": False},
    "detect_unapplied_modifiers": {"ignore": []},
    "detect_over_vertex_budget": {"max_verts": 30},
    "detect_wrong_texture_format": {"formats": ["JPEG", "TGA"]},
}


# ---------- scenes ----------

def _flip_faces(obj, indices):
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bm.faces.ensure_lookup_table()
    bmesh.ops.reverse_faces(bm, faces=[bm.faces[i] for i in indices])
    bm.to_mesh(obj.data)
    bm.free()


def _image_node(mat, image):
    if mat.node_tree is None:  # Blender 4.x; 5.x materials always have nodes
        mat.use_nodes = True
    node = mat.node_tree.nodes.new("ShaderNodeTexImage")
    node.image = image
    return node


def scene_clean():
    """A finished asset: triangulated, at the origin, cm units, one UV map, collision."""
    fresh()
    units = bpy.context.scene.unit_settings
    units.system, units.scale_length, units.length_unit = "METRIC", 0.01, "CENTIMETERS"
    crate = cube("SM_Crate")
    crate.data.materials.append(bpy.data.materials.new("M_Crate"))
    bm = bmesh.new()
    bm.from_mesh(crate.data)
    bmesh.ops.triangulate(bm, faces=bm.faces[:])
    bm.to_mesh(crate.data)
    bm.free()
    cube("UCX_SM_Crate_01", size=2.1)


def scene_primitives():
    """Blender's primitives as added, with their default names and UVs.

    No UV sphere: Blender builds it with its faces in a different order each time.
    """
    fresh()
    adds = [bpy.ops.mesh.primitive_plane_add, bpy.ops.mesh.primitive_cube_add,
            bpy.ops.mesh.primitive_circle_add, bpy.ops.mesh.primitive_ico_sphere_add,
            bpy.ops.mesh.primitive_cylinder_add, bpy.ops.mesh.primitive_cone_add,
            bpy.ops.mesh.primitive_torus_add, bpy.ops.mesh.primitive_grid_add,
            bpy.ops.mesh.primitive_monkey_add]
    for i, add in enumerate(adds):
        add(location=(i * 4, 0, 0))


def scene_broken():
    """One of almost everything that can be wrong."""
    fresh()
    bpy.context.scene.unit_settings.system_rotation = "RADIANS"
    # Geometry
    mesh_from("SM_Ngon", [(0, 0, 0), (1, 0, 0), (1.5, 1, 0), (0.5, 1.5, 0), (-0.5, 1, 0)], [(0, 1, 2, 3, 4)])
    mesh_from("SM_Bent", [(3, 0, 0), (4, 0, 0), (4, 1, 0.3), (3, 1, 0)], [(0, 1, 2, 3)])
    flipped = cube("SM_Flipped", loc=(6, 0, 0))
    _flip_faces(flipped, [1, 4])
    holed = cube("SM_Holed", loc=(9, 0, 0))
    bm = bmesh.new()
    bm.from_mesh(holed.data)
    bm.faces.ensure_lookup_table()
    bmesh.ops.delete(bm, geom=[bm.faces[5]], context="FACES_ONLY")
    bm.to_mesh(holed.data)
    bm.free()
    cube("SM_OverlapA", loc=(12, 0, 0))
    cube("SM_OverlapB", loc=(12.5, 0.5, 0))
    # Transforms
    t = cube("SM_Transformed", loc=(15, 2, 1))
    t.rotation_euler = (0.3, 0, 0.5)
    t.scale = (2, 2, 1)
    cube("SM_Mirrored", loc=(18, 0, 0)).scale = (-1, 1, 1)
    pivot = cube("SM_OffPivot", loc=(21, 0, 0))
    pivot.data.transform(Matrix.Translation((0, 0, 3)))
    # UVs and mesh data
    uvs = cube("SM_UVs", loc=(24, 0, 0))
    uvs.data.uv_layers.new(name="Lightmap")
    uvs.data.uv_layers.new(name="Spare")
    uvs.data.color_attributes.new("Col", "FLOAT_COLOR", "POINT")
    layer = uvs.data.uv_layers[0]
    for loop in uvs.data.polygons[0].loop_indices:  # mirror one face's UVs in place
        u, v = layer.data[loop].uv
        layer.data[loop].uv = (1.0 - u, v)
    nouv = cube("SM_NoUV", loc=(27, 0, 0))
    nouv.data.uv_layers.remove(nouv.data.uv_layers[0])
    mod = cube("SM_Modified", loc=(30, 0, 0))
    mod.modifiers.new("Bevel", "BEVEL")
    mod.modifiers.new("Rig", "ARMATURE")
    # Materials and textures
    mat = bpy.data.materials.new("M_Textured")
    textured = cube("SM_Textured", loc=(33, 0, 0))
    textured.data.materials.append(mat)
    textured.data.materials.append(None)
    textured.data.materials.append(bpy.data.materials.new("M_Spare"))
    missing = bpy.data.images.new("T_Gone", 4, 4)
    missing.source, missing.filepath = "FILE", "/nonexistent/T_Gone.png"
    _image_node(mat, missing)
    jpg = bpy.data.images.new("T_Wrong", 4, 4)
    jpg.source, jpg.filepath = "FILE", "//textures/T_Wrong.jpg"
    _image_node(mat, jpg)
    normal = bpy.data.images.new("T_Normal_N", 1000, 1000)
    normal.colorspace_settings.name = "sRGB"
    normal_node = _image_node(mat, normal)
    nt = mat.node_tree
    nmap = nt.nodes.new("ShaderNodeNormalMap")
    nt.links.new(normal_node.outputs["Color"], nmap.inputs["Color"])
    bsdf = next((n for n in nt.nodes if n.type == "BSDF_PRINCIPLED"), None)
    if bsdf:
        nt.links.new(nmap.outputs["Normal"], bsdf.inputs["Normal"])
    bpy.data.materials.new("M_Orphan")
    # Naming and collision
    cube("Cube.001", loc=(36, 0, 0))
    cube("SM_Bad Name!", loc=(39, 0, 0))
    cube("UCX_SM_Nobody_01", loc=(42, 0, 0))
    concave = mesh_from("UCX_SM_Ngon_01", [(0, 0, 0), (2, 0, 0), (1, 0.5, 0), (2, 2, 0), (0, 2, 0)],
                        [(0, 1, 2, 3, 4)])
    concave.location = (45, 0, 0)
    # Other objects
    bpy.ops.object.camera_add(location=(0, -10, 0))
    bpy.ops.object.light_add(type="POINT", location=(0, 0, 10))
    bpy.ops.object.empty_add(location=(48, 0, 0))
    bpy.context.active_object.name = "SOCKET_Handle"
    bpy.ops.object.empty_add(location=(51, 0, 0))


def scene_rigged():
    """A skinned mesh with too many bone influences on some vertices."""
    fresh()
    arm_data = bpy.data.armatures.new("Rig")
    rig = bpy.data.objects.new("SK_Rig", arm_data)
    bpy.context.scene.collection.objects.link(rig)
    bpy.context.view_layer.objects.active = rig
    bpy.ops.object.mode_set(mode="EDIT")
    for i in range(6):
        bone = arm_data.edit_bones.new(f"B{i}")
        bone.head, bone.tail = (0, 0, i), (0, 0, i + 1)
    bpy.ops.object.mode_set(mode="OBJECT")
    body = cube("SK_Body")
    body.parent = rig
    body.modifiers.new("Armature", "ARMATURE").object = rig
    for i in range(6):
        vg = body.vertex_groups.new(name=f"B{i}")
        vg.add(list(range(i + 1)), 1.0 / (i + 1), "REPLACE")


SCENES = {"clean": scene_clean, "primitives": scene_primitives, "broken": scene_broken, "rigged": scene_rigged}


# ---------- recording ----------

def _ranges(indices) -> str:
    """[0, 1, 2, 5, 7, 8] -> "0-2,5,7-8", so the file stays small and readable."""
    out, run_start, prev = [], None, None
    for i in sorted(indices):
        if run_start is None:
            run_start = prev = i
        elif i == prev + 1:
            prev = i
        else:
            out.append(f"{run_start}-{prev}" if prev > run_start else str(run_start))
            run_start = prev = i
    if run_start is not None:
        out.append(f"{run_start}-{prev}" if prev > run_start else str(run_start))
    return ",".join(out)


def _result(res) -> dict:
    return {
        "status": res.status,
        "summary": res.summary,
        "issues": [[i.object_name, i.message, i.value, i.target, i.element, _ranges(i.indices)]
                   + ([i.no_fix] if i.no_fix else []) for i in res.issues],
    }


def _scene_state() -> dict:
    """What a fix can change, per object."""
    state = {}
    for obj in sorted(bpy.context.scene.objects, key=lambda o: o.name):
        entry = {"type": obj.type, "location": [round(v, 4) for v in obj.location],
                 "rotation": [round(v, 4) for v in obj.rotation_euler], "scale": [round(v, 4) for v in obj.scale]}
        if obj.type == "MESH":
            me = obj.data
            entry.update(verts=len(me.vertices), faces=len(me.polygons),
                         face_sizes=sorted(len(p.vertices) for p in me.polygons),
                         normals_z=round(sum(p.normal.z * p.area for p in me.polygons), 4),
                         uv_maps=[layer.name for layer in me.uv_layers],
                         colors=[a.name for a in me.color_attributes],
                         materials=[m.name if m else None for m in me.materials])
        state[obj.name] = entry
    units = bpy.context.scene.unit_settings
    state["<units>"] = [round(units.scale_length, 6), units.length_unit, units.system_rotation]
    state["<materials>"] = sorted(m.name for m in bpy.data.materials)
    state["<images>"] = sorted((i.name, i.colorspace_settings.name) for i in bpy.data.images)
    return state


def snapshot() -> dict:
    out = {}
    checks = [entry.name for entry in AgentTools.all(CHECK)]
    for scene_name, build in SCENES.items():
        scene_out = {}
        build()
        for name in checks:
            scene_out[name] = _result(run(name)[1])
            if name in STRICT:
                scene_out[name + " (strict)"] = _result(run(name, **STRICT[name])[1])
        out[scene_name] = scene_out
    # Fixes: each one on a fresh broken scene, so they don't affect each other.
    fixes = {}
    for name in checks:
        if AgentTools.fix_for(name) is None:
            continue
        for label, params in (("default", {}), ("strict", STRICT.get(name))):
            if params is None:
                continue
            scene_broken()
            before = _scene_state()
            _, res = run(name, **params)
            message = runner.apply_fix(res, params, build_scope(list(bpy.context.scene.objects)))
            after = _scene_state()
            changed = {key: after.get(key) for key in sorted(set(before) | set(after))
                       if before.get(key) != after.get(key)}  # None: removed
            fixes[f"{name} ({label})"] = {"message": message, "after": _result(run(name, **params)[1]),
                                         "changed": changed}
    out["fixes"] = fixes
    return out


def _short(value) -> str:
    text = json.dumps(value)
    return text if len(text) <= 300 else text[:300] + " …"


def _diff(expected, actual, path=""):
    """The first difference between two snapshots, as readable text."""
    if isinstance(expected, list) and isinstance(actual, list):
        for i, (e, a) in enumerate(zip(expected, actual)):
            d = _diff(e, a, f"{path}[{i}]")
            if d:
                return d
        if len(expected) != len(actual):
            return f"{path}: expected {len(expected)} items, got {len(actual)}"
        return ""
    if isinstance(expected, dict) and isinstance(actual, dict):
        for key in list(expected) + [k for k in actual if k not in expected]:
            if key not in actual:
                return f"{path}/{key}: missing"
            if key not in expected:
                return f"{path}/{key}: new"
            d = _diff(expected[key], actual[key], f"{path}/{key}")
            if d:
                return d
        return ""
    if expected != actual:
        return f"{path}:\n  expected {_short(expected)}\n  actual   {_short(actual)}"
    return ""


@test
def every_check_and_fix_matches_the_snapshot():
    with open(GOLDEN, encoding="utf-8") as f:
        expected = json.load(f)
    actual = json.loads(json.dumps(snapshot()))  # tuples become lists, as in the file
    difference = _diff(expected, actual)
    assert not difference, "check results changed (see module docstring)\n" + difference


def update_golden() -> None:
    """Writes one line per check or fix, so a change shows up as a one-line diff."""
    data = snapshot()
    lines = ["{"]
    for i, (group, entries) in enumerate(data.items()):
        lines.append(f"  {json.dumps(group)}: {{")
        items = [f"    {json.dumps(key)}: {json.dumps(value, ensure_ascii=False)}" for key, value in entries.items()]
        lines.append(",\n".join(items))
        lines.append("  }" + ("," if i < len(data) - 1 else ""))
    lines.append("}")
    with open(GOLDEN, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(f"Wrote {GOLDEN}")


if __name__ == "__main__":
    if "--update-golden" in sys.argv:
        update_golden()
        from helpers import finish
        finish(0)
    main(globals())
