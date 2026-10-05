import hashlib
from pathlib import Path

import ezdxf
import pytest
from conftest import build_floor


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def test_full_flow_and_validation(env):
    s = env["server"]
    ref_hash = sha(env["ref"])
    build_floor(s)
    v = s.validate_drawing("demo", "4F")
    assert v["ok"], v["issues"]
    m = s.list_devices("demo", "4F")
    ids = {d["id"] for d in m["devices"]}
    assert "DB-4F" in ids and "4F-L01" in ids and "4F-P01" in ids and "4F-S01" in ids
    assert {r["id"] for r in m["routes"]} == {"R-L1", "R-P1"}
    # views reconcile with the model
    out = s.STORE.output_dir("demo", "4F")
    for name in ("Architectural_Base", "Lighting_Design", "Power_Socket_AC_Design",
                 "Electrical_Complete"):
        assert (out / f"4F_{name}.dxf").exists()
    comb = ezdxf.readfile(out / "4F_Electrical_Complete.dxf")
    light = ezdxf.readfile(out / "4F_Lighting_Design.dxf")
    n_comb = len(list(comb.modelspace().query('INSERT[layer=="LIGHTING"]')))
    n_light = len(list(light.modelspace().query('INSERT[layer=="LIGHTING"]')))
    assert n_comb == n_light > 0
    assert not list(light.modelspace().query('INSERT[layer=="SOCKETS"]'))
    # reference untouched, architecture preserved
    assert sha(env["ref"]) == ref_hash
    assert not [i for i in v["issues"] if i["code"] == "ARCH_CHANGED"]


def test_repeat_plan_creates_no_duplicates(env):
    s = env["server"]
    build_floor(s)
    before = len(s.list_devices("demo", "4F")["devices"])
    cs = s.propose_lighting_grid("demo", "4F", "4-A", 3000, 2500, circuit="L1")
    assert cs["operations"] == 0 and cs["unchanged_inputs"] > 0
    cs = s.plan_devices("demo", "4F", [{"type": "socket", "x": 800, "y": 4500, "circuit": "P1"}])
    assert cs["operations"] == 0
    assert len(s.list_devices("demo", "4F")["devices"]) == before


def test_stale_changeset_rejected(env):
    s = env["server"]
    a = s.plan_devices("demo", "4F", [{"type": "db", "x": 5000, "y": 6000}])
    b = s.plan_devices("demo", "4F", [{"type": "socket", "x": 1, "y": 1}])
    s.apply_changes("demo", "4F", a["changeset_id"])
    with pytest.raises(ValueError, match="Stale"):
        s.apply_changes("demo", "4F", b["changeset_id"])


def test_manual_edit_conflict_and_sync(env):
    s = env["server"]
    build_floor(s)
    out = s.STORE.output_dir("demo", "4F")
    f = out / "4F_Electrical_Complete.dxf"
    doc = ezdxf.readfile(f)
    ref = next(e for e in doc.modelspace().query("INSERT")
               if e.dxf.layer == "SOCKETS")
    moved_id = next(a.dxf.text for a in ref.attribs if a.dxf.tag == "ID")
    ref.dxf.insert = (ref.dxf.insert.x + 100, ref.dxf.insert.y, 0)
    doc.saveas(f)
    assert any(i["code"] == "MANUAL_EDIT" for i in s.validate_drawing("demo", "4F")["issues"])
    cs = s.plan_devices("demo", "4F", [{"type": "socket", "x": 9000, "y": 4500}])
    with pytest.raises(ValueError, match="Manual edits"):
        s.apply_changes("demo", "4F", cs["changeset_id"])
    res = s.sync_from_drawing("demo", "4F")
    assert res["moved"] == [moved_id]
    with pytest.raises(ValueError, match="Stale"):  # sync bumped the revision
        s.apply_changes("demo", "4F", cs["changeset_id"])
    cs = s.plan_devices("demo", "4F", [{"type": "socket", "x": 9000, "y": 4500}])
    s.apply_changes("demo", "4F", cs["changeset_id"])  # allowed after adopting edits
    new = next(d for d in s.list_devices("demo", "4F")["devices"] if d["id"] == moved_id)
    assert new["x"] in (900.0, 5600.0)


