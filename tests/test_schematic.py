import pytest
from fake_acad import App
from acad_electrical_mcp import server
from acad_electrical_mcp.backends.base import BackendError
from acad_electrical_mcp.live import LiveSession, PlainCom
from acad_electrical_mcp.schematic import Schematic


@pytest.fixture()
def sch(tmp_path):
    app = App()
    doc = app.ActiveDocument
    doc.add_block("HPB11", (100, 200), {"TAG1": "PB1", "DESC1": "START", "DESC2": "PUSHBUTTON",
                                       "INST": "PANEL", "LOC": "FRONT", "MFG": "ABB",
                                       "CAT": "CP1-10", "TERM01": "13", "TERM02": "14"})
    doc.add_block("VCR11", (300, 200), {"TAG1": "K1", "DESC1": "MOTOR", "X1TERM01": "A1"})
    doc.add_block("WD_WNUM", (150, 210), {"WIRENO": "101"})
    doc.add_block("TITLE", (0, 0), {"DWGNAME": "x"}, layer="0")
    for lay in ("WIRES", "WIRES", "WIRES_B", "WALL"):
        doc.ModelSpace.AddLine((0, 0, 0), (50, 0, 0)).Layer = lay
    live = LiveSession(PlainCom(app), tmp_path / "st")
    return Schematic(live), live, app


def test_read_components_wire_numbers_and_wires(sch):
    s, _, _ = sch
    r = s.read()
    assert r["components_total"] == 2 and r["looks_like_schematic"]
    pb = next(c for c in r["components"] if c["tag"] == "PB1")
    assert pb["description"] == "START PUSHBUTTON" and pb["manufacturer"] == "ABB"
    assert pb["catalog"] == "CP1-10" and pb["terminals"] == {"TERM01": "13", "TERM02": "14"}
    assert r["wire_numbers"][0]["wire_number"] == "101"
    assert r["wires"]["lines_per_wire_layer"] == {"WIRES": 2, "WIRES_B": 1}
    assert r["other_attribute_blocks"] == 1  # the title block is not a component


def test_lisp_roundtrip_chunking_and_errors(sch):
    s, _, app = sch
    big = "x" * 1000
    app.ActiveDocument.lisp_handler = lambda cmd: big
    assert s.lisp("anything") == big
    app.ActiveDocument.lisp_handler = lambda cmd: "short"
    assert s.lisp("anything") == "short"

    def boom(cmd):
        raise RuntimeError("bad expr")
    app.ActiveDocument.lisp_handler = boom
    with pytest.raises(BackendError, match="LISP ERROR"):
        s.lisp("(oops)")


def test_lisp_timeout_when_autocad_busy(sch, monkeypatch):
    s, _, app = sch
    app.ActiveDocument.SendCommand = lambda cmd: None  # AutoCAD never answers
    monkeypatch.setattr("acad_electrical_mcp.schematic.time.sleep", lambda *_: None)
    t = iter(range(0, 1000, 10))
    monkeypatch.setattr("acad_electrical_mcp.schematic.time.time", lambda: next(t))
    with pytest.raises(BackendError, match="did not answer"):
        s.lisp("(x)", timeout=15)


def test_probe_and_detect(sch):
    s, _, app = sch

    def handler(cmd):
        if "atoms-family" in cmd:
            return "C:AEPROJECT,C:AECOMPONENT,C:AEWIRENO,"
        if "PRODUCT" in cmd:
            return "AutoCAD Electrical 2026"
        if "ACADVER" in cmd:
            return "25.0s"
        return "yes" if "c:wd_proj" in cmd else "defined"
    app.ActiveDocument.lisp_handler = handler
    p = s.probe()
    assert p["symbols"] == ["C:AEPROJECT", "C:AECOMPONENT", "C:AEWIRENO"] and not p["truncated"]
    d = s.detect()
    assert d["lisp_bridge"] == "ok" and d["components"] == 2 and d["looks_like_schematic"]
    assert d["electrical_loaded"] == "yes"


def test_mode_switch_blocks_plan_tools_and_back(sch, monkeypatch):
    _, live, _ = sch
    monkeypatch.setattr(server, "_LIVE", live)
    assert server.live_place("4F", "socket", 10, 10)["created"]  # default = plan mode
    server.live_set_mode("schematic")
    with pytest.raises(ValueError, match="Schematic mode is on"):
        server.live_place("4F", "socket", 20, 20)
    with pytest.raises(ValueError, match="Schematic mode is on"):
        server.live_route("C1", "lighting")
    assert server.sch_read(limit=5)["components_total"] == 2  # sch tools work
    server.live_set_mode("plan")
    assert server.live_place("4F", "socket", 20, 20)["created"]


def test_run_lisp_needs_explicit_enable(sch, monkeypatch):
    _, live, app = sch
    monkeypatch.setattr(server, "_LIVE", live)
    monkeypatch.setattr(server.CFG, "allow_commands", False)
    with pytest.raises(ValueError, match="disabled"):
        server.sch_run_lisp("(+ 1 2)")
    monkeypatch.setattr(server.CFG, "allow_commands", True)
    app.ActiveDocument.lisp_handler = lambda cmd: "3"
    assert server.sch_run_lisp("(+ 1 2)") == {"result": "3"}
