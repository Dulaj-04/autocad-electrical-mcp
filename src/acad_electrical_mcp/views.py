"""Render discipline and combined views from the canonical floor model."""

from __future__ import annotations

import math
from typing import Any

from .backends.base import BackendError, DrawingBackend
from .ids import DEVICE_TYPES, ROUTE_LAYERS
from .model import sha256_file
from .template import VIEWS

LEGEND_TEXT = {
    "luminaire": "Luminaire",
    "switch": "Light switch",
    "socket": "Power socket outlet",
    "data": "Data outlet",
    "ac": "Air-conditioning provision",
    "db": "Distribution board",
    "emergency": "Exit / emergency provision",
}
ROUTE_LEGEND = {
    "LIGHT_WIRING": "Lighting route",
    "POWER_WIRING": "General power route",
    "AC_WIRING": "Dedicated AC route",
}


def check_source(model: dict[str, Any]) -> None:
    src = model.get("source")
    if not src:
        return
    try:
        current = sha256_file(src["path"])
    except OSError as exc:
        raise BackendError(f"Reference file is no longer readable: {src['path']} ({exc})") from exc
    if current != src["sha256"]:
        raise BackendError(
            "Stale input: the architectural reference changed since it was registered. "
            "Re-run prepare_floor_model to accept the new file."
        )


def _extent_of_model(model: dict[str, Any]) -> tuple[float, float, float, float] | None:
    xs, ys = [], []
    for r in model["rooms"]:
        b = r["bounds"]
        xs += [b[0], b[2]]
        ys += [b[1], b[3]]
    for d in model["devices"]:
        xs.append(d["x"])
        ys.append(d["y"])
    return (min(xs), min(ys), max(xs), max(ys)) if xs else None


def symbol_metrics(model: dict[str, Any], bounds) -> tuple[float, float]:
    tpl = model["template"]
    size = tpl.get("symbol_size")
    if not size:
        b = bounds or (0, 0, 100, 100)
        diag = math.hypot(b[2] - b[0], b[3] - b[1]) or 100.0
        size = diag / 80
    th = tpl.get("text_height") or size * 0.6
    return float(size), float(th)


def render_view(
    backend: DrawingBackend, model: dict[str, Any], view: str, base: str | None
) -> dict[str, Any]:
    if view not in VIEWS:
        raise ValueError(f"Unknown view {view!r}; expected one of {sorted(VIEWS)}")
    _, layers, title = VIEWS[view]
    check_source(model)
    backend.begin(base)
    tpl = model["template"]
    for name, props in tpl["layers"].items():
        backend.ensure_layer(name, props["color"], props["lineweight"])

    bounds = backend.bounds()
    arch_bounds = bounds
    if bounds is None:
        bounds = _extent_of_model(model)
    size, th = symbol_metrics(model, bounds)
    backend.define_symbols(size, th)

    if base is None:  # no reference drawing: outline the rooms from the model
        for room in model["rooms"]:
            backend.add_rect("Wall", tuple(room["bounds"]))
            b = room["bounds"]
            backend.add_text("TEXT", room["name"], b[0] + th, b[3] - 2 * th, th)

    counts = {"devices": 0, "routes": 0}
    for route in model["routes"]:
        layer = ROUTE_LAYERS[route["kind"]]
        if layer in layers and len(route["points"]) >= 2:
            backend.add_polyline(layer, [tuple(p) for p in route["points"]])
            counts["routes"] += 1
    used_types: set[str] = set()
    for d in model["devices"]:
        layer = DEVICE_TYPES[d["type"]][1]
        if layer not in layers:
            continue
        backend.insert_device(
            d["type"], layer, d["x"], d["y"], d.get("rotation", 0.0),
            {"ID": d["id"], "CIRCUIT": d.get("circuit") or "", "DB": d.get("db") or "",
             "TYPE": d["type"]},
        )
        used_types.add(d["type"])
        counts["devices"] += 1

    _annotate(backend, model, view, title, layers, used_types, bounds, size, th)
    return {"view": view, "extent": arch_bounds or bounds, "symbol_size": size, **counts}


def _annotate(backend, model, view, title, layers, used_types, bounds, size, th) -> None:
    """Title, status, legend and notes below the plan on the NOTES layer."""
    x0 = bounds[0] if bounds else 0.0
    y = (bounds[1] if bounds else 0.0) - size * 4
    tb = model["template"]["title_block"]
    backend.add_text("NOTES", f"{model['floor']} - {title}", x0, y, th * 2.2, bold=True)
    y -= th * 3.5
    status = model["template"].get("status", "DRAFT")
    backend.add_text(
        "NOTES",
        f"STATUS: {status} - revision {model['revision']} - not for construction",
        x0, y, th * 1.2,
    )
    y -= th * 2
    if tb.get("project"):
        backend.add_text("NOTES", f"Project: {tb['project']}", x0, y, th)
        y -= th * 1.8
    for line in tb.get("notes", []):
        backend.add_text("NOTES", str(line), x0, y, th)
        y -= th * 1.8

    # legend: only the symbols/routes that appear in this view
    y -= th
    backend.add_text("NOTES", "LEGEND", x0, y, th * 1.2)
    y -= size * 1.8
    for dtype in LEGEND_TEXT:
        if dtype not in used_types:
            continue
        backend.insert_device(dtype, "NOTES", x0 + size, y, 0.0,
                              {"ID": "", "CIRCUIT": "", "DB": "", "TYPE": "legend"})
        backend.add_text("NOTES", LEGEND_TEXT[dtype], x0 + size * 3.2, y - th / 2, th)
        y -= size * 1.8
    for layer, text in ROUTE_LEGEND.items():
        if layer in layers and any(ROUTE_LAYERS[r["kind"]] == layer for r in model["routes"]):
            backend.add_polyline(layer, [(x0, y), (x0 + size * 2, y)])
            backend.add_text("NOTES", text, x0 + size * 3.2, y - th / 2, th)
            y -= size * 1.8
