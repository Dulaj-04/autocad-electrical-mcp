"""MCP server exposing AutoCAD Electrical floor-drawing tools."""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from typing import Any, Literal

from mcp.server.fastmcp import FastMCP, Image
from mcp.server.transport_security import TransportSecuritySettings

from . import __version__, export, inspection, planner, template, validate
from .backends import autocad_backend
from .backends.base import BackendError
from .config import Config, safe_name
from .model import Store, sha256_file
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


# --------------------------------------------------------------------------- CLI
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
    args = ap.parse_args(argv)
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
