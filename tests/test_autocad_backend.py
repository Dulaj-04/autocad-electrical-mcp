import pytest

from acad_electrical_mcp import server
from acad_electrical_mcp.backends import BackendError, make_backend


def test_command_tool_disabled_by_default(monkeypatch):
    monkeypatch.setattr(server.CFG, "allow_commands", False)
    with pytest.raises(ValueError, match="disabled"):
        server.acad_run_command("_ZOOM E")


def test_live_tools_fail_cleanly_without_autocad():
    # On Linux/CI (no pywin32 / no AutoCAD) the tools must give a clear error, not crash.
    with pytest.raises(ValueError, match="pywin32|AutoCAD"):
        server.acad_status()
    with pytest.raises(BackendError):
        make_backend("autocad").begin(None)


def test_unknown_backend():
    with pytest.raises(BackendError):
        make_backend("nope")
