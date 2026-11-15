"""AutoCAD Electrical project reading, schematic analysis, reports, audits and install capture."""

import asyncio
import json

import ezdxf
import openpyxl
import pytest

from acad_electrical_mcp import aecapture, aeproject, aeschematic, server
from acad_electrical_mcp.live import LiveSession, PlainCom
from acad_electrical_mcp.model import Store
from acad_electrical_mcp.schematic import Schematic
from fake_acad import App

# component blocks: (block, insert, attributes, {attribute: point})
DWG1 = [
    ("WD_M", (0, 0), {"WD_LADDER": "1"}, {}),
    ("HPB11", (0, 10), {"TAG1": "PB1", "DESC1": "START", "MFG": "ABB", "CAT": "CP1-10",
                        "TERM01": "13", "TERM02": "14", "X4TERM01": "", "X1TERM02": ""},
     {"X4TERM01": (-2, 10), "X1TERM02": (2, 10)}),
    ("HCR1", (10, 10), {"TAG1": "K1", "DESC1": "MOTOR", "DESC2": "CONTACTOR", "MFG": "AB",
                        "CAT": "100-C09", "TERM01": "A1", "TERM02": "A2", "X4TERM01": "",
                        "X1TERM02": ""}, {"X4TERM01": (8, 10), "X1TERM02": (12, 10)}),
    ("VLT1", (5, 0), {"TAG1": "LT1", "DESC1": "RUN", "TERM01": "X1", "X2TERM01": ""},
     {"X2TERM01": (5, 0)}),
    ("HT0001", (-10, 10), {"TAGSTRIP": "TB1", "TERM01": "1", "MFG": "PHX", "CAT": "UT2.5",
                           "X1TERM01": ""}, {"X1TERM01": (-10, 10)}),
    ("WD_WNH", (5, 10), {"WIRENO": "101"}, {}),
    ("WD_WNH", (25, 20), {"WIRENO": "101"}, {}),
    ("HPB11", (40, 40), {"TAG1": "PB1", "DESC1": "SPARE", "MFG": "ABB", "CAT": "CP1-10"}, {}),
    ("HA1S1", (50, 50), {"SIGCODE": "S1"}, {}),
]
LINES1 = [((2, 10), (8, 10)), ((5, 10), (5, 0)), ((-10, 10), (-2, 10)), ((20, 20), (30, 20))]
DWG2 = [
    ("WD_M", (0, 0), {}, {}),
    ("HCR2", (0, 0), {"TAG2": "K1", "TERM01": "13", "TERM02": "14"}, {}),
    ("HCR2", (5, 0), {"TAG2": "K9", "TERM01": "13"}, {}),
]


def _write_dxf(path, blocks, lines):
    doc = ezdxf.new()
    msp = doc.modelspace()
    for name, ins, attrs, pts in blocks:
        if name not in doc.blocks:
            doc.blocks.new(name)
        ref = msp.add_blockref(name, ins)
        for tag, val in attrs.items():
            ref.add_attrib(tag, val, insert=pts.get(tag, ins))
    for a, b in lines:
        msp.add_line(a, b, dxfattribs={"layer": "WIRES"})
    doc.saveas(path)


@pytest.fixture()
def proj(tmp_path, monkeypatch):
    ws = tmp_path / "ws"
    monkeypatch.setattr(server.CFG, "workspace", ws)
    monkeypatch.setattr(server, "STORE", Store(ws))
    _write_dxf(tmp_path / "dwg1.dxf", DWG1, LINES1)
    _write_dxf(tmp_path / "dwg2.dxf", DWG2, [])
    wdp = tmp_path / "DEMO.wdp"
    text = ("*[1]Demo machine\n*[2]Second line\n+[1]1\n?[1]Customer\n=====SEC=01\n=====SUB=A\n"
            "===Main power\ndwg1.dxf\n===Controls\ndwg2.dxf\nMISSING.dwg\nsomething odd\n")
    wdp.write_bytes(b"\xff\xfe" + text.encode("utf-16-le"))
    return tmp_path, wdp


