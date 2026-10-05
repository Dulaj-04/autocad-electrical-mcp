from __future__ import annotations

from .base import BackendError, DrawingBackend


def make_backend(name: str) -> DrawingBackend:
    if name == "dxf":
        from .dxf_backend import DxfBackend

        return DxfBackend()
    if name == "autocad":
        from .autocad_backend import AutoCadBackend

        return AutoCadBackend()
    raise BackendError(f"Unknown backend {name!r}; use 'dxf' or 'autocad'.")


__all__ = ["BackendError", "DrawingBackend", "make_backend"]
