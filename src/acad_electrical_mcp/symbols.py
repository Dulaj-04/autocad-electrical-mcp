"""Plan-level symbol geometry in the style of the reference drawings (plain LINEs).

Sizes are given in millimetres (width, height) and scaled to the drawing's units.
Segments are returned centred on (0, 0) as ((x1, y1), (x2, y2)) tuples.
"""

from __future__ import annotations

import math

Seg = tuple[tuple[float, float], tuple[float, float]]

# device type -> (width, height) in mm, taken from the reference floor drawings
SIZES_MM: dict[str, tuple[float, float]] = {
    "luminaire": (600, 600),
    "switch": (140, 360),
    "socket": (360, 280),
    "data": (360, 280),
    "ac": (1300, 450),
    "emergency": (1200, 300),
    "db": (600, 800),
}


def _rect(w: float, h: float) -> list[Seg]:
    a, b = w / 2, h / 2
    pts = [(-a, -b), (a, -b), (a, b), (-a, b)]
    return [(pts[i], pts[(i + 1) % 4]) for i in range(4)]


def _ngon(r: float, n: int = 8) -> list[Seg]:
    pts = [(r * math.cos(2 * math.pi * i / n), r * math.sin(2 * math.pi * i / n)) for i in range(n)]
    return [(pts[i], pts[(i + 1) % n]) for i in range(n)]


def symbol_segments(dtype: str, scale: float = 1.0, rotation: float = 0.0) -> list[Seg]:
    if dtype not in SIZES_MM:
        raise ValueError(f"No symbol for device type {dtype!r}; expected {sorted(SIZES_MM)}")
    w, h = (v * scale for v in SIZES_MM[dtype])
    a, b = w / 2, h / 2
    segs = _rect(w, h)
    if dtype == "luminaire":  # square with both diagonals
        segs += [((-a, -b), (a, b)), ((-a, b), (a, -b))]
    elif dtype == "switch":  # small circle with a stem
        r = w / 2
        segs = _ngon(r) + [((0, r), (0, b))]
    elif dtype == "socket":  # plate with a centre socket mark
        segs += _rect(w * 0.2, h * 0.32)
    elif dtype == "data":  # plate with a diagonal
        segs += [((-a, -b), (a, b))]
    elif dtype == "ac":  # box with a centre divider
        segs += [((0, -b), (0, b))]
    elif dtype == "emergency":  # box with an arrow
        segs += [((-a * 0.7, 0), (a * 0.7, 0)), ((a * 0.7, 0), (a * 0.4, b * 0.6)),
                 ((a * 0.7, 0), (a * 0.4, -b * 0.6))]
    elif dtype == "db":  # board with both diagonals
        segs += [((-a, -b), (a, b)), ((-a, b), (a, -b))]
    if rotation:
        c, s = math.cos(math.radians(rotation)), math.sin(math.radians(rotation))
        segs = [((p[0] * c - p[1] * s, p[0] * s + p[1] * c),
                 (q[0] * c - q[1] * s, q[0] * s + q[1] * c)) for p, q in segs]
    return segs