def test_wdp_parse(proj):
    _, wdp = proj
    p = aeproject.parse(str(wdp))
    assert p["encoding"] == "utf-16" and p["description"] == ["Demo machine", "Second line"]
    assert p["settings"] == {"1": "1"} and p["properties"] == {"1": "Customer"}
    d1, d2, d3 = p["drawings"]
    assert (d1["section"], d1["subsection"], d1["descriptions"]) == ("01", "A", ["Main power"])
    assert d2["descriptions"] == ["Controls"] and d2["section"] is None
    assert d1["exists"] and not d3["exists"] and p["missing"] == ["MISSING.dwg"]
    assert p["unrecognised"] == [{"line": 12, "text": "something odd"}]


def test_networks_pins_and_from_to(proj):
    tmp, _ = proj
    d = aeschematic.analyse(aeschematic.raw_from_dxf(str(tmp / "dwg1.dxf")), tolerance=0.01)
    k1 = next(c for c in d["components"] if c["tag"] == "K1")
    assert k1["family"] == "CR" and k1["description"] == "MOTOR CONTACTOR"
    assert [p["pin"] for p in k1["pins"]] == ["01", "02"]
    net = next(n for n in d["nets"] if n["wire_numbers"] == ["101"] and n["pins"])
    assert {p["device"] for p in net["pins"]} == {"PB1", "K1", "LT1"}  # includes the T-junction
    rows = [r for r in d["from_to"] if r["net"] == net["net"]]
    assert len(rows) == 2 and all(r["wire_number"] == "101" for r in rows)
    assert {"device": "K1", "pin": "02", "terminal": "A2"} in d["unconnected_pins"]
    tb = next(n for n in d["nets"] if any(p["device"] == "TB1:1" for p in n["pins"]))
    assert {p["device"] for p in tb["pins"]} == {"TB1:1", "PB1"} and not tb["wire_numbers"]


def test_server_read_audit_and_report(proj):
    tmp, wdp = proj
    r = server.ae_read(str(wdp), tolerance=0.01, detail="full")
    assert [d["drawing"] for d in r["drawings"]] == ["dwg1.dxf", "dwg2.dxf"]
    assert r["project"]["missing"] == ["MISSING.dwg"] and r["drawings"][0]["electrical_drawing"]
    a = server.ae_audit(str(wdp), tolerance=0.01)
    codes = a["by_code"]
    for code in ("drawing_missing", "duplicate_tag", "child_without_parent", "missing_catalog",
                 "unnumbered_wire", "duplicate_wire_number", "unpaired_signal", "unconnected_pin"):
        assert code in codes, code
    assert not any(i["ref"] == "K1" and i["code"] == "child_without_parent" for i in a["issues"])
    rep = server.ae_report("all", str(wdp), project="demo", tolerance=0.01)
    bom = {(b["manufacturer"], b["catalog"]): b["quantity"] for b in rep["rows"]["bom"]}
    assert bom[("ABB", "CP1-10")] == 2 and bom[("PHX", "UT2.5")] == 1
    xref = next(x for x in rep["rows"]["cross_reference"] if x["tag"] == "K1")
    assert xref["child_count"] == 1 and "dwg2.dxf" in xref["children"]
    term = rep["rows"]["terminals"][0]
    assert term["strip"] == "TB1" and "PB1:13" in term["connected_to"]
    wb = openpyxl.load_workbook(rep["workbook"])
    assert {"Info", "bom", "from_to", "audit"} <= set(wb.sheetnames)


def test_open_drawing_source_matches_file(proj, monkeypatch, tmp_path):
    app = App()
    doc = app.ActiveDocument
    for name, ins, attrs, pts in DWG1:
        doc.add_block(name, ins, attrs, points=pts)
    for a, b in LINES1:
        doc.ModelSpace.AddLine((*a, 0), (*b, 0)).Layer = "WIRES"
    monkeypatch.setattr(server, "_LIVE", LiveSession(PlainCom(app), tmp_path / "st"))
    r = server.ae_read(source="open", tolerance=0.01)
    f = server.ae_read(str(proj[0] / "dwg1.dxf"), tolerance=0.01)
    keys = ("components", "terminals", "wire_numbers", "wire_networks", "unconnected_pins")
    assert {k: r["drawings"][0][k] for k in keys} == {k: f["drawings"][0][k] for k in keys}


