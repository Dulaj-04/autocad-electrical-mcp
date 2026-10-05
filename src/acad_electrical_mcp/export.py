"""Generate views and export packages (DXF, DWG when available, PNG, PDF, manifest)."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import ezdxf

from .backends import BackendError, make_backend
from .model import sha256_file
from .template import VIEWS
from .validate import validate_floor
from .views import check_source, render_view


def view_filename(floor: str, view: str, ext: str) -> str:
    return f"{floor}_{VIEWS[view][0]}.{ext}"


def _base_path(model: dict[str, Any]) -> str | None:
    src = model.get("source")
    return src["path"] if src else None


def manual_edit_conflicts(model: dict[str, Any], out_dir: Path) -> list[str]:
    bad = []
    for name, digest in model.get("outputs", {}).items():
        p = out_dir / name
        if p.exists() and sha256_file(p) != digest:
            bad.append(name)
    return bad


def generate_dxf_views(
    model: dict[str, Any], out_dir: Path, backend_name: str,
    views: list[str] | None = None, overwrite_manual_edits: bool = False,
    try_dwg: bool = False,
) -> list[dict[str, Any]]:
    views = views or list(VIEWS)
    check_source(model)
    edited = manual_edit_conflicts(model, out_dir)
    if edited and not overwrite_manual_edits:
        raise BackendError(
            f"Manual edits detected in {edited}. Run sync_from_drawing to adopt them, or pass "
            "overwrite_manual_edits=true to discard them."
        )
    results = []
    for view in views:
        backend = make_backend(backend_name)
        try:
            info = render_view(backend, model, view, _base_path(model))
            dxf = out_dir / view_filename(model["floor"], view, "dxf")
            backend.save_dxf(dxf)
            model["outputs"][dxf.name] = sha256_file(dxf)
            entry = {"view": view, "dxf": str(dxf), **info}
            if try_dwg:
                dwg = out_dir / view_filename(model["floor"], view, "dwg")
                try:
                    backend.save_dwg(dwg)
                    entry["dwg"] = str(dwg)
                except BackendError as exc:
                    entry["dwg"] = None
                    entry["dwg_skipped"] = str(exc)
        finally:
            backend.close()
        results.append(entry)
    return results


def render_image(dxf: Path, out: Path, dark: bool = True, size_in: tuple[float, float] = (16, 11)):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from ezdxf.addons.drawing import Frontend, RenderContext, config
    from ezdxf.addons.drawing.matplotlib import MatplotlibBackend

    doc = ezdxf.readfile(str(dxf))
    bg = "#1e1e1e" if dark else "#ffffff"
    cfg = config.Configuration(
        background_policy=config.BackgroundPolicy.CUSTOM, custom_bg_color=bg,
    )
    fig = plt.figure(figsize=size_in)
    ax = fig.add_axes([0.01, 0.01, 0.98, 0.98])
    Frontend(RenderContext(doc), MatplotlibBackend(ax), config=cfg).draw_layout(doc.modelspace())
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(str(out), dpi=150, facecolor=bg)
    plt.close(fig)


def export_package(
    model: dict[str, Any], out_dir: Path, backend_name: str, views: list[str] | None = None,
    overwrite_manual_edits: bool = False,
) -> dict[str, Any]:
    views = views or list(VIEWS)
    gen = generate_dxf_views(model, out_dir, backend_name, views, overwrite_manual_edits,
                             try_dwg=True)
    files: list[dict[str, Any]] = []
    skipped: list[dict[str, str]] = []
    for g in gen:
        view = g["view"]
        dxf = Path(g["dxf"])
        files.append(_entry(view, "dxf", dxf))
        if g.get("dwg"):
            files.append(_entry(view, "dwg", Path(g["dwg"])))
        else:
            skipped.append({"view": view, "format": "dwg",
                            "reason": g.get("dwg_skipped", "not requested")})
        png = out_dir / view_filename(model["floor"], view, "png")
        render_image(dxf, png, dark=True)
        files.append(_entry(view, "png", png))
        if view != "architectural":
            pdf = out_dir / view_filename(model["floor"], view, "pdf")
            render_image(dxf, pdf, dark=False, size_in=(16.54, 11.69))  # A3 landscape
            files.append(_entry(view, "pdf", pdf))
    validation = validate_floor(model, out_dir, views)
    manifest = {
        "project": model["project"], "floor": model["floor"], "revision": model["revision"],
        "status": model["template"].get("status", "DRAFT"),
        "generated": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "backend": backend_name,
        "source": model.get("source"),
        "files": files, "skipped": skipped,
        "validation": {k: validation[k] for k in ("ok", "errors", "warnings", "files")},
        "note": "Draft drawing package. Engineering approval is a separate process.",
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2))
    manifest["manifest_path"] = str(out_dir / "manifest.json")
    return manifest


def _entry(view: str, fmt: str, path: Path) -> dict[str, Any]:
    return {"view": view, "format": fmt, "path": str(path), "bytes": path.stat().st_size,
            "sha256": sha256_file(path)}
