"""AutoCAD Electrical schematic analysis that works on drawing FILES and on the OPEN drawing.

Both sources are first reduced to the same plain structure (``raw`` below): block references with
their attributes and attribute positions, plus wire lines. Everything after that (components,
pins, wire networks, wire numbers, reports, audits) is shared, so a report reads the same whether
it came from a DXF on disk or from AutoCAD.

How AutoCAD Electrical stores a schematic (as used here):

* components are blocks with attributes: ``TAG1`` (parent), ``TAG1F`` (fixed tag), ``TAG2``
  (child), ``DESC1-3``, ``INST``, ``LOC``, ``MFG``, ``CAT``, ``ASSYCODE``, ``FAMILY``, ``RATINGn``
* pins are ``TERMnn`` attributes; where a wire attaches is marked by ``X?TERMnn`` attributes
  whose insertion point is the connection point and whose digit gives the wire direction
  (1 right, 2 top, 4 left, 8 bottom)
* terminals carry ``TAGSTRIP`` and ``TERM01``; wire numbers are blocks with a ``WIRENO`` attribute
* wires are LINEs on wire layers (default: any layer whose name contains ``WIRE``)
* signal arrows carry ``SIGCODE``; the drawing settings block is ``WD_M``

Wire networks are DERIVED FROM GEOMETRY (touching wire ends and T-junctions). They are a check, not
a replacement for AutoCAD Electrical's own wire data: compare important results with its reports.
"""

from __future__ import annotations

import math
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

PIN_POINT = re.compile(r"^X([0-9])TERM(\d{2,3})$")
PIN_NUMBER = re.compile(r"^TERM(\d{2,3})$")
RATING = re.compile(r"^RATING\d+$")
WIRE_NUMBER_ATTRS = ("WIRENO", "WIRENOF", "WIRENUM", "WIRE_NO")
DIRECTION = {"1": "right", "2": "top", "4": "left", "8": "bottom"}
PARENT_BLOCK = re.compile(r"^[HV]([A-Z0-9]{2})([12])", re.I)


# ----------------------------------------------------------------------------- raw readers
def raw_from_dxf(path: str, wire_layers: list[str] | None = None) -> dict[str, Any]:
    """Blocks with attributes (and attribute positions) and wire lines from a DXF/DWG file."""
    from .backends.dxf_backend import load_dxf

    doc = load_dxf(path)
    msp = doc.modelspace()
    blocks, lines = [], []
    want = _layer_filter(wire_layers)
    for e in msp:
        t = e.dxftype()
        if t == "INSERT":
            attrs, pts = {}, {}
            for a in e.attribs:
                tag = a.dxf.tag.upper()
                attrs[tag] = a.dxf.text
                ip = a.dxf.insert
                pts[tag] = (float(ip[0]), float(ip[1]))
            ip = e.dxf.insert
            blocks.append({"block": e.dxf.name, "layer": e.dxf.layer, "x": float(ip[0]),
                           "y": float(ip[1]), "attributes": attrs, "points": pts,
                           "handle": e.dxf.handle})
        elif t == "LINE" and want(e.dxf.layer):
            a, b = e.dxf.start, e.dxf.end
            lines.append({"layer": e.dxf.layer, "a": (float(a[0]), float(a[1])),
                          "b": (float(b[0]), float(b[1])), "handle": e.dxf.handle})
        elif t == "LWPOLYLINE" and want(e.dxf.layer):
            pts = [(float(p[0]), float(p[1])) for p in e.get_points("xy")]
            if e.closed and pts:
                pts.append(pts[0])
            for p, q in zip(pts, pts[1:]):
                lines.append({"layer": e.dxf.layer, "a": p, "b": q, "handle": e.dxf.handle})
    return {"drawing": Path(path).name, "path": str(path), "blocks": blocks, "lines": lines,
            "insunits": int(doc.header.get("$INSUNITS", 0))}


