import pytest
from fake_acad import App
from acad_electrical_mcp.live import LiveSession, PlainCom
from acad_electrical_mcp.symbols import symbol_segments


@pytest.fixture()
def live(tmp_path):
    app = App()
    ms = app.ActiveDocument.ModelSpace
    # a reference-style drawing in millimetres whose header claims metres (insunits=6)
    for x in (1000, 3000, 5000):  # three luminaires drawn as loose LINEs, no blocks
        for p, q in symbol_segments("luminaire"):
            e = ms.AddLine((x + p[0], 2000 + p[1], 0), (x + q[0], 2000 + q[1], 0))
            e.Layer = "LIGHTING"
    ms.AddText("Classroom", (500, 4000, 0), 270).Layer = "TEXT"
    ms.AddText("Office", (7000, 4000, 0), 270).Layer = "TEXT"
    for p, q in [((0, 0), (9000, 0)), ((9000, 0), (9000, 5000))]:
        ms.AddLine((*p, 0), (*q, 0)).Layer = "WALL"
    return LiveSession(PlainCom(app), tmp_path / "state"), app


def test_connect_reports_geometry_scale_not_header(live):
    s, _ = live
    st = s.connect()
    assert st["unit_scale_vs_mm"] == 1.0 and st["header_insunits"] == 6
    assert st["entities_per_layer"]["LIGHTING"] == 18


def test_scan_recognises_reference_luminaires(live):
    s, _ = live
    cl = s.scan(["LIGHTING"])
    assert len(cl) == 3 and all(c["lines"] == 6 and c["width"] == 600 for c in cl)
    assert s.texts(contains="class")[0]["text"] == "Classroom"


def test_adopt_then_move_and_delete_by_id(live):
    s, app = live
    res = s.adopt("4F")
    assert res["by_type"] == {"luminaire": 3}
    assert s.scan(["LIGHTING"]) == []  # already tracked
    first = res["devices"][0]["id"]
    assert first == "4F-LUM-01"
    r = s.move(first, dx=250, dy=-100)
    assert (r["x"], r["y"]) == (1250.0, 1900.0)
    listing = s.list_devices()
    assert {d["id"] for d in listing["devices"]} == {"4F-LUM-01", "4F-LUM-02", "4F-LUM-03"}
    s.delete("4F-LUM-02")
    assert len(s.list_devices()["devices"]) == 2
    assert s.list_devices()["missing_from_drawing"] == []


def test_place_is_idempotent_and_matches_reference_symbol(live):
    s, app = live
    a = s.place("4F", "luminaire", 7000, 2000)
    b = s.place("4F", "luminaire", 7005, 2000)  # within tolerance: same device
    assert a["created"] and not b["created"] and a["id"] == b["id"]
    lines = [e for e in app.ActiveDocument.ModelSpace
             if e.ObjectName == "AcDbLine" and e.Layer == "LIGHTING"]
    assert len(lines) == 18 + 6
    with pytest.raises(ValueError):
        s.place("4F", "toaster", 0, 0)
    with pytest.raises(ValueError):
        s.place("4F", "luminaire", "abc", 0)


def test_route_and_stale_after_move(live):
    s, app = live
    s.place("4F", "db", 8000, 3000)
    s.place("4F", "luminaire", 7000, 2000, circuit="4F-L01", db="DB-4F")
    s.place("4F", "luminaire", 7000, 1000, circuit="4F-L01", db="DB-4F")
    r = s.route("4F-L01", "lighting")
    assert r["layer"] == "LIGHT_WIRING" and r["from"] == "DB-4F" and len(r["devices"]) == 2
    assert any(e.ObjectName == "AcDbText" and e.TextString == "4F-L01"
               for e in app.ActiveDocument.ModelSpace)
    m = s.move("4F-LUM-01", dx=500)
    assert m["routes_now_stale"] == ["4F-L01"]
    s.route("4F-L01", "lighting")  # redraw replaces the old group, no duplicates
    plines = [e for e in app.ActiveDocument.ModelSpace if e.ObjectName == "AcDbPolyline"]
    assert len(plines) == 1
    with pytest.raises(ValueError):
        s.route("NOPE", "lighting")
    with pytest.raises(ValueError):
        s.route("4F-L01", "steam")


def test_manual_move_detected_and_undo(live):
    s, app = live
    s.place("4F", "socket", 2000, 500)
    g = s._groups()["4F-SKT-01"]
    for it in g:  # user nudges the symbol by hand in AutoCAD
        it.Move((0, 0, 0), (300, 0, 0))
    assert s.list_devices()["devices"][0]["moved_by_hand"] is True
    n = len([e for e in app.ActiveDocument.ModelSpace])
    s.place("4F", "socket", 4000, 500)
    assert len([e for e in app.ActiveDocument.ModelSpace]) > n
    s.undo()
    assert "UNDO" in app.ActiveDocument.commands[-1]
    assert len([e for e in app.ActiveDocument.ModelSpace]) == n


def test_zoom_texts_and_selftest(live):
    s, app = live
    s.zoom(1000, 2000, 4000)
    assert app.zoomed is not None
    assert s.selftest()["ok"]
    assert s.list_devices()["devices"] == []  # self-test cleans up after itself
    assert not [e for e in app.ActiveDocument.ModelSpace
                if e.ObjectName == "AcDbPolyline"]


def test_server_live_tools_use_injected_session(live, monkeypatch):
    from acad_electrical_mcp import server
    s, app = live
    monkeypatch.setattr(server, "_LIVE", s)
    assert server.live_connect()["drawing"] == "Drawing1.dwg"
    assert server.live_scan(["LIGHTING"])["count"] == 3
    assert server.live_adopt("4F", ["LIGHTING"])["adopted"] == 3
    assert server.live_place("4F", "socket", 100, 100)["id"] == "4F-SKT-01"
    with pytest.raises(ValueError, match="Unknown device"):
        server.live_move("NOPE", dx=1)
    with pytest.raises(ValueError):
        server.live_place("../x", "socket", 1, 1)


def test_live_tools_fail_cleanly_without_autocad(monkeypatch):
    from acad_electrical_mcp import server
    monkeypatch.setattr(server, "_LIVE", None)
    with pytest.raises(ValueError, match="pywin32|AutoCAD"):
        server.live_connect()
