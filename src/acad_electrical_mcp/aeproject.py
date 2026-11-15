"""Read an AutoCAD Electrical project file (.wdp) without AutoCAD.

A .wdp file is plain text: project description lines, project settings, and the list of drawing
files, each optionally preceded by lines that carry its description, section and sub-section.
Since AutoCAD Electrical 2016 the file is Unicode; older projects are ANSI.

The parser is deliberately tolerant. Line markers it knows:

* ``*[n]text``  project description line n
* ``+[n]text``  project setting n
* ``?[n]text``  project property n
* ``=...``      a drawing attribute for the NEXT drawing in the list: ``=====SEC=..``,
                ``=====SUB=..`` (section, sub-section), ``=====KEY=value`` (other property),
                or any other ``=``-prefixed text (a description line)
* a line ending in ``.dwg`` / ``.dxf``  a drawing file (relative to the .wdp folder unless absolute)

Anything else is returned under ``unrecognised`` with its line number instead of being guessed at,
so a format difference in your version shows up instead of being silently dropped.
"""

from __future__ import annotations

import os
import re
from pathlib import Path, PureWindowsPath
from typing import Any

_PREFIXED = re.compile(r"^([*+?])\[(\d+)\](.*)$")
_EQ = re.compile(r"^(=+)(.*)$")
_KV = re.compile(r"^([A-Za-z][A-Za-z0-9_]*)=(.*)$")
DRAWING_EXT = (".dwg", ".dxf")


def read_text(path: Path) -> tuple[str, str]:
    """Decode a .wdp: UTF-16 / UTF-8 with or without BOM, else ANSI (cp1252)."""
    raw = path.read_bytes()
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        return raw.decode("utf-16"), "utf-16"
    if raw.startswith(b"\xef\xbb\xbf"):
        return raw[3:].decode("utf-8"), "utf-8-sig"
    if len(raw) > 3 and raw[1:2] == b"\x00" and raw[3:4] == b"\x00":
        return raw.decode("utf-16-le"), "utf-16-le"
    try:
        return raw.decode("utf-8"), "utf-8"
    except UnicodeDecodeError:
        return raw.decode("cp1252", errors="replace"), "cp1252"


def _resolve(folder: Path, entry: str) -> Path:
    win = PureWindowsPath(entry)
    if win.is_absolute() or entry.startswith(("/", "\\\\")):
        p = Path(entry)
        if p.exists():
            return p
        # an absolute Windows path read on another machine: try the file name next to the .wdp
        local = folder / win.name
        return local if local.exists() else p
    return folder / Path(*win.parts)


def parse(path: str) -> dict[str, Any]:
    p = Path(path)
    if not p.is_file():
        raise ValueError(f"Project file not found: {path}")
    if p.suffix.lower() != ".wdp":
        raise ValueError(f"{p.name} is not a .wdp project file")
    text, encoding = read_text(p)
    folder = p.parent
    description: dict[int, str] = {}
    settings: dict[int, str] = {}
    properties: dict[int, str] = {}
    drawings: list[dict[str, Any]] = []
    unrecognised: list[dict[str, Any]] = []
    pending: dict[str, Any] = {"descriptions": [], "section": None, "subsection": None,
                               "properties": {}}
    for no, line in enumerate(text.splitlines(), 1):
        s = line.strip().strip("\x00")
        if not s or s.startswith(";"):
            continue
        m = _PREFIXED.match(s)
        if m:
            kind, n, val = m.group(1), int(m.group(2)), m.group(3)
            {"*": description, "+": settings, "?": properties}[kind][n] = val
            continue
        m = _EQ.match(s)
        if m:
            body = m.group(2)
            kv = _KV.match(body)
            if kv:
                key, val = kv.group(1).upper(), kv.group(2)
                if key == "SEC":
                    pending["section"] = val
                elif key == "SUB":
                    pending["subsection"] = val
                else:
                    pending["properties"][key] = val
            else:
                pending["descriptions"].append(body)
            continue
        if s.lower().endswith(DRAWING_EXT):
            resolved = _resolve(folder, s)
            drawings.append({"index": len(drawings) + 1, "file": s, "name": PureWindowsPath(s).name,
                             "path": str(resolved), "exists": resolved.exists(), **pending})
            pending = {"descriptions": [], "section": None, "subsection": None, "properties": {}}
            continue
        unrecognised.append({"line": no, "text": s[:200]})
    names = [d["name"].lower() for d in drawings]
    dups = sorted({n for n in names if names.count(n) > 1})
    warnings = []
    missing = [d["file"] for d in drawings if not d["exists"]]
    if missing:
        warnings.append(f"{len(missing)} drawing(s) listed in the project are not on disk: "
                        f"{', '.join(missing[:10])}")
    if dups:
        warnings.append(f"Drawing listed more than once: {', '.join(dups)}")
    if any(pending.values()):
        warnings.append("Description/section lines at the end of the file belong to no drawing.")
    if unrecognised:
        warnings.append(f"{len(unrecognised)} line(s) not recognised; see 'unrecognised'. Share "
                        "them so the reader can be extended for your version.")
    return {
        "project": p.stem, "path": str(p.resolve()), "encoding": encoding,
        "description": [description[k] for k in sorted(description)],
        "settings": {str(k): v for k, v in sorted(settings.items())},
        "properties": {str(k): v for k, v in sorted(properties.items())},
        "drawings": drawings, "drawing_count": len(drawings), "missing": missing,
        "duplicates": dups, "unrecognised": unrecognised[:100], "warnings": warnings,
        "note": "Read-only. Settings are reported by their +[n]/?[n] index; their meaning depends "
                "on your AutoCAD Electrical version.",
    }


def drawing_paths(target: str) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    """Drawings to read for a target: a .wdp project, one .dxf/.dwg, or a folder of them."""
    p = Path(target)
    if p.is_file() and p.suffix.lower() == ".wdp":
        proj = parse(target)
        return proj["drawings"], proj
    if p.is_file() and p.suffix.lower() in DRAWING_EXT:
        return [{"index": 1, "file": p.name, "name": p.name, "path": str(p), "exists": True,
                 "descriptions": [], "section": None, "subsection": None, "properties": {}}], None
    if p.is_dir():
        files = sorted(f for f in p.iterdir() if f.suffix.lower() in DRAWING_EXT
                       and not f.name.startswith(("~", ".")))
        return [{"index": i + 1, "file": f.name, "name": f.name, "path": str(f), "exists": True,
                 "descriptions": [], "section": None, "subsection": None, "properties": {}}
                for i, f in enumerate(files)], None
    raise ValueError(f"Not a .wdp project, a .dxf/.dwg drawing or a folder: {target}")


def norm(path: str) -> str:
    return os.path.normcase(os.path.abspath(path))
