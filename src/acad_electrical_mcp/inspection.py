"""Read-only inventory of a DXF/DWG reference drawing."""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

from ezdxf import bbox

from .backends.dxf_backend import load_dxf
from .model import sha256_file

UNIT_NAMES = {
    0: "unitless/undeclared", 1: "inches", 2: "feet", 4: "millimetres", 5: "centimetres",
    6: "metres",
}


def inspect_drawing(path: str, max_texts: int = 200) -> dict[str, Any]:
    doc = load_dxf(path)
    msp = doc.modelspace()
    entities = list(msp)
    by_layer: dict[str, Counter] = {}
    for e in entities:
        by_layer.setdefault(e.dxf.layer, Counter())[e.dxftype()] += 1
    layers = []
    for lyr in doc.layers:
        layers.append({
            "name": lyr.dxf.name, "color": lyr.color, "lineweight": lyr.dxf.get("lineweight"),
            "frozen": lyr.is_frozen(), "off": lyr.is_off(),
            "entities": dict(by_layer.get(lyr.dxf.name, {})),
        })
    texts = []
    for e in msp.query("TEXT MTEXT"):
        raw = e.dxf.text if e.dxftype() == "TEXT" else e.text
        texts.append({"text": raw.strip(), "layer": e.dxf.layer,
                      "x": round(e.dxf.insert.x, 3), "y": round(e.dxf.insert.y, 3)})
    try:
        box = bbox.extents(msp, fast=True)
        extents = ([round(v, 3) for v in (*box.extmin[:2], *box.extmax[:2])]
                   if box.has_data else None)
    except Exception:  # noqa: BLE001
        extents = None
    ins = int(doc.header.get("$INSUNITS", 0))
    warnings = []
    if ins == 0:
        warnings.append("$INSUNITS is undeclared: confirm units before measuring areas or "
                        "applying a transform.")
    return {
        "path": str(Path(path).resolve()),
        "sha256": sha256_file(path),
        "dxf_version": doc.dxfversion,
        "insunits": ins,
        "units": UNIT_NAMES.get(ins, f"code {ins}"),
        "extents": extents,
        "layouts": doc.layout_names(),
        "entity_counts": dict(Counter(e.dxftype() for e in entities)),
        "layers": layers,
        "blocks": sorted(b.name for b in doc.blocks if not b.name.startswith("*")),
        "text_entities": texts[:max_texts],
        "text_entities_total": len(texts),
        "warnings": warnings,
    }
