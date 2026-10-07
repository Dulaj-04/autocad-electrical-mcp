"""MCP server exposing AutoCAD Electrical floor-drawing tools."""

from __future__ import annotations

import argparse
import json
import logging
import os
from pathlib import Path
from typing import Any, Literal

from mcp.server.fastmcp import FastMCP, Image
from mcp.server.transport_security import TransportSecuritySettings

from . import __version__, export, inspection, planner, template, validate
from .backends import autocad_backend
from .backends.base import BackendError
from .config import Config, safe_name
from .live import LiveSession, RealCom
from .model import Store, sha256_file
from .schematic import Schematic
from .template import VIEWS

logging.getLogger("ezdxf").setLevel(logging.ERROR)  # quiet stderr (stdio transport)

CFG = Config.from_env()
STORE = Store(CFG.workspace)

INSTRUCTIONS = """\
Tools to create, revise, validate and export editable electrical floor drawings
(AutoCAD Electrical workflow). Everything is a DRAFT drawing aid, not engineering approval.

Typical flow: prepare_floor_model (register the architectural DXF/DWG + rooms) ->
plan_devices / propose_lighting_grid / set_circuit_assignment / plan_routes (each returns a
changeset) -> preview_changes -> apply_changes (regenerates the DXF views) ->
validate_drawing -> export_package (DXF/DWG/PNG/PDF + manifest.json).
Reference drawings are never modified; outputs go to the workspace output folder.

LIVE MODE (Windows, drawing open in AutoCAD / AutoCAD Electrical): when the user wants to work
on the open drawing and see changes on screen, use the live_* tools instead: live_connect first,
then live_scan / live_adopt (give existing symbols ids), live_texts (room names and positions),
live_place / live_move / live_delete / live_assign / live_route, live_zoom to show the change,
live_undo to revert one instruction. Each call edits the open drawing immediately; keep steps
small and tell the user what changed. These draw plan-level geometry, not Electrical schematic
components. SCHEMATIC MODE: only when the user asks to work with AutoCAD Electrical schematics, call
live_set_mode('schematic'), then sch_detect / sch_read / sch_probe. Otherwise stay in plan mode.
Check unit_scale_vs_mm from live_connect: reference drawings are in millimetres
even when the header says metres.
Always pass explicit project and floor ids (letters, digits, '_' and '-' only).
"""

mcp = FastMCP("acad-electrical", instructions=INSTRUCTIONS)


def _model(project: str, floor: str, create: bool = False) -> dict[str, Any]:
    return STORE.load(project, floor, create=create)


def _regen_and_record(model: dict[str, Any], overwrite: bool = False) -> list[dict[str, Any]]:
    out_dir = STORE.output_dir(model["project"], model["floor"])
    res = export.generate_dxf_views(model, out_dir, CFG.backend, None, overwrite)
    STORE.save(model)
    return res


# --------------------------------------------------------------------------- inspect
@mcp.tool()
def register_reference(path: str) -> dict[str, Any]:
    """Hash and inventory a reference DXF (or DWG with ODA converter): layers, entity counts,
    blocks, units, extents, layouts and text entities (candidate room labels). Read-only."""
    return inspection.inspect_drawing(path)


@mcp.tool()
def inspect_drawing(project: str, floor: str, view: Literal[
        "architectural", "lighting", "power", "combined"] = "combined") -> dict[str, Any]:
    """Inventory a generated output drawing of a floor (layers, entity counts, device ids)."""
    model = _model(project, floor)
    path = STORE.output_dir(project, floor) / export.view_filename(floor, view, "dxf")
    if not path.exists():
        raise ValueError(f"{path.name} has not been generated yet; run apply_changes or "
                         "generate_views.")
    info = inspection.inspect_drawing(str(path))
    import ezdxf
    info["devices_in_drawing"] = sorted(validate.read_devices(ezdxf.readfile(str(path))))
    info["model_revision"] = model["revision"]
    return info


@mcp.tool()
def list_devices(project: str, floor: str) -> dict[str, Any]:
    """List the logical devices, circuits, routes and rooms of a floor model."""
    m = _model(project, floor)
    return {k: m[k] for k in ("revision", "status", "units", "source", "rooms", "devices",
                              "circuits", "routes")}


