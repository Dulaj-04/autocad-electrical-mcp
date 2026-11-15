"""Project reports and audits for AutoCAD Electrical schematics (from aeschematic analyses).

Reports: bill of materials, components, terminals, wire numbers, wire from/to, parent/child
cross-reference. Audits: duplicate tags and terminals, children without a parent, missing catalog
data and descriptions, duplicate or missing wire numbers, unconnected pins, unpaired signal arrows,
missing or unreadable drawings. All read-only; Excel export writes one new workbook.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

REPORTS = ("bom", "components", "terminals", "wire_numbers", "from_to", "cross_reference")

COLUMNS: dict[str, list[str]] = {
    "bom": ["manufacturer", "catalog", "assembly", "description", "quantity", "tags"],
    "components": ["drawing", "tag", "kind", "family", "block", "description", "installation",
                   "location", "manufacturer", "catalog", "x", "y"],
    "terminals": ["drawing", "strip", "number", "installation", "location", "manufacturer",
                  "catalog", "wire_numbers", "connected_to"],
    "wire_numbers": ["drawing", "wire_number", "fixed", "net", "devices"],
    "from_to": ["drawing", "wire_number", "from", "to", "layer", "net"],
    "cross_reference": ["tag", "installation", "location", "parent_drawing", "parent_block",
                        "children", "child_count"],
}


def _key(c: dict[str, Any]) -> tuple[str, str, str]:
    return (c.get("installation", ""), c.get("location", ""), c.get("tag", ""))


def build(drawings: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    parents = [c for d in drawings for c in d["components"] if c["kind"] == "parent"]
    children = [c for d in drawings for c in d["components"] if c["kind"] == "child"]
    terms = [t for d in drawings for t in d["terminals"]]

    groups: dict[tuple, list[dict]] = defaultdict(list)
    for c in parents + terms:
        if c.get("manufacturer") or c.get("catalog"):
            groups[(c["manufacturer"], c["catalog"], c.get("assembly", ""))].append(c)
    bom = [{"manufacturer": k[0], "catalog": k[1], "assembly": k[2],
            "description": next((c["description"] for c in v if c["description"]), ""),
            "quantity": len(v),
            "tags": ", ".join(sorted(c.get("tag") or f"{c['strip']}:{c['number']}" for c in v))}
           for k, v in sorted(groups.items())]

    components = [{k: c.get(k, "") for k in COLUMNS["components"]} for c in parents + children]

    terminal_rows = []
    for d in drawings:
        nets = {n["net"]: n for n in d.get("nets", [])}
        for t in d["terminals"]:
            ref = f"{t['strip']}:{t['number']}"
            nset = sorted({k for p in t["pins"] for k in p.get("nets", [])})
            others = sorted({f"{p['device']}:{p['terminal'] or p['pin']}" for k in nset
                             for p in nets[k]["pins"] if p["device"] != ref})
            terminal_rows.append({"drawing": d["drawing"], "strip": t["strip"], "number": t["number"],
                                  "installation": t["installation"], "location": t["location"],
                                  "manufacturer": t["manufacturer"], "catalog": t["catalog"],
                                  "wire_numbers": ", ".join(sorted({w for k in nset
                                                                    for w in nets[k]["wire_numbers"]})),
                                  "connected_to": ", ".join(others)})

    wire_rows = []
    for d in drawings:
        nets = {n["net"]: n for n in d.get("nets", [])}
        for w in d["wire_numbers"]:
            devs = sorted({p["device"] for p in nets[w["net"]]["pins"]}) if w.get("net") else []
            wire_rows.append({"drawing": d["drawing"], "wire_number": w["wire_number"],
                              "fixed": "yes" if w["fixed"] else "", "net": w.get("net") or "",
                              "devices": ", ".join(devs)})

    from_to = [{k: r.get(k, "") for k in COLUMNS["from_to"]}
               for d in drawings for r in d.get("from_to", [])]

    by_tag: dict[str, list[dict]] = defaultdict(list)
    for c in children:
        by_tag[c["tag"]].append(c)
    xref = [{"tag": p["tag"], "installation": p["installation"], "location": p["location"],
             "parent_drawing": p["drawing"], "parent_block": p["block"],
             "children": ", ".join(f"{c['drawing']}:{c['block']}" for c in by_tag.get(p["tag"], [])),
             "child_count": len(by_tag.get(p["tag"], []))} for p in parents]
    return {"bom": bom, "components": components, "terminals": terminal_rows,
            "wire_numbers": wire_rows, "from_to": from_to, "cross_reference": xref}


def _issue(sev: str, code: str, msg: str, drawing: str | None = None,
           ref: str | None = None) -> dict[str, Any]:
    return {"severity": sev, "code": code, "message": msg, "drawing": drawing, "ref": ref}


def audit(drawings: list[dict[str, Any]], project: dict[str, Any] | None = None,
          unreadable: list[dict[str, Any]] | None = None, max_items: int = 300) -> dict[str, Any]:
    issues: list[dict[str, Any]] = []
    for path in (project or {}).get("missing", []):
        issues.append(_issue("error", "drawing_missing",
                             f"Listed in the project but not on disk: {path}", path))
    for u in unreadable or []:
        issues.append(_issue("warning", "drawing_unreadable", u["reason"], u["drawing"]))
    parents = [c for d in drawings for c in d["components"] if c["kind"] == "parent"]
    children = [c for d in drawings for c in d["components"] if c["kind"] == "child"]
    for d in drawings:
        if d["settings_block"] is None and (d["components"] or d["terminals"]):
            issues.append(_issue("info", "no_wd_m", "No WD_M block: the drawing is not set up as an "
                                 "AutoCAD Electrical drawing (or it was saved without it).",
                                 d["drawing"]))

    counts = Counter(_key(c) for c in parents if c["tag"])
    for (inst, loc, tag), n in sorted(counts.items()):
        if n > 1:
            where = sorted({c["drawing"] for c in parents if _key(c) == (inst, loc, tag)})
            issues.append(_issue("error", "duplicate_tag",
                                 f"Tag {tag} is used by {n} parent components"
                                 + (f" (INST {inst}, LOC {loc})" if inst or loc else "")
                                 + f" in {', '.join(where)}", where[0], tag))
    for c in parents:
        if not c["tag"]:
            issues.append(_issue("warning", "untagged_component",
                                 f"Component {c['block']} at {c['x']},{c['y']} has no tag",
                                 c["drawing"], c["handle"]))
    parent_tags = {c["tag"] for c in parents}
    for c in children:
        if c["tag"] and c["tag"] not in parent_tags:
            issues.append(_issue("warning", "child_without_parent",
                                 f"Child {c['block']} refers to {c['tag']}, which has no parent in "
                                 "the drawings read", c["drawing"], c["tag"]))
    for c in parents:
        if c["tag"] and not (c["manufacturer"] or c["catalog"]):
            issues.append(_issue("warning", "missing_catalog",
                                 f"{c['tag']} has no manufacturer/catalog: it will be missing from "
                                 "the BOM", c["drawing"], c["tag"]))
        if c["tag"] and not c["description"]:
            issues.append(_issue("info", "missing_description", f"{c['tag']} has no description",
                                 c["drawing"], c["tag"]))
    tcount = Counter((t["installation"], t["location"], t["strip"], t["number"])
                     for d in drawings for t in d["terminals"] if t["number"])
    for (inst, loc, strip, num), n in sorted(tcount.items()):
        if n > 1:
            issues.append(_issue("error", "duplicate_terminal",
                                 f"Terminal {strip}:{num} appears {n} times", None, f"{strip}:{num}"))

    owners: dict[str, set[tuple[str, int]]] = defaultdict(set)
    for d in drawings:
        for w in d["wire_numbers"]:
            if w.get("net"):
                owners[w["wire_number"]].add((d["drawing"], w["net"]))
        for nk in d.get("nets", []):
            if len({p["device"] for p in nk["pins"]}) >= 2 and not nk["wire_numbers"]:
                issues.append(_issue("warning", "unnumbered_wire",
                                     f"Wire network {nk['net']} joins "
                                     f"{', '.join(sorted({p['device'] for p in nk['pins']}))} "
                                     "but has no wire number", d["drawing"], f"net {nk['net']}"))
            if len(nk["wire_numbers"]) > 1:
                issues.append(_issue("warning", "several_wire_numbers",
                                     f"Wire network {nk['net']} carries several wire numbers: "
                                     f"{', '.join(nk['wire_numbers'])}", d["drawing"],
                                     f"net {nk['net']}"))
        for w in d.get("wire_numbers_off_wire", []):
            issues.append(_issue("info", "wire_number_off_wire",
                                 f"Wire number {w} is not on a wire line", d["drawing"], w))
        for p in d.get("unconnected_pins", []):
            issues.append(_issue("info", "unconnected_pin",
                                 f"{p['device']} pin {p['terminal'] or p['pin']} has no wire "
                                 "(fine for a spare contact)", d["drawing"], p["device"]))
    for num, where in sorted(owners.items()):
        if len(where) > 1:
            dwgs = sorted({w[0] for w in where})
            sev = "error" if len(dwgs) == 1 else "warning"
            issues.append(_issue(sev, "duplicate_wire_number",
                                 f"Wire number {num} is on {len(where)} separate networks in "
                                 f"{', '.join(dwgs)}" + ("" if sev == "error" else
                                                          " (fine only if joined by signal arrows)"),
                                 dwgs[0], num))
    sig = Counter(s["code"] for d in drawings for s in d["signals"] if s["code"])
    for code, n in sorted(sig.items()):
        if n == 1:
            where = next(d["drawing"] for d in drawings for s in d["signals"] if s["code"] == code)
            issues.append(_issue("warning", "unpaired_signal",
                                 f"Signal arrow {code} has no partner source/destination",
                                 where, code))
    order = {"error": 0, "warning": 1, "info": 2}
    issues.sort(key=lambda i: (order[i["severity"]], i["code"], str(i["drawing"]), str(i["ref"])))
    by = Counter(i["severity"] for i in issues)
    by_code = Counter(i["code"] for i in issues)
    return {"errors": by.get("error", 0), "warnings": by.get("warning", 0), "info": by.get("info", 0),
            "by_code": dict(sorted(by_code.items())), "issues": issues[:max_items],
            "truncated": len(issues) > max_items,
            "note": "Wire networks are derived from geometry; confirm wiring findings with AutoCAD "
                    "Electrical's own reports before acting on them."}


def export_xlsx(path: Path, reports: dict[str, list[dict[str, Any]]],
                issues: list[dict[str, Any]] | None = None, meta: dict[str, Any] | None = None) -> str:
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill

    wb = Workbook()
    info = wb.active
    info.title = "Info"
    rows = [("AutoCAD Electrical project reports", ""), ("Status", "DRAFT: generated from drawing data; "
            "wire from/to is derived from geometry")]
    rows += [(k, str(v)) for k, v in (meta or {}).items()]
    for r in rows:
        info.append(list(r))
    info["A1"].font = Font(bold=True, size=13)
    info.column_dimensions["A"].width, info.column_dimensions["B"].width = 22, 90
    sheets = dict(reports)
    if issues is not None:
        sheets["audit"] = issues
        COLUMNS.setdefault("audit", ["severity", "code", "message", "drawing", "ref"])
    for name, data in sheets.items():
        ws = wb.create_sheet(name[:31])
        cols = COLUMNS[name]
        ws.append(cols)
        for c in ws[1]:
            c.font = Font(bold=True)
            c.fill = PatternFill("solid", fgColor="DDDDDD")
        for row in data:
            ws.append([row.get(k, "") for k in cols])
        ws.freeze_panes = "A2"
        if data:
            ws.auto_filter.ref = ws.dimensions
        for i, k in enumerate(cols, 1):
            width = max([len(k)] + [len(str(r.get(k, ""))) for r in data[:500]])
            ws.column_dimensions[ws.cell(1, i).column_letter].width = min(max(width + 2, 8), 60)
    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)
    return str(path)