def raw_from_open(live, wire_layers: list[str] | None = None) -> dict[str, Any]:
    """The same structure read from the drawing open in AutoCAD (COM). Read-only."""
    c = live.com.call
    want = _layer_filter(wire_layers)
    blocks, lines = [], []
    for e in c(lambda: live._ms()):
        kind = str(c(lambda e=e: e.ObjectName))
        if "BlockReference" in kind:
            attrs, pts = {}, {}
            if c(lambda e=e: e.HasAttributes):
                for a in c(lambda e=e: e.GetAttributes()):
                    tag = str(c(lambda a=a: a.TagString)).upper()
                    attrs[tag] = str(c(lambda a=a: a.TextString))
                    try:
                        ip = c(lambda a=a: a.InsertionPoint)
                        pts[tag] = (float(ip[0]), float(ip[1]))
                    except Exception:  # noqa: BLE001 - attribute without a readable position
                        pass
            p = c(lambda e=e: e.InsertionPoint)
            try:
                name = str(c(lambda e=e: e.EffectiveName))
            except Exception:  # noqa: BLE001
                name = str(c(lambda e=e: e.Name))
            blocks.append({"block": name, "layer": str(c(lambda e=e: e.Layer)), "x": float(p[0]),
                           "y": float(p[1]), "attributes": attrs, "points": pts,
                           "handle": str(c(lambda e=e: e.Handle))})
        elif kind.endswith("Line") and "Polyline" not in kind:
            lay = str(c(lambda e=e: e.Layer))
            if want(lay):
                a, b = c(lambda e=e: e.StartPoint), c(lambda e=e: e.EndPoint)
                lines.append({"layer": lay, "a": (float(a[0]), float(a[1])),
                              "b": (float(b[0]), float(b[1])), "handle": str(c(lambda e=e: e.Handle))})
    doc = live.doc
    return {"drawing": str(c(lambda: doc.Name)), "path": str(c(lambda: doc.FullName)),
            "blocks": blocks, "lines": lines, "insunits": int(c(lambda: doc.GetVariable("INSUNITS")) or 0)}


def _layer_filter(wire_layers: list[str] | None):
    if wire_layers:
        names = {x.upper() for x in wire_layers}
        return lambda lay: str(lay).upper() in names
    return lambda lay: "WIRE" in str(lay).upper()


# ----------------------------------------------------------------------------- interpretation
def _family_from_block(name: str) -> str | None:
    m = PARENT_BLOCK.match(name or "")
    return m.group(1).upper() if m else None


def _pins(b: dict[str, Any]) -> list[dict[str, Any]]:
    a, pts = b["attributes"], b["points"]
    pins: dict[str, dict[str, Any]] = {}
    for tag, val in a.items():
        m = PIN_NUMBER.match(tag)
        if m:
            pins.setdefault(m.group(1), {"pin": m.group(1), "terminal": val, "points": []})
    for tag in a:
        m = PIN_POINT.match(tag)
        if m:
            pin = pins.setdefault(m.group(2), {"pin": m.group(2), "terminal": "", "points": []})
            x, y = pts.get(tag, (b["x"], b["y"]))
            pin["points"].append({"x": round(x, 4), "y": round(y, 4),
                                  "direction": DIRECTION.get(m.group(1), m.group(1))})
    return [pins[k] for k in sorted(pins)]