# --------------------------------------------------------------------------- prepare
@mcp.tool()
def prepare_floor_model(
    project: str, floor: str, reference_path: str | None = None,
    rooms: list[dict[str, Any]] | None = None, replace_rooms: bool = False,
) -> dict[str, Any]:
    """Create/update the floor model: register the architectural reference (hash + units check)
    and rooms. Each room is {"id","name","bounds":[minx,miny,maxx,maxy]} in drawing units.
    Existing rooms are kept unless replace_rooms=true; differing names are reported, not
    overwritten silently. The reference file itself is never modified."""
    safe_name(project, "project")
    safe_name(floor, "floor")
    model = _model(project, floor, create=True)
    report: dict[str, Any] = {"warnings": [], "room_differences": []}
    if reference_path:
        info = inspection.inspect_drawing(reference_path, max_texts=0)
        model["source"] = {"path": info["path"], "sha256": info["sha256"]}
        model["units"] = info["units"]
        report["warnings"] += info["warnings"]
        report["reference"] = {k: info[k] for k in ("sha256", "units", "extents", "layouts")}
    for r in rooms or []:
        if not {"id", "name", "bounds"} <= set(r) or len(r["bounds"]) != 4:
            raise ValueError("Each room needs id, name and bounds [minx,miny,maxx,maxy]")
        b = [float(v) for v in r["bounds"]]
        if b[0] >= b[2] or b[1] >= b[3]:
            raise ValueError(f"Room {r['id']}: bounds must be [minx,miny,maxx,maxy] with min<max")
        cur = next((x for x in model["rooms"] if x["id"] == r["id"]), None)
        if cur and not replace_rooms:
            if cur["name"] != r["name"] or cur["bounds"] != b:
                report["room_differences"].append(
                    {"id": r["id"], "existing": cur, "supplied": {**r, "bounds": b}})
            continue
        model["rooms"] = [x for x in model["rooms"] if x["id"] != r["id"]]
        model["rooms"].append({"id": r["id"], "name": r["name"], "bounds": b})
    model["rooms"].sort(key=lambda r: r["id"])
    STORE.save(model)
    report.update(project=project, floor=floor, revision=model["revision"],
                  rooms=len(model["rooms"]), model_path=str(STORE.floor_dir(project, floor)))
    return report


@mcp.tool()
def prepare_template(project: str, floor: str, overrides: dict[str, Any]) -> dict[str, Any]:
    """Customise the drawing template. Keys: layers {name:{color,lineweight,description}},
    symbol_size, text_height (drawing units), status, title_block {project,drawn_by,notes[]}.
    Regenerate views afterwards with generate_views."""
    model = _model(project, floor)
    model["template"] = template.merge_template(model["template"], overrides)
    STORE.save(model)
    return {"template": model["template"]}


# --------------------------------------------------------------------------- planning
def _store_cs(cs: dict[str, Any], model: dict[str, Any]) -> dict[str, Any]:
    STORE.save_changeset(cs)
    return planner.describe(cs, model)


@mcp.tool()
def plan_devices(
    project: str, floor: str, devices: list[dict[str, Any]],
    remove_ids: list[str] | None = None, tolerance: float = 0.01,
) -> dict[str, Any]:
    """Propose luminaires, switches, sockets, data, ac, emergency and db devices.
    Each device: {"type","x","y"} plus optional id, rotation, room, circuit, db, note.
    Same-type devices at the same position (within tolerance) are treated as already present,
    so repeating a plan creates no duplicates. Returns a changeset to preview/apply."""
    m = _model(project, floor)
    return _store_cs(planner.plan_devices(m, devices, remove_ids, tolerance), m)


@mcp.tool()
def propose_lighting_grid(
    project: str, floor: str, room_id: str, spacing_x: float, spacing_y: float,
    circuit: str | None = None, margin: float = 0.0,
) -> dict[str, Any]:
    """Propose a regular luminaire grid in a room (placement draft only, no lux calculation)."""
    m = _model(project, floor)
    return _store_cs(planner.propose_lighting_grid(m, room_id, spacing_x, spacing_y,
                                                   circuit, margin), m)


