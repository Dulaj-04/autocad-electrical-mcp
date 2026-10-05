"""Deterministic, floor-prefixed device identifiers (e.g. 4F-L01, DB-4F)."""

from __future__ import annotations

# device type -> (id prefix, drawing layer, route kind)
DEVICE_TYPES: dict[str, tuple[str, str, str | None]] = {
    "luminaire": ("L", "LIGHTING", "lighting"),
    "switch": ("S", "SWITCHES", "lighting"),
    "socket": ("P", "SOCKETS", "power"),
    "data": ("D", "DATA", "power"),
    "ac": ("AC", "AC", "ac"),
    "emergency": ("E", "EMERGENCY", "lighting"),
    "db": ("DB", "DB", None),
}

ROUTE_LAYERS = {"lighting": "LIGHT_WIRING", "power": "POWER_WIRING", "ac": "AC_WIRING"}


def next_device_id(floor: str, dtype: str, existing_ids: set[str]) -> str:
    if dtype not in DEVICE_TYPES:
        raise ValueError(f"Unknown device type {dtype!r}; expected one of {sorted(DEVICE_TYPES)}")
    if dtype == "db":
        return f"DB-{floor}"
    prefix = DEVICE_TYPES[dtype][0]
    n = 1
    while f"{floor}-{prefix}{n:02d}" in existing_ids:
        n += 1
    return f"{floor}-{prefix}{n:02d}"


def route_id(circuit_id: str) -> str:
    return f"R-{circuit_id}"