def interpret(raw: dict[str, Any]) -> dict[str, Any]:
    """Split the blocks of one drawing into components, terminals, wire numbers, signals."""
    comps, terms, wnos, signals, others, ladders = [], [], [], [], 0, 0
    settings: dict[str, str] | None = None
    dwg = raw["drawing"]
    for b in raw["blocks"]:
        a = b["attributes"]
        name = str(b["block"]).upper()
        if name == "WD_M":
            settings = dict(a)
            continue
        if name.startswith("WD_MLR"):
            ladders += 1
            continue
        base = {"drawing": dwg, "block": b["block"], "layer": b["layer"],
                "x": round(b["x"], 4), "y": round(b["y"], 4), "handle": b["handle"]}
        if "TAGSTRIP" in a:
            terms.append({**base, "kind": "terminal", "strip": a.get("TAGSTRIP", ""),
                          "number": a.get("TERM01", ""), "installation": a.get("INST", ""),
                          "location": a.get("LOC", ""), "manufacturer": a.get("MFG", ""),
                          "catalog": a.get("CAT", ""), "assembly": a.get("ASSYCODE", ""),
                          "description": _desc(a), "pins": _pins(b)})
        elif any(k in a for k in ("TAG1", "TAG1F", "TAG2")):
            child = "TAG2" in a and not ("TAG1" in a or "TAG1F" in a)
            tag = a.get("TAG2") if child else (a.get("TAG1") or a.get("TAG1F") or "")
            comps.append({**base, "kind": "child" if child else "parent", "tag": tag,
                          "fixed_tag": "TAG1F" in a,
                          "family": a.get("FAMILY") or _family_from_block(b["block"]) or "",
                          "description": _desc(a), "installation": a.get("INST", ""),
                          "location": a.get("LOC", ""), "manufacturer": a.get("MFG", ""),
                          "catalog": a.get("CAT", ""), "assembly": a.get("ASSYCODE", ""),
                          "ratings": {k: v for k, v in a.items() if RATING.match(k) and v},
                          "pins": _pins(b)})
        elif any(k in a for k in WIRE_NUMBER_ATTRS):
            key = next(k for k in WIRE_NUMBER_ATTRS if k in a)
            wnos.append({**base, "wire_number": a[key], "fixed": key == "WIRENOF"})
        elif "SIGCODE" in a:
            signals.append({**base, "code": a.get("SIGCODE", ""), "description": _desc(a)})
        elif a:
            others += 1
    return {"drawing": dwg, "path": raw.get("path"), "components": comps, "terminals": terms,
            "wire_numbers": wnos, "signals": signals, "other_attribute_blocks": others,
            "ladders": ladders, "settings_block": settings, "insunits": raw.get("insunits"),
            "lines": raw["lines"]}


def _desc(a: dict[str, str]) -> str:
    return " ".join(a.get(k, "") for k in ("DESC1", "DESC2", "DESC3") if a.get(k)).strip()


# ----------------------------------------------------------------------------- wire networks
class _Grid:
    """Spatial hash of segments so endpoint/pin look-ups stay fast on large drawings."""

    def __init__(self, segs: list[tuple[tuple[float, float], tuple[float, float]]], cell: float):
        self.segs, self.cell = segs, cell
        self.cells: dict[tuple[int, int], list[int]] = defaultdict(list)
        for i, (a, b) in enumerate(segs):
            x0, x1 = sorted((a[0], b[0]))
            y0, y1 = sorted((a[1], b[1]))
            for cx in range(self._k(x0), self._k(x1) + 1):
                for cy in range(self._k(y0), self._k(y1) + 1):
                    self.cells[(cx, cy)].append(i)

    def _k(self, v: float) -> int:
        return math.floor(v / self.cell)

    def near(self, p: tuple[float, float], tol: float) -> list[int]:
        out: set[int] = set()
        for cx in range(self._k(p[0] - tol), self._k(p[0] + tol) + 1):
            for cy in range(self._k(p[1] - tol), self._k(p[1] + tol) + 1):
                for i in self.cells.get((cx, cy), ()):
                    if _dist_to_seg(p, *self.segs[i]) <= tol:
                        out.add(i)
        return sorted(out)


def _dist_to_seg(p, a, b) -> float:
    dx, dy = b[0] - a[0], b[1] - a[1]
    L2 = dx * dx + dy * dy
    if L2 == 0:
        return math.hypot(p[0] - a[0], p[1] - a[1])
    t = max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / L2))
    return math.hypot(p[0] - (a[0] + t * dx), p[1] - (a[1] + t * dy))


def auto_tolerance(drawing: dict[str, Any]) -> float:
    pts = [p for ln in drawing["lines"] for p in (ln["a"], ln["b"])]
    pts += [(c["x"], c["y"]) for c in drawing["components"] + drawing["terminals"]]
    if not pts:
        return 0.01
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    span = max(max(xs) - min(xs), max(ys) - min(ys), 1e-9)
    return max(span * 0.0005, 1e-6)