@mcp.tool()
def set_circuit_assignment(
    project: str, floor: str, circuit_id: str, kind: Literal["lighting", "power", "ac"],
    db: str | None = None, device_ids: list[str] | None = None,
) -> dict[str, Any]:
    """Create/update a circuit, bind it to a distribution board and assign devices to it."""
    m = _model(project, floor)
    return _store_cs(planner.set_circuit(m, circuit_id, kind, db, device_ids), m)


@mcp.tool()
def plan_routes(
    project: str, floor: str, circuit_id: str, device_ids: list[str] | None = None
) -> dict[str, Any]:
    """Propose an orthogonal route from the circuit's DB through its devices (nearest-first, or
    in the order given). The route is associated with the circuit/DB in the model; geometric
    crossings imply no connectivity. Draft drawing aid, not cable routing/sizing."""
    m = _model(project, floor)
    return _store_cs(planner.plan_route(m, circuit_id, device_ids), m)


@mcp.tool()
def preview_changes(project: str, floor: str, changeset_id: str) -> dict[str, Any]:
    """Show what a changeset would do (adds/updates/removals, assumptions, conflicts)."""
    m = _model(project, floor)
    return planner.describe(STORE.load_changeset(project, floor, changeset_id), m)


@mcp.tool()
def apply_changes(
    project: str, floor: str, changeset_id: str, overwrite_manual_edits: bool = False
) -> dict[str, Any]:
    """Apply a changeset: guarded by model revision, reference hash and manual-edit detection;
    snapshots the previous revision (undo_last), regenerates all four DXF views and reads them
    back for validation."""
    m = _model(project, floor)
    cs = STORE.load_changeset(project, floor, changeset_id)
    out_dir = STORE.output_dir(project, floor)
    try:
        new, stats = planner.apply_ops(m, cs)
    except planner.Conflict as exc:
        raise ValueError(str(exc)) from exc
    problems = validate.validate_model(new)
    errs = [i for i in problems if i["severity"] == "error"]
    if errs:
        raise ValueError("Changeset rejected, resulting model is invalid: "
                         + "; ".join(i["message"] for i in errs))
    STORE.snapshot(m)
    try:
        files = export.generate_dxf_views(new, out_dir, CFG.backend, None, overwrite_manual_edits)
    except BackendError as exc:
        raise ValueError(str(exc)) from exc
    STORE.save(new)
    STORE.delete_changeset(project, floor, changeset_id)
    report = validate.validate_floor(new, out_dir)
    return {"revision": new["revision"], **stats, "files": [f["dxf"] for f in files],
            "validation": {k: report[k] for k in ("ok", "errors", "warnings", "issues")}}


@mcp.tool()
def undo_last(project: str, floor: str, overwrite_manual_edits: bool = False) -> dict[str, Any]:
    """Restore the model to the revision before the last apply_changes and regenerate views."""
    m = _model(project, floor)
    snap = STORE.last_snapshot(project, floor)
    if snap is None:
        raise ValueError("Nothing to undo.")
    prev = json.loads(snap.read_text())
    prev["outputs"] = m["outputs"]
    prev["revision"] = m["revision"] + 1  # revisions only move forward
    try:
        _regen_and_record(prev, overwrite_manual_edits)
    except BackendError as exc:
        raise ValueError(str(exc)) from exc
    snap.unlink()
    return {"restored_from": snap.name, "revision": prev["revision"],
            "devices": len(prev["devices"])}


# --------------------------------------------------------------------------- views/export
@mcp.tool()
def generate_views(
    project: str, floor: str,
    views: list[Literal["architectural", "lighting", "power", "combined"]] | None = None,
    overwrite_manual_edits: bool = False,
) -> dict[str, Any]:
    """(Re)generate DXF views from the canonical model, e.g. after prepare_template."""
    m = _model(project, floor)
    out_dir = STORE.output_dir(project, floor)
    try:
        res = export.generate_dxf_views(m, out_dir, CFG.backend, views, overwrite_manual_edits)
    except BackendError as exc:
        raise ValueError(str(exc)) from exc
    STORE.save(m)
    return {"revision": m["revision"], "files": res}


