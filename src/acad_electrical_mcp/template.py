"""Default drawing template: layer vocabulary, colours, lineweights, text sizes.

Based on the benchmark layer set. Colours are AutoCAD Color Index (ACI) values and
every property can be overridden through ``prepare_template``.
"""

from __future__ import annotations

import copy
from typing import Any

# name: (aci colour, lineweight in 1/100 mm, description)
DEFAULT_LAYERS: dict[str, tuple[int, int, str]] = {
    "Wall": (7, 50, "Architectural walls"),
    "Doors": (3, 25, "Doors"),
    "Lift": (8, 25, "Lift shafts"),
    "Stairs": (8, 25, "Stairs"),
    "FURNITURE": (9, 13, "Floor-specific furnishings"),
    "TEXT": (7, 13, "Room names and architectural text"),
    "LIGHTING": (2, 35, "Luminaire symbols (yellow)"),
    "SWITCHES": (2, 35, "Switching symbols"),
    "LIGHT_WIRING": (1, 25, "Lighting routes (red)"),
    "SOCKETS": (6, 35, "Socket symbols (magenta)"),
    "POWER_WIRING": (5, 25, "General power routes (blue)"),
    "DATA": (4, 35, "Data outlet symbols (cyan)"),
    "AC": (6, 35, "AC provisions"),
    "AC_WIRING": (6, 25, "Dedicated AC routes (magenta)"),
    "DB": (3, 50, "Distribution boards"),
    "EMERGENCY": (3, 35, "Exit / emergency provisions (green)"),
    "NOTES": (7, 18, "Titles, legend and status notes"),
}

ARCH_LAYERS = ("Wall", "Doors", "Lift", "Stairs", "FURNITURE", "TEXT")

# view name -> (file suffix, layers drawn, title)
VIEWS: dict[str, tuple[str, tuple[str, ...], str]] = {
    "architectural": ("Architectural_Base", (), "ARCHITECTURAL BASE"),
    "lighting": (
        "Lighting_Design",
        ("LIGHTING", "SWITCHES", "LIGHT_WIRING", "EMERGENCY", "DB"),
        "LIGHTING DESIGN",
    ),
    "power": (
        "Power_Socket_AC_Design",
        ("SOCKETS", "POWER_WIRING", "DATA", "AC", "AC_WIRING", "DB"),
        "POWER / SOCKET / AC DESIGN",
    ),
    "combined": (
        "Electrical_Complete",
        (
            "LIGHTING", "SWITCHES", "LIGHT_WIRING", "EMERGENCY", "DB",
            "SOCKETS", "POWER_WIRING", "DATA", "AC", "AC_WIRING",
        ),
        "ELECTRICAL COMPLETE",
    ),
}

DEFAULT_TEMPLATE: dict[str, Any] = {
    "layers": {k: {"color": v[0], "lineweight": v[1], "description": v[2]}
               for k, v in DEFAULT_LAYERS.items()},
    "symbol_size": None,  # drawing units; None = derive from drawing extents
    "text_height": None,  # None = derive from symbol size
    "status": "DRAFT",
    "title_block": {"project": "", "drawn_by": "", "notes": []},
}


def new_template() -> dict[str, Any]:
    return copy.deepcopy(DEFAULT_TEMPLATE)


def merge_template(base: dict[str, Any], overrides: dict[str, Any]) -> dict[str, Any]:
    out = copy.deepcopy(base)
    for key, val in overrides.items():
        if key == "layers":
            for name, props in val.items():
                out["layers"].setdefault(name, {"color": 7, "lineweight": 25, "description": ""})
                out["layers"][name].update(props)
        elif key == "title_block":
            out["title_block"].update(val)
        elif key in out:
            out[key] = val
        else:
            raise ValueError(f"Unknown template key {key!r}")
    return out