def test_capture_install_writes_file(proj, monkeypatch, tmp_path):
    app = App()
    app.ActiveDocument.add_block("HCR1", (0, 0), {"TAG1": "K1", "X4TERM01": ""},
                                 points={"X4TERM01": (-1, 0)})
    app.ActiveDocument.lisp_handler = lambda cmd: "yes" if "AEPROJECT" in cmd else "nil"
    monkeypatch.setattr(server, "_LIVE", LiveSession(PlainCom(app), tmp_path / "st"))
    res = server.ae_capture_install()
    data = json.loads(open(res["file"], encoding="utf-8").read())
    assert "AEPROJECT" in res["commands_found"]
    sample = data["drawing"]["sample_blocks"][0]
    assert sample["block"] == "HCR1" and sample["attribute_offsets"]["X4TERM01"] == [-1.0, 0.0]
    assert set(data["probe"]) == set(aecapture.PROBE_PREFIXES)


def test_acceptance_run_cleans_up(proj, monkeypatch, tmp_path):
    app = App()
    live = LiveSession(PlainCom(app), tmp_path / "st")
    monkeypatch.setattr(server, "_LIVE", live)
    with pytest.raises(ValueError, match="scratch"):
        server.live_acceptance_run(False)
    res = server.live_acceptance_run(True)
    names = {s["step"]: s["ok"] for s in res["steps"]}
    for must in ("live_place db", "live_place luminaire", "live_route", "live_move", "cleanup"):
        assert names[must], (must, res["steps"])
    assert live.list_devices()["devices"] == [] and json.loads(open(res["file"]).read())["passed"]


def test_every_tool_has_safety_hints():
    tools = asyncio.run(server.mcp.list_tools())
    names = {t.name for t in tools}
    assert not server.READ_ONLY & server.DESTRUCTIVE
    assert (server.READ_ONLY | server.DESTRUCTIVE) <= names
    for t in tools:
        assert t.annotations is not None and t.annotations.readOnlyHint == (t.name in server.READ_ONLY)
    assert next(t for t in tools if t.name == "live_delete").annotations.destructiveHint


def test_set_workspace_moves_every_store(tmp_path, monkeypatch):
    for attr in ("STORE", "PLANS", "BASES", "OPS"):
        monkeypatch.setattr(server, attr, getattr(server, attr))
    old = (server.CFG.workspace, server.STORE.root, server.PLANS.root, server.BASES.file,
           server.OPS.workspace)
    try:
        server.set_workspace(tmp_path / "w2")
        w = (tmp_path / "w2").resolve()
        assert server.STORE.root == server.PLANS.root == server.OPS.workspace == w
        assert server.BASES.file == w / ".bases.json"
    finally:
        (server.CFG.workspace, server.STORE.root, server.PLANS.root, server.BASES.file,
         server.OPS.workspace) = old


def test_live_tracking_is_per_folder(tmp_path):
    a, b = App(), App()
    b.ActiveDocument.FullName = "C:/other/Drawing1.dwg"
    la = LiveSession(PlainCom(a), tmp_path / "st")
    lb = LiveSession(PlainCom(b), tmp_path / "st")
    la.place("4F", "db", 0, 0)
    assert la._state_path() != lb._state_path()
    assert lb._load()["devices"] == {} and la._load()["devices"]


def test_schematic_reader_still_reads_open_drawing(tmp_path):
    app = App()
    app.ActiveDocument.add_block("HCR1", (0, 0), {"TAG1": "K1"})
    assert Schematic(LiveSession(PlainCom(app), tmp_path / "st")).read()["components_total"] == 1