@mcp.tool()
def export_package(
    project: str, floor: str,
    views: list[Literal["architectural", "lighting", "power", "combined"]] | None = None,
    overwrite_manual_edits: bool = False,
) -> dict[str, Any]:
    """Write the drawing package: DXF per view, DWG (needs live AutoCAD or ODA File Converter;
    otherwise reported as skipped), PNG previews, A3 PDF sheets and manifest.json with hashes
    and the validation result."""
    m = _model(project, floor)
    out_dir = STORE.output_dir(project, floor)
    try:
        manifest = export.export_package(m, out_dir, CFG.backend, views, overwrite_manual_edits)
    except BackendError as exc:
        raise ValueError(str(exc)) from exc
    STORE.save(m)
    return manifest


@mcp.tool()
def get_preview_image(
    project: str, floor: str,
    view: Literal["architectural", "lighting", "power", "combined"] = "combined",
) -> Image:
    """Render a PNG of a generated view so the drawing can be looked at."""
    _model(project, floor)
    out_dir = STORE.output_dir(project, floor)
    dxf = out_dir / export.view_filename(floor, view, "dxf")
    if not dxf.exists():
        raise ValueError(f"{dxf.name} has not been generated yet.")
    png = out_dir / export.view_filename(floor, view, "png")
    export.render_image(dxf, png, dark=True, size_in=(12, 8))
    return Image(path=str(png))


@mcp.tool()
def validate_drawing(project: str, floor: str) -> dict[str, Any]:
    """Validate model consistency and the generated files: devices/circuits/routes, labels,
    layers, architecture preserved vs reference, reference hash, manual edits, reopen check."""
    m = _model(project, floor)
    return validate.validate_floor(m, STORE.output_dir(project, floor))


@mcp.tool()
def sync_from_drawing(
    project: str, floor: str, view: Literal["lighting", "power", "combined"] = "combined",
    remove_missing: bool = False,
) -> dict[str, Any]:
    """Adopt manual edits: read device positions from an edited output DXF back into the model.
    Devices only in the drawing are reported (not adopted). Routes touching moved devices are
    dropped and must be re-planned. Use remove_missing=true to delete devices erased in CAD."""
    import ezdxf
    m = _model(project, floor)
    path = STORE.output_dir(project, floor) / export.view_filename(floor, view, "dxf")
    if not path.exists():
        raise ValueError(f"{path.name} does not exist.")
    found = validate.read_devices(ezdxf.readfile(str(path)))
    layers = set(VIEWS[view][1])
    from .ids import DEVICE_TYPES
    moved, missing = [], []
    for d in m["devices"]:
        if DEVICE_TYPES[d["type"]][1] not in layers:
            continue
        hit = found.get(d["id"])
        if not hit:
            missing.append(d["id"])
            continue
        h = hit[0]
        if abs(h["x"] - d["x"]) > 1e-6 or abs(h["y"] - d["y"]) > 1e-6:
            d["x"], d["y"] = h["x"], h["y"]
            moved.append(d["id"])
    unknown = sorted(set(found) - {d["id"] for d in m["devices"]})
    if remove_missing and missing:
        m["devices"] = [d for d in m["devices"] if d["id"] not in missing]
    drop = set(moved) | (set(missing) if remove_missing else set())
    dropped_routes = [r["id"] for r in m["routes"] if drop & set(r["device_ids"])]
    m["routes"] = [r for r in m["routes"] if r["id"] not in dropped_routes]
    if moved or (remove_missing and missing):
        STORE.snapshot(_model(project, floor))
        m["revision"] += 1
    m["outputs"][path.name] = sha256_file(path)  # edits accepted
    STORE.save(m)
    return {"revision": m["revision"], "moved": moved, "missing_in_drawing": missing,
            "removed": missing if remove_missing else [], "unknown_in_drawing": unknown,
            "routes_dropped_replan_needed": dropped_routes,
            "note": "Run generate_views to refresh the other views."}


@mcp.tool()
def list_floors(project: str) -> dict[str, Any]:
    """List floors that have a model in a project."""
    base = STORE.root / safe_name(project, "project")
    floors = sorted(p.parent.name for p in base.glob("*/model.json")) if base.exists() else []
    return {"project": project, "floors": floors, "output_root": str(base / "output")}


