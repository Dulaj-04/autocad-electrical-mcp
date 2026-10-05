"""A tiny synthetic architectural floor (millimetres) for trying the server and for tests."""

from __future__ import annotations

import json

import ezdxf

ROOMS = [
    {"id": "4-A", "name": "OFFICE", "bounds": [0, 0, 6000, 5000]},
    {"id": "4-B", "name": "MEETING ROOM", "bounds": [6000, 0, 10000, 5000]},
    {"id": "4-C", "name": "CORRIDOR", "bounds": [0, 5000, 10000, 7000]},
]


def make_sample_floor(path: str) -> str:
    doc = ezdxf.new("R2018", setup=True)
    doc.units = 4  # millimetres
    for name, color in (("Wall", 7), ("Doors", 3), ("TEXT", 7), ("FURNITURE", 9)):
        doc.layers.add(name, color=color)
    msp = doc.modelspace()
    for r in ROOMS:
        x0, y0, x1, y1 = r["bounds"]
        msp.add_lwpolyline([(x0, y0), (x1, y0), (x1, y1), (x0, y1)], close=True,
                           dxfattribs={"layer": "Wall"})
        msp.add_text(r["name"], height=250, dxfattribs={"layer": "TEXT"}).set_placement(
            (x0 + 300, y1 - 600))
    msp.add_line((2500, 5000), (3300, 5000), dxfattribs={"layer": "Doors"})
    msp.add_lwpolyline([(500, 500), (2500, 500), (2500, 1200), (500, 1200)], close=True,
                       dxfattribs={"layer": "FURNITURE"})
    doc.saveas(path)
    return json.dumps({"written": path, "rooms": ROOMS})