def test_undo_restores_previous_revision(env):
    s = env["server"]
    build_floor(s)
    n = len(s.list_devices("demo", "4F")["devices"])
    cs = s.plan_devices("demo", "4F", [{"type": "luminaire", "x": 7000, "y": 2500}])
    s.apply_changes("demo", "4F", cs["changeset_id"])
    assert len(s.list_devices("demo", "4F")["devices"]) == n + 1
    s.undo_last("demo", "4F")
    assert len(s.list_devices("demo", "4F")["devices"]) == n
    assert s.validate_drawing("demo", "4F")["ok"]


def test_invalid_assignments_rejected(env):
    s = env["server"]
    build_floor(s)
    with pytest.raises(ValueError):
        s.set_circuit_assignment("demo", "4F", "P1", "power", "DB-4F", ["4F-L01"])
    with pytest.raises(ValueError):
        s.plan_devices("demo", "4F", [{"type": "toaster", "x": 0, "y": 0}])
    with pytest.raises(ValueError):
        s.plan_routes("demo", "4F", "NOPE")


def test_export_package(env):
    s = env["server"]
    build_floor(s)
    man = s.export_package("demo", "4F")
    fmts = {(f["view"], f["format"]) for f in man["files"]}
    assert ("combined", "png") in fmts and ("combined", "pdf") in fmts
    assert ("combined", "dxf") in fmts
    assert man["validation"]["ok"], man
    for f in man["files"]:
        assert Path(f["path"]).stat().st_size > 0
        assert f["sha256"] == sha(f["path"])
    assert Path(man["manifest_path"]).exists()
    # DWG is reported honestly when no converter is installed
    assert any(k["format"] == "dwg" for k in man["skipped"]) or any(
        f["format"] == "dwg" for f in man["files"])


def test_stale_reference_detected(env):
    s = env["server"]
    build_floor(s)
    with open(env["ref"], "ab") as fh:
        fh.write(b"\n")
    cs = s.plan_devices("demo", "4F", [{"type": "luminaire", "x": 1, "y": 1}])
    with pytest.raises(ValueError, match="Stale input"):
        s.apply_changes("demo", "4F", cs["changeset_id"])


def test_path_traversal_rejected(env):
    s = env["server"]
    with pytest.raises(ValueError):
        s.prepare_floor_model("../evil", "4F")
    with pytest.raises(ValueError):
        s.list_devices("demo", "../4F")


def test_register_reference_and_room_difference(env):
    s = env["server"]
    info = s.register_reference(str(env["ref"]))
    assert info["units"] == "millimetres" and "Wall" in [lyr["name"] for lyr in info["layers"]]
    rep = s.prepare_floor_model("demo", "4F", rooms=[{"id": "4-A", "name": "RENAMED",
                                                       "bounds": [0, 0, 6000, 5000]}])
    assert rep["room_differences"], "approved names must not be silently replaced"
    assert next(r for r in s.list_devices("demo", "4F")["rooms"] if r["id"] == "4-A")["name"] \
        == "OFFICE"


def test_blank_drawing_without_reference(tmp_path, monkeypatch):
    from acad_electrical_mcp import server
    from acad_electrical_mcp.model import Store
    monkeypatch.setattr(server, "STORE", Store(tmp_path))
    monkeypatch.setattr(server.CFG, "backend", "dxf")
    server.prepare_floor_model("p", "GF", rooms=[{"id": "G-A", "name": "HALL",
                                                   "bounds": [0, 0, 10, 8]}])
    cs = server.plan_devices("p", "GF", [{"type": "luminaire", "x": 5, "y": 4}])
    server.apply_changes("p", "GF", cs["changeset_id"])
    assert server.validate_drawing("p", "GF")["ok"]
