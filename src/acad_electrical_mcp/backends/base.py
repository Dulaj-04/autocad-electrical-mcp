"""Drawing backend interface.

A backend turns drawing primitives into a saved drawing. ``dxf`` runs offline with
ezdxf; ``autocad`` drives a live AutoCAD Electrical session through COM.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path


class BackendError(RuntimeError):
    pass


class DrawingBackend(ABC):
    name = "base"

    @abstractmethod
    def begin(self, base: str | None) -> None:
        """Start a working drawing from an architectural base file (or blank)."""

    @abstractmethod
    def units(self) -> int:
        """DXF $INSUNITS code of the working drawing (0 = unitless/undeclared)."""

    @abstractmethod
    def bounds(self) -> tuple[float, float, float, float] | None:
        """Extents (minx, miny, maxx, maxy) of existing geometry, or None."""

    @abstractmethod
    def ensure_layer(self, name: str, color: int, lineweight: int) -> None: ...

    @abstractmethod
    def define_symbols(self, size: float, text_height: float) -> None: ...

    @abstractmethod
    def insert_device(
        self, dtype: str, layer: str, x: float, y: float, rotation: float,
        attribs: dict[str, str],
    ) -> None: ...

    @abstractmethod
    def add_polyline(self, layer: str, points: list[tuple[float, float]]) -> None: ...

    @abstractmethod
    def add_rect(self, layer: str, bounds: tuple[float, float, float, float]) -> None: ...

    @abstractmethod
    def add_text(
        self, layer: str, text: str, x: float, y: float, height: float, bold: bool = False
    ) -> None: ...

    @abstractmethod
    def save_dxf(self, path: Path) -> None: ...

    def save_dwg(self, path: Path) -> None:
        raise BackendError("DWG export is not supported by this backend.")

    def close(self) -> None:  # pragma: no cover - optional
        pass
