"""One-shot evidence gathering on the user's own AutoCAD (Electrical) install.

``capture_install`` records what this install exposes (modules, commands, AutoLISP functions,
the attribute names its symbols really use) so schematic WRITE tools can be built against facts,
not guesses. ``acceptance_run`` exercises every live plan-mode tool on a scratch drawing and
reports pass/fail per step, replacing one-tool-at-a-time manual testing. Both write one JSON file
the user can send back.
"""

from __future__ import annotations

import platform
import time
from collections import Counter
from typing import Any

from . import __version__
from .aeschematic import raw_from_open

# Command names to ask about. "no" is an answer too: it shows what this version lacks.
KNOWN_COMMANDS = [
    "AEPROJECT", "AECOMPONENT", "AEWIRE", "AEMULTIBUS", "AELADDER", "AEWIRENO", "AERETAG",
    "AEREPORTS", "AEAUDIT", "AEDWGAUDIT", "AETITLE", "AEUPDATETITLE", "AESOURCE", "AEDESTINATION",
    "AEFOOTPRINT", "AETERMINAL", "AEEDITTERMINAL", "AEPLC", "AEEDITCOMPONENT", "AECOPYCOMP",
    "AESCOOT", "AEERASECOMP", "AEPROJECTUPDATE", "AEPROPERTIES", "AECABLEMARKER",
]
PROBE_PREFIXES = ["c:ae", "c:wd", "c:ace", "wd_", "ace_"]


def _try(fn, *a, **kw) -> Any:
    try:
        return fn(*a, **kw)
    except Exception as exc:  # noqa: BLE001 - every part is optional evidence
        return {"error": f"{type(exc).__name__}: {exc}"}


def capture_install(schematic, extra_commands: list[str] | None = None,
                    sample_blocks: int = 60) -> dict[str, Any]:
    live = schematic.live
    out: dict[str, Any] = {
        "captured_at": time.strftime("%Y-%m-%d %H:%M:%S"), "server_version": __version__,
        "python": platform.python_version(), "os": platform.platform(),
    }
    out["detect"] = _try(schematic.detect)
    out["arx_modules"] = _try(schematic.arx_modules)
    out["commands"] = _try(schematic.commands_exist, KNOWN_COMMANDS + list(extra_commands or []))
    out["probe"] = {p: _try(schematic.probe, p, 2000) for p in PROBE_PREFIXES}
    raw = _try(raw_from_open, live)
    if isinstance(raw, dict) and "blocks" in raw:
        names = Counter(b["block"] for b in raw["blocks"])
        tags = Counter(t for b in raw["blocks"] for t in b["attributes"])
        samples, seen = [], set()
        for b in raw["blocks"]:
            if b["block"] in seen or not b["attributes"]:
                continue
            seen.add(b["block"])
            samples.append({"block": b["block"], "layer": b["layer"],
                            "attributes": b["attributes"],
                            "attribute_offsets": {k: [round(p[0] - b["x"], 4), round(p[1] - b["y"], 4)]
                                                  for k, p in b["points"].items()}})
            if len(samples) >= sample_blocks:
                break
        out["drawing"] = {"name": raw["drawing"], "insunits": raw["insunits"],
                          "block_counts": dict(names.most_common(80)),
                          "attribute_tags": dict(tags.most_common(150)),
                          "wire_layers": dict(Counter(ln["layer"] for ln in raw["lines"])),
                          "sample_blocks": samples}
    else:
        out["drawing"] = raw
    out["next"] = ("Send this file back. It shows which commands and functions exist on this install "
                   "and the attribute names its symbols use, so schematic insert/wire/number tools "
                   "can be built for this exact version.")
    return out


def acceptance_run(live) -> dict[str, Any]:
    """Run every live plan-mode operation once on the ACTIVE (scratch) drawing and clean up."""
    steps: list[dict[str, Any]] = []
    made: list[str] = []
    floor = "ZZACC"

    def step(name: str, fn, *a, **kw):
        t0 = time.time()
        try:
            res = fn(*a, **kw)
            steps.append({"step": name, "ok": True, "seconds": round(time.time() - t0, 2)})
            return res
        except Exception as exc:  # noqa: BLE001 - the report IS the result
            steps.append({"step": name, "ok": False, "seconds": round(time.time() - t0, 2),
                          "error": f"{type(exc).__name__}: {exc}"})
            return None

    info = step("live_connect", live.connect) or {}
    inv = step("live_inventory", live.inventory) or {}
    step("live_texts", live.texts)
    step("live_scan", live.scan)
    s = info.get("unit_scale_vs_mm", 1.0) or 1.0
    x0 = y0 = 0.0
    ext = inv.get("extents")
    if isinstance(ext, (list, tuple)) and len(ext) == 4:
        x0, y0 = float(ext[2]) + 5000 * s, float(ext[1])
    db = step("live_place db", live.place, floor, "db", x0, y0)
    if db:
        made.append(db["id"])
    for i, t in enumerate(["luminaire", "switch", "socket", "data", "ac", "emergency"]):
        r = step(f"live_place {t}", live.place, floor, t, x0 + (i + 1) * 1500 * s, y0 + 1500 * s)
        if r:
            made.append(r["id"])
    lum = next((m for m in made if "-LUM-" in m), None)
    if lum and db:
        step("live_assign", live.assign, lum, f"{floor}-L01", db["id"])
        step("live_move", live.move, lum, dx=300 * s)
        step("live_route", live.route, f"{floor}-L01", "lighting", db=db["id"])
        step("live_circuit_lengths", live.circuit_lengths)
    step("live_list_devices", live.list_devices)
    step("live_add_text", live.add_text, "NOTES", "ACCEPTANCE RUN", x0, y0 - 1000 * s, 250 * s)
    step("live_add_polyline", live.add_polyline, "NOTES",
         [[x0, y0 - 1500 * s], [x0 + 3000 * s, y0 - 1500 * s]])
    step("live_undo (removes the polyline)", live.undo)
    step("live_zoom", live.zoom, x0, y0, 12000 * s)
    step("live_resync", live.resync)
    for did in made:
        step(f"live_delete {did}", live.delete, did)
    # leftovers: the route group and the note text
    def _cleanup():
        data = live._load()
        for gname, g in live._groups().items():
            if gname.startswith(f"R-{floor}"):
                for it in live._items(g):
                    live.com.call(lambda it=it: it.Delete())
                live.com.call(lambda g=g: g.Delete())
        data["routes"] = {k: v for k, v in data["routes"].items() if not k.startswith(floor)}
        live._save(data)
        return True
    step("cleanup", _cleanup)
    ok = sum(s_["ok"] for s_ in steps)
    return {"passed": ok, "failed": len(steps) - ok, "steps": steps,
            "note": "The ACCEPTANCE RUN text may remain on layer NOTES; delete it by hand. Send "
                    "this report back if anything failed."}