def networks(drawing: dict[str, Any], tolerance: float | None = None,
             wire_number_radius: float | None = None) -> dict[str, Any]:
    """Group wire lines that touch (end to end or at a T) into networks, attach device pins and
    wire numbers to them, and derive from/to pairs. Adds results to ``drawing`` in place."""
    tol = tolerance or auto_tolerance(drawing)
    segs = [(ln["a"], ln["b"]) for ln in drawing["lines"]]
    n = len(segs)
    parent = list(range(n))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    lengths = sorted(math.dist(a, b) for a, b in segs) or [1.0]
    cell = max(lengths[len(lengths) // 2], tol * 10)
    grid = _Grid(segs, cell)
    for i, (a, b) in enumerate(segs):
        for p in (a, b):
            for j in grid.near(p, tol):
                if j != i:
                    parent[find(i)] = find(j)
    roots = sorted({find(i) for i in range(n)})
    net_of = {r: k + 1 for k, r in enumerate(roots)}
    nets: dict[int, dict[str, Any]] = {
        net_of[r]: {"net": net_of[r], "segments": 0, "pins": [], "wire_numbers": [],
                    "layers": set()} for r in roots}
    for i in range(n):
        nk = nets[net_of[find(i)]]
        nk["segments"] += 1
        nk["layers"].add(drawing["lines"][i]["layer"])
    unconnected: list[dict[str, Any]] = []
    for dev in drawing["components"] + drawing["terminals"]:
        ref = dev.get("tag") if dev["kind"] != "terminal" else f"{dev['strip']}:{dev['number']}"
        for pin in dev["pins"]:
            touched: set[int] = set()
            for pt in pin["points"]:
                for j in grid.near((pt["x"], pt["y"]), tol):
                    touched.add(net_of[find(j)])
            pin["nets"] = sorted(touched)
            for k in touched:
                nets[k]["pins"].append({"device": ref, "kind": dev["kind"], "pin": pin["pin"],
                                        "terminal": pin["terminal"],
                                        "x": pin["points"][0]["x"], "y": pin["points"][0]["y"]})
            if pin["points"] and not touched:
                unconnected.append({"device": ref, "pin": pin["pin"], "terminal": pin["terminal"]})
    radius = wire_number_radius or tol * 20
    loose_numbers = []
    for w in drawing["wire_numbers"]:
        hits = grid.near((w["x"], w["y"]), radius)
        if hits:
            best = min(hits, key=lambda j: _dist_to_seg((w["x"], w["y"]), *segs[j]))
            w["net"] = net_of[find(best)]
            nets[w["net"]]["wire_numbers"].append(w["wire_number"])
        else:
            w["net"] = None
            loose_numbers.append(w["wire_number"])
    from_to = []
    for nk in nets.values():
        nk["layers"] = sorted(nk["layers"])
        nk["wire_numbers"] = sorted(set(nk["wire_numbers"]))
        chain = _chain(nk["pins"])
        for a, b in zip(chain, chain[1:]):
            from_to.append({"drawing": drawing["drawing"], "net": nk["net"],
                            "wire_number": ", ".join(nk["wire_numbers"]),
                            "from": f"{a['device']}:{a['terminal'] or a['pin']}",
                            "to": f"{b['device']}:{b['terminal'] or b['pin']}",
                            "layer": ", ".join(nk["layers"])})
    drawing.update(tolerance=tol, nets=list(nets.values()), from_to=from_to,
                   unconnected_pins=unconnected, wire_numbers_off_wire=loose_numbers)
    return drawing


def _chain(pins: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Order the pins of one network as a nearest-neighbour chain (approximate wire order)."""
    seen, left = [], sorted({(p["device"], p["pin"]): p for p in pins}.values(),
                            key=lambda p: (p["x"], -p["y"]))
    if not left:
        return []
    cur = left.pop(0)
    seen.append(cur)
    while left:
        nxt = min(left, key=lambda p: math.hypot(p["x"] - cur["x"], p["y"] - cur["y"]))
        left.remove(nxt)
        seen.append(nxt)
        cur = nxt
    return seen


def analyse(raw: dict[str, Any], tolerance: float | None = None) -> dict[str, Any]:
    return networks(interpret(raw), tolerance)


def summary(d: dict[str, Any]) -> dict[str, Any]:
    nets = d.get("nets", [])
    return {"drawing": d["drawing"], "components": sum(c["kind"] == "parent" for c in d["components"]),
            "child_components": sum(c["kind"] == "child" for c in d["components"]),
            "terminals": len(d["terminals"]), "wire_numbers": len(d["wire_numbers"]),
            "wire_lines": len(d["lines"]), "wire_networks": len(nets),
            "signal_arrows": len(d["signals"]), "ladders": d["ladders"],
            "electrical_drawing": d["settings_block"] is not None,
            "unconnected_pins": len(d.get("unconnected_pins", [])),
            "tolerance": round(d.get("tolerance", 0), 6)}
