"""Validation of the model and of generated drawing files."""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path
from typing import Any

import ezdxf

from .ids import DEVICE_TYPES, ROUTE_LAYERS
from .model import sha256_file
from .template import ARCH_LAYERS, VIEWS

KIND_OF = {t: v[2] for t, v in DEVICE_TYPES.items() if v[2]}
KIND_OF["data"] = "power"
DEVICE_LAYERS = {v[1] for v in DEVICE_TYPES.values()}


def _issue(sev: str, code: str, msg: str, ref: str | None = None) -> dict[str, Any]:
    return {"severity": sev, "code": code, "message": msg, "ref": ref}


def validate_model(model: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    floor = model["floor"]
    devs = {d["id"]: d for d in model["devices"]}
    pat = re.compile(rf"^({re.escape(floor)}-[A-Z]+\d\d+|DB-{re.escape(floor)})$")
    ids = Counter(d["id"] for d in model["devices"])
    for did, n in ids.items():
        if n > 1:
            out.append(_issue("error", "DUP_ID", f"Device id {did} used {n} times", did))
        if not pat.match(did):
            out.append(_issue("warning", "ID_FORMAT", f"{did} is not floor-prefixed", did))
    dbs = [d for d in model["devices"] if d["type"] == "db"]
    if not dbs:
        out.append(_issue("warning", "NO_DB", f"Floor {floor} has no distribution board"))
    circuits = {c["id"]: c for c in model["circuits"]}
    rooms = {r["id"]: r for r in model["rooms"]}
    for d in model["devices"]:
        if d["type"] == "db":
            continue
        if not d.get("circuit"):
            out.append(_issue("warning", "NO_CIRCUIT", f"{d['id']} has no circuit", d["id"]))
        elif d["circuit"] not in circuits:
            out.append(_issue("error", "BAD_CIRCUIT", f"{d['id']}: unknown circuit "
                              f"{d['circuit']}", d["id"]))
        else:
            c = circuits[d["circuit"]]
            if c["kind"] != KIND_OF[d["type"]]:
                out.append(_issue("error", "CIRCUIT_KIND", f"{d['id']} ({d['type']}) is on "
                                  f"{c['kind']} circuit {c['id']}", d["id"]))
            if c.get("db") and c["db"] not in devs:
                out.append(_issue("error", "BAD_DB", f"Circuit {c['id']} references missing "
                                  f"DB {c['db']}", c["id"]))
        r = rooms.get(d.get("room") or "")
        if d.get("room") and not r:
            out.append(_issue("warning", "BAD_ROOM", f"{d['id']}: unknown room {d['room']}",
                              d["id"]))
        elif r:
            b = r["bounds"]
            if not (b[0] <= d["x"] <= b[2] and b[1] <= d["y"] <= b[3]):
                out.append(_issue("warning", "OUTSIDE_ROOM",
                                  f"{d['id']} lies outside room {r['id']}", d["id"]))
    for rt in model["routes"]:
        c = circuits.get(rt["circuit"])
        if not c:
            out.append(_issue("error", "ROUTE_CIRCUIT", f"Route {rt['id']}: unknown circuit", rt["id"]))
            continue
        if c["kind"] != rt["kind"]:
            out.append(_issue("error", "ROUTE_KIND", f"Route {rt['id']} kind mismatch", rt["id"]))
        for did in rt["device_ids"]:
            d = devs.get(did)
            if d is None:
                out.append(_issue("error", "ROUTE_DEVICE", f"Route {rt['id']}: missing device "
                                  f"{did}", rt["id"]))
            elif d.get("circuit") != rt["circuit"]:
                out.append(_issue("error", "ROUTE_ASSOC", f"Route {rt['id']}: {did} is on circuit "
                                  f"{d.get('circuit')}", rt["id"]))
        pts = rt["points"]
        for did in rt["device_ids"][-1:]:
            d = devs.get(did)
            if d and pts and (abs(pts[-1][0] - d["x"]) > 1e-6 or abs(pts[-1][1] - d["y"]) > 1e-6):
                out.append(_issue("warning", "ROUTE_END", f"Route {rt['id']} no longer ends at "
                                  f"{did} (device moved?)", rt["id"]))
    return out


def _label_overlaps(doc, layers: set[str]) -> int:
    boxes = []
    for e in doc.modelspace().query("INSERT"):
        if e.dxf.layer not in layers:
            continue
        for a in e.attribs:
            if a.dxf.tag == "ID" and a.dxf.text and not (a.dxf.flags & 1):
                x, y = a.dxf.insert.x, a.dxf.insert.y
                w = a.dxf.height * 0.7 * len(a.dxf.text)
                boxes.append((x, y, x + w, y + a.dxf.height))
    n = 0
    for i in range(len(boxes)):
        for j in range(i + 1, len(boxes)):
            a, b = boxes[i], boxes[j]
            if a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]:
                n += 1
    return n