# --------------------------------------------------------------------------- live AutoCAD
@mcp.tool()
def acad_status() -> dict[str, Any]:
    """(Windows) Report the running AutoCAD / AutoCAD Electrical session via COM."""
    try:
        return autocad_backend.status()
    except BackendError as exc:
        raise ValueError(str(exc)) from exc


@mcp.tool()
def acad_open(path: str) -> dict[str, Any]:
    """(Windows) Open a drawing read-only in the running AutoCAD session."""
    try:
        return autocad_backend.open_document(path)
    except BackendError as exc:
        raise ValueError(str(exc)) from exc


@mcp.tool()
def acad_run_command(command: str) -> dict[str, Any]:
    """(Windows) Send a command line to the active AutoCAD document. Disabled unless the server
    was started with ACAD_MCP_ALLOW_COMMANDS=1 because commands can modify any open drawing."""
    if not CFG.allow_commands:
        raise ValueError("acad_run_command is disabled. Start the server with "
                         "ACAD_MCP_ALLOW_COMMANDS=1 to enable it.")
    try:
        return autocad_backend.run_command(command)
    except BackendError as exc:
        raise ValueError(str(exc)) from exc



# --------------------------------------------------------------------------- live editing
_LIVE: LiveSession | None = None


def _live() -> LiveSession:
    """Session bound to the drawing currently open in AutoCAD (created on first use)."""
    global _LIVE
    if _LIVE is None:
        _LIVE = LiveSession(RealCom(), CFG.workspace / "live")
    return _LIVE


def _guard(fn, *a, **kw):
    try:
        return fn(*a, **kw)
    except BackendError as exc:
        raise ValueError(str(exc)) from exc
    except ValueError:
        raise
    except Exception as exc:  # noqa: BLE001 - surface COM errors readably to the assistant
        raise ValueError(f"AutoCAD call failed: {type(exc).__name__}: {exc}") from exc


def _plan() -> LiveSession:
    live = _live()
    if live.mode != "plan":
        raise ValueError("Schematic mode is on, so plan-level drawing tools are disabled. Use the "
                         "sch_* tools, or call live_set_mode('plan') to go back.")
    return live


@mcp.tool()
def live_set_mode(mode: Literal["plan", "schematic"]) -> dict[str, Any]:
    """Choose what the live tools work with. 'plan' (default): floor-plan symbols and routes
    (live_place, live_route...). 'schematic': AutoCAD Electrical schematics (sch_* tools); the
    plan-level drawing tools are then blocked so the two are never mixed by accident. Only switch
    to 'schematic' when the user asks to work with schematics."""
    live = _live()
    live.mode = mode
    return {"mode": mode, "use": "sch_detect, sch_read, sch_probe" if mode == "schematic"
            else "live_place, live_move, live_route, ..."}


@mcp.tool()
def sch_detect() -> dict[str, Any]:
    """SCHEMATIC: check the open drawing / AutoCAD Electrical: product and version, whether the
    Electrical commands are loaded, whether the AutoLISP bridge works, and how many components,
    wire numbers and wire lines the drawing has. Run this first in schematic mode."""
    return _guard(lambda: Schematic(_live()).detect())


@mcp.tool()
def sch_read(include_wires: bool = True, limit: int = 500) -> dict[str, Any]:
    """SCHEMATIC: read the open schematic: components (tag, description, installation, location,
    manufacturer, catalog, terminals), wire numbers and wire-layer line counts. Read-only."""
    return _guard(lambda: Schematic(_live()).read(include_wires, limit))


@mcp.tool()
def sch_probe(prefix: str = "c:ae", limit: int = 400) -> dict[str, Any]:
    """SCHEMATIC: list the AutoLISP functions/commands this AutoCAD Electrical install exposes whose
    name starts with prefix (try c:ae, c:wd, c:ace, wd_, ace_). Read-only; used to learn the real
    command names before insert/wire tools are built."""
    return _guard(lambda: Schematic(_live()).probe(prefix, limit))


@mcp.tool()
def sch_run_lisp(expression: str) -> dict[str, Any]:
    """SCHEMATIC (advanced): evaluate an AutoLISP expression in the open drawing and return its
    printed result. Can change the drawing, so it is disabled unless the server was started with
    ACAD_MCP_ALLOW_COMMANDS=1."""
    if not CFG.allow_commands:
        raise ValueError("sch_run_lisp is disabled. Start the server with ACAD_MCP_ALLOW_COMMANDS=1.")
    return {"result": _guard(lambda: Schematic(_live()).lisp(expression))}


