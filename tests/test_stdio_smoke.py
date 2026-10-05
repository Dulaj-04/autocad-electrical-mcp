"""Start the real server over stdio and call tools through the MCP client."""

import asyncio
import json
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


def test_stdio_roundtrip(tmp_path):
    async def run():
        params = StdioServerParameters(
            command=sys.executable, args=["-m", "acad_electrical_mcp.server"],
            env={"ACAD_MCP_WORKSPACE": str(tmp_path / "ws"), "PATH": "/usr/bin:/bin"},
        )
        async with stdio_client(params) as (r, w), ClientSession(r, w) as sess:
            await sess.initialize()
            tools = {t.name for t in (await sess.list_tools()).tools}
            assert {"plan_devices", "apply_changes", "export_package", "validate_drawing",
                    "preview_changes", "undo_last", "acad_status"} <= tools
            await sess.call_tool("prepare_floor_model", {
                "project": "p", "floor": "1F",
                "rooms": [{"id": "1-A", "name": "HALL", "bounds": [0, 0, 10, 8]}]})
            cs = await sess.call_tool("plan_devices", {
                "project": "p", "floor": "1F",
                "devices": [{"type": "luminaire", "x": 5, "y": 4}]})
            cs_id = json.loads(cs.content[0].text)["changeset_id"]
            res = await sess.call_tool("apply_changes", {
                "project": "p", "floor": "1F", "changeset_id": cs_id})
            assert not res.isError, res.content
            bad = await sess.call_tool("plan_devices", {
                "project": "p", "floor": "../x", "devices": []})
            assert bad.isError

    asyncio.run(run())
