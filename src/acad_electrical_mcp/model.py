"""Canonical floor model and its on-disk store.

One JSON model per project/floor is the single source of truth. All drawing views
are generated from it, so discipline views and the combined view always agree.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

from .config import safe_name
from .template import new_template

DEVICE_FIELDS = ("id", "type", "x", "y", "rotation", "room", "circuit", "db", "note")


def sha256_file(path: str | Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_obj(obj: Any) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True).encode()).hexdigest()


def empty_model(project: str, floor: str) -> dict[str, Any]:
    return {
        "project": project,
        "floor": floor,
        "revision": 0,
        "status": "DRAFT",
        "units": None,
        "source": None,  # {"path", "sha256"} of the architectural reference
        "rooms": [],  # {"id","name","bounds":[minx,miny,maxx,maxy]}
        "devices": [],  # see DEVICE_FIELDS
        "circuits": [],  # {"id","kind","db"}
        "routes": [],  # {"id","kind","circuit","db","points","device_ids"}
        "template": new_template(),
        "outputs": {},  # file name -> sha256 recorded when generated
    }


class Store:
    def __init__(self, workspace: Path):
        self.root = workspace

    # ---- paths -------------------------------------------------------------
    def floor_dir(self, project: str, floor: str) -> Path:
        return self.root / safe_name(project, "project") / safe_name(floor, "floor")

    def output_dir(self, project: str, floor: str) -> Path:
        return self.root / safe_name(project, "project") / "output" / safe_name(floor, "floor")

    def _model_path(self, project: str, floor: str) -> Path:
        return self.floor_dir(project, floor) / "model.json"

    # ---- model -------------------------------------------------------------
    def exists(self, project: str, floor: str) -> bool:
        return self._model_path(project, floor).exists()

    def load(self, project: str, floor: str, create: bool = False) -> dict[str, Any]:
        p = self._model_path(project, floor)
        if not p.exists():
            if not create:
                raise FileNotFoundError(
                    f"No model for {project}/{floor}. Run prepare_floor_model first."
                )
            return empty_model(project, floor)
        return json.loads(p.read_text())

    def save(self, model: dict[str, Any]) -> None:
        p = self._model_path(model["project"], model["floor"])
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps(model, indent=2, sort_keys=True))
        tmp.replace(p)

    # ---- history (undo) ----------------------------------------------------
    def snapshot(self, model: dict[str, Any]) -> None:
        d = self.floor_dir(model["project"], model["floor"]) / "history"
        d.mkdir(parents=True, exist_ok=True)
        (d / f"rev_{model['revision']:04d}.json").write_text(json.dumps(model, indent=2))

    def last_snapshot(self, project: str, floor: str) -> Path | None:
        d = self.floor_dir(project, floor) / "history"
        snaps = sorted(d.glob("rev_*.json")) if d.exists() else []
        return snaps[-1] if snaps else None

    # ---- changesets --------------------------------------------------------
    def _cs_dir(self, project: str, floor: str) -> Path:
        return self.floor_dir(project, floor) / "changesets"

    def save_changeset(self, cs: dict[str, Any]) -> None:
        d = self._cs_dir(cs["project"], cs["floor"])
        d.mkdir(parents=True, exist_ok=True)
        (d / f"{cs['id']}.json").write_text(json.dumps(cs, indent=2))

    def load_changeset(self, project: str, floor: str, cs_id: str) -> dict[str, Any]:
        p = self._cs_dir(project, floor) / f"{safe_name(cs_id, 'changeset id')}.json"
        if not p.exists():
            raise FileNotFoundError(f"Unknown changeset {cs_id!r}")
        return json.loads(p.read_text())

    def delete_changeset(self, project: str, floor: str, cs_id: str) -> None:
        p = self._cs_dir(project, floor) / f"{safe_name(cs_id, 'changeset id')}.json"
        p.unlink(missing_ok=True)

    def wipe_floor(self, project: str, floor: str) -> None:
        shutil.rmtree(self.floor_dir(project, floor), ignore_errors=True)