def read_devices(doc) -> dict[str, list[dict[str, Any]]]:
    """Device INSERTs found in a drawing, grouped by id (legend symbols are skipped)."""
    found: dict[str, list[dict[str, Any]]] = {}
    for e in doc.modelspace().query("INSERT"):
        if e.dxf.layer not in DEVICE_LAYERS:
            continue
        tags = {a.dxf.tag: a.dxf.text for a in e.attribs}
        did = tags.get("ID")
        if not did:
            continue
        found.setdefault(did, []).append(
            {"x": e.dxf.insert.x, "y": e.dxf.insert.y, "rotation": e.dxf.get("rotation", 0.0),
             "layer": e.dxf.layer, "attribs": tags}
        )
    return found


def validate_file(model: dict[str, Any], path: Path, view: str, ref_doc=None) -> list[dict]:
    out: list[dict[str, Any]] = []
    name = path.name
    if not path.exists():
        return [_issue("error", "MISSING_FILE", f"{name} does not exist", name)]
    recorded = model["outputs"].get(name)
    if recorded and sha256_file(path) != recorded:
        out.append(_issue("warning", "MANUAL_EDIT", f"{name} changed since it was generated "
                          "(manual edits). Use sync_from_drawing to adopt them.", name))
    try:
        doc = ezdxf.readfile(str(path))
    except (OSError, ezdxf.DXFError) as exc:
        return out + [_issue("error", "REOPEN_FAILED", f"{name} cannot be reopened: {exc}", name)]
    for layer in model["template"]["layers"]:
        if layer not in doc.layers:
            out.append(_issue("error", "MISSING_LAYER", f"{name}: layer {layer} missing", name))
    layers = set(VIEWS[view][1])
    expected = {d["id"] for d in model["devices"] if DEVICE_TYPES[d["type"]][1] in layers}
    found = read_devices(doc)
    for did in sorted(expected - set(found)):
        out.append(_issue("error", "DEVICE_MISSING", f"{name}: {did} not drawn", did))
    for did in sorted(set(found) - expected):
        out.append(_issue("warning", "DEVICE_EXTRA", f"{name}: {did} drawn but not in model", did))
    for did, items in found.items():
        if len(items) > 1:
            out.append(_issue("error", "DEVICE_DUP", f"{name}: {did} drawn {len(items)} times", did))
    wire_layers = {ROUTE_LAYERS[r["kind"]] for r in model["routes"]} & layers
    for wl in wire_layers:
        if not list(doc.modelspace().query(f'LWPOLYLINE[layer=="{wl}"]')):
            out.append(_issue("error", "ROUTE_MISSING", f"{name}: no geometry on {wl}", name))
    notes = " ".join(t.dxf.text for t in doc.modelspace().query("TEXT") if t.dxf.layer == "NOTES")
    if model["template"].get("status", "DRAFT") not in notes:
        out.append(_issue("warning", "NO_STATUS", f"{name}: status note missing", name))
    if ref_doc is not None:
        for layer in ARCH_LAYERS:
            n_ref = len(list(ref_doc.modelspace().query(f'*[layer=="{layer}"]')))
            n_out = len(list(doc.modelspace().query(f'*[layer=="{layer}"]')))
            if n_ref != n_out:
                out.append(_issue("error", "ARCH_CHANGED", f"{name}: layer {layer} has {n_out} "
                                  f"entities, reference has {n_ref}", name))
    n_over = _label_overlaps(doc, DEVICE_LAYERS)
    if n_over:
        out.append(_issue("warning", "LABEL_OVERLAP", f"{name}: {n_over} overlapping device "
                          "label pair(s)", name))
    return out


def validate_floor(model: dict[str, Any], out_dir: Path, views: list[str] | None = None) -> dict:
    issues = validate_model(model)
    ref_doc = None
    src = model.get("source")
    if src:
        try:
            if sha256_file(src["path"]) != src["sha256"]:
                issues.append(_issue("error", "SOURCE_CHANGED",
                                     "Reference file hash differs from the registered hash"))
            elif src["path"].lower().endswith(".dxf"):
                ref_doc = ezdxf.readfile(src["path"])
        except (OSError, ezdxf.DXFError) as exc:
            issues.append(_issue("error", "SOURCE_UNREADABLE", str(exc)))
    files = {}
    for view in views or list(VIEWS):
        fname = f"{model['floor']}_{VIEWS[view][0]}.dxf"
        file_issues = validate_file(model, out_dir / fname, view, ref_doc)
        files[fname] = not any(i["severity"] == "error" for i in file_issues)
        issues += file_issues
    errors = sum(i["severity"] == "error" for i in issues)
    return {
        "ok": errors == 0,
        "errors": errors,
        "warnings": sum(i["severity"] == "warning" for i in issues),
        "files": files,
        "device_counts": dict(Counter(d["type"] for d in model["devices"])),
        "issues": issues,
        "status_note": "DRAFT drawing validation only; no engineering approval is implied.",
    }