@mcp.tool()
def live_connect() -> dict[str, Any]:
    """LIVE (Windows): attach to the drawing open in AutoCAD / AutoCAD Electrical and report its
    name, entity counts per layer and unit scale. Start here. All live_* tools edit the open
    drawing directly, so the user sees every change on screen."""
    return _guard(lambda: _live().connect())


@mcp.tool()
def live_selftest() -> dict[str, Any]:
    """LIVE: prove the connection works. Creates a DB, luminaire and route on the ACTIVE drawing,
    moves and reads them back, then removes them. Run on a scratch drawing the first time."""
    return _guard(lambda: _live().selftest())


@mcp.tool()
def live_scan(layers: list[str] | None = None) -> dict[str, Any]:
    """LIVE: find symbols in the open drawing (loose LINEs that touch are clustered per device
    layer, as in the reference drawings). Returns type, centre and size of each, not yet tracked."""
    cl = _guard(lambda: _live().scan(layers))
    by: dict[str, int] = {}
    for c in cl:
        by[c["layer"]] = by.get(c["layer"], 0) + 1
    return {"count": len(cl), "by_layer": by, "symbols": cl[:300]}


@mcp.tool()
def live_adopt(floor: str, layers: list[str] | None = None, min_size: float = 0.0,
               max_size: float = 1e12) -> dict[str, Any]:
    """LIVE: give the existing symbols in the open drawing stable ids (e.g. 4F-LUM-01, DB-4F) by
    grouping them, so they can be moved, deleted or assigned by id. Geometry is not changed.
    Use min_size/max_size (drawing units) to skip tiny pieces such as socket pins."""
    safe_name(floor, "floor")
    return _guard(lambda: _plan().adopt(floor, layers, min_size, max_size))


@mcp.tool()
def live_list_devices() -> dict[str, Any]:
    """LIVE: tracked devices/routes with positions read fresh from the drawing (flags devices
    the user moved by hand, and ones deleted by hand)."""
    return _guard(lambda: _live().list_devices())


@mcp.tool()
def live_texts(layer: str | None = None, contains: str | None = None) -> dict[str, Any]:
    """LIVE: read TEXT in the open drawing with positions (e.g. layer 'TEXT' for room names, to
    work out where a room is before placing devices)."""
    return {"texts": _guard(lambda: _live().texts(layer, contains))}


@mcp.tool()
def live_place(
    floor: str, type: Literal["luminaire", "switch", "socket", "data", "ac", "emergency", "db"],
    x: float, y: float, rotation: float = 0.0, circuit: str | None = None,
    db: str | None = None, room: str | None = None,
) -> dict[str, Any]:
    """LIVE: draw a device symbol (reference style, correct layer) at x,y in the open drawing now.
    Same type at the same spot is not duplicated. One undo step."""
    safe_name(floor, "floor")
    return _guard(lambda: _plan().place(floor, type, x, y, rotation, circuit, db, room))


@mcp.tool()
def live_move(device_id: str, x: float | None = None, y: float | None = None,
              dx: float | None = None, dy: float | None = None) -> dict[str, Any]:
    """LIVE: move a tracked device to x,y or by dx,dy. Routes through it are flagged stale."""
    return _guard(lambda: _plan().move(device_id, x, y, dx, dy))


@mcp.tool()
def live_delete(device_id: str) -> dict[str, Any]:
    """LIVE: delete a tracked device from the open drawing (one undo step)."""
    return _guard(lambda: _plan().delete(device_id))


@mcp.tool()
def live_assign(device_id: str, circuit: str, db: str | None = None) -> dict[str, Any]:
    """LIVE: record which circuit / distribution board a device belongs to."""
    return _guard(lambda: _plan().assign(device_id, circuit, db))


