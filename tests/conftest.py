import pytest

from acad_electrical_mcp import server
from acad_electrical_mcp.model import Store
from acad_electrical_mcp.sample import ROOMS, make_sample_floor


@pytest.fixture()
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(server.CFG, "workspace", tmp_path / "ws")
    monkeypatch.setattr(server.CFG, "backend", "dxf")
    monkeypatch.setattr(server, "STORE", Store(tmp_path / "ws"))
    ref = tmp_path / "4F_Architectural_Base.dxf"
    make_sample_floor(str(ref))
    server.prepare_floor_model("demo", "4F", str(ref), ROOMS)
    return {"ref": ref, "tmp": tmp_path, "server": server}


def build_floor(s):
    """DB + a lighting circuit with a grid + a socket circuit; returns nothing."""
    cs = s.plan_devices("demo", "4F", [{"type": "db", "x": 5000, "y": 6000}])
    s.apply_changes("demo", "4F", cs["changeset_id"])
    cs = s.set_circuit_assignment("demo", "4F", "L1", "lighting", "DB-4F")
    s.apply_changes("demo", "4F", cs["changeset_id"])
    cs = s.propose_lighting_grid("demo", "4F", "4-A", 3000, 2500, circuit="L1")
    s.apply_changes("demo", "4F", cs["changeset_id"])
    cs = s.set_circuit_assignment("demo", "4F", "P1", "power", "DB-4F")
    s.apply_changes("demo", "4F", cs["changeset_id"])
    cs = s.plan_devices("demo", "4F", [
        {"type": "socket", "x": 800, "y": 4500, "room": "4-A", "circuit": "P1"},
        {"type": "socket", "x": 5500, "y": 4500, "room": "4-A", "circuit": "P1"},
        {"type": "switch", "x": 5800, "y": 4000, "room": "4-A", "circuit": "L1"},
    ])
    s.apply_changes("demo", "4F", cs["changeset_id"])
    for c in ("L1", "P1"):
        cs = s.plan_routes("demo", "4F", c)
        s.apply_changes("demo", "4F", cs["changeset_id"])