@mcp.tool()
def live_route(circuit: str, kind: Literal["lighting", "power", "ac"],
               device_ids: list[str] | None = None, db: str | None = None,
               label: bool = True) -> dict[str, Any]:
    """LIVE: draw (or redraw, replacing the old one) an orthogonal route from the DB through the
    circuit's devices on the lighting/power/AC wiring layer, labelled with the circuit id."""
    return _guard(lambda: _plan().route(circuit, kind, device_ids, db, label))


@mcp.tool()
def live_add_text(layer: str, text: str, x: float, y: float, height: float) -> dict[str, Any]:
    """LIVE: add a TEXT note/label to the open drawing."""
    return _guard(lambda: _plan().add_text(layer, text, x, y, height))


@mcp.tool()
def live_add_polyline(layer: str, points: list[list[float]]) -> dict[str, Any]:
    """LIVE: draw a polyline [[x,y],...] on a layer in the open drawing."""
    return _guard(lambda: _plan().add_polyline(layer, points))


@mcp.tool()
def live_zoom(x: float, y: float, width: float) -> dict[str, Any]:
    """LIVE: pan/zoom AutoCAD's view to x,y so the user can see the change."""
    return _guard(lambda: _live().zoom(x, y, width))


@mcp.tool()
def live_undo() -> dict[str, Any]:
    """LIVE: undo the last chat instruction in AutoCAD (each live_* call is one undo step)."""
    return _guard(lambda: _live().undo())


@mcp.tool()
def live_save(path: str | None = None) -> dict[str, Any]:
    """LIVE: save the open drawing (or Save As to path)."""
    return _guard(lambda: _live().save(path))


# --------------------------------------------------------------------------- CLI
def _selftest() -> int:
    import asyncio
    import sys
    import tempfile

    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    async def run() -> list[str]:
        with tempfile.TemporaryDirectory() as tmp:
            params = StdioServerParameters(
                command=sys.executable, args=["-m", "acad_electrical_mcp.server"],
                env={**os.environ, "ACAD_MCP_WORKSPACE": tmp},
            )
            async with stdio_client(params) as (r, w), ClientSession(r, w) as sess:
                await sess.initialize()
                return sorted(t.name for t in (await sess.list_tools()).tools)

    try:
        names = asyncio.run(run())
    except Exception as exc:  # noqa: BLE001 - report any startup failure
        print(f"SELFTEST FAILED: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    print(f"SELFTEST OK: server started and exposes {len(names)} tools:")
    print("  " + ", ".join(names))
    return 0


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="acad-electrical-mcp", description=__doc__)
    ap.add_argument("--transport", choices=["stdio", "http"], default="stdio")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--allowed-host", action="append", default=[],
                    help="extra Host header allowed over HTTP (e.g. your ngrok domain)")
    ap.add_argument("--workspace", help="project/output folder (default ./acad_mcp_workspace)")
    ap.add_argument("--backend", choices=["dxf", "autocad"], help="drawing backend")
    ap.add_argument("--version", action="version", version=__version__)
    ap.add_argument("--make-sample", metavar="FILE.dxf",
                    help="write a small sample architectural floor DXF and exit")
    ap.add_argument("--selftest", action="store_true",
                    help="start the server over stdio, list its tools and exit (0 = OK)")
    args = ap.parse_args(argv)
    if args.selftest:
        raise SystemExit(_selftest())
    if args.make_sample:
        from .sample import make_sample_floor
        print(make_sample_floor(args.make_sample))
        return
    if args.workspace:
        CFG.workspace = Path(args.workspace).resolve()
        STORE.root = CFG.workspace
    if args.backend:
        CFG.backend = args.backend
    CFG.workspace.mkdir(parents=True, exist_ok=True)
    if args.transport == "http":
        mcp.settings.host = args.host
        mcp.settings.port = args.port
        if args.allowed_host or args.host not in ("127.0.0.1", "localhost", "::1"):
            hosts = args.allowed_host + [f"{args.host}:*", "127.0.0.1:*", "localhost:*"]
            mcp.settings.transport_security = TransportSecuritySettings(
                enable_dns_rebinding_protection=True, allowed_hosts=hosts,
                allowed_origins=[f"https://{h}" for h in args.allowed_host]
                + ["https://chatgpt.com", "https://claude.ai"],
            )
        mcp.run(transport="streamable-http")
    else:
        mcp.run()


if __name__ == "__main__":
    main()
