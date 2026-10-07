# acad-electrical-mcp

An [MCP](https://modelcontextprotocol.io) server that lets Claude, ChatGPT or any MCP client
**create, revise, validate and export editable electrical floor drawings** for an
AutoCAD Electrical workflow: lighting, switching, sockets, data, AC, distribution boards,
emergency provisions, routes and labels, on a clean layer vocabulary, with DWG/DXF/PNG/PDF output.

> Everything it produces is a **DRAFT drawing aid**. It does not perform lighting, load, cable or
> protection calculations and implies no engineering approval.

## How it works

One JSON **floor model** (rooms, devices, circuits, routes) is the single source of truth.
The four drawings per floor are generated from it, so they always agree:

| View | File |
| --- | --- |
| architectural | `<floor>_Architectural_Base.dxf` |
| lighting | `<floor>_Lighting_Design.dxf` |
| power / socket / AC | `<floor>_Power_Socket_AC_Design.dxf` |
| combined | `<floor>_Electrical_Complete.dxf` |

`export_package` additionally writes DWG (when available), PNG previews, A3 PDF sheets and a
`manifest.json` (file hashes, revision, validation result).

Edits are **changesets**: plan → `preview_changes` → `apply_changes`. Applying is guarded by the
model revision, the reference-file hash and manual-edit detection; it snapshots the previous
revision (`undo_last`), regenerates the views and reads them back for validation. Re-planning
the same devices creates no duplicates (deterministic IDs such as `4F-L01`, `4F-P01`,
`4F-AC01`, `DB-4F`). Your reference drawings are never modified.

### Two backends

| Backend | Needs | Does |
| --- | --- | --- |
| `dxf` (default) | Python only, any OS | Reads/writes DXF with [ezdxf](https://ezdxf.mozman.at); PNG/PDF rendering. DWG in/out only if the free [ODA File Converter](https://www.opendesign.com/guestfiles/oda_file_converter) is installed. |
| `autocad` | Windows, licensed AutoCAD / AutoCAD Electrical running, `pywin32` | Draws through the AutoCAD COM API and saves native DWG/DXF. |

## Install

```bash
git clone https://github.com/dulaj-04/claude_repo.git
cd claude_repo
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -e .                                      # add ".[autocad]" for the live backend
acad-electrical-mcp --make-sample sample_floor.dxf    # optional demo architectural drawing
```

Python 3.10+. Output goes to `./acad_mcp_workspace` (override with `ACAD_MCP_WORKSPACE` or
`--workspace`).

## Use with Claude

**Claude Code**

```bash
claude mcp add acad-electrical -- acad-electrical-mcp
```

**Claude Desktop** — add to `claude_desktop_config.json` (use the full path to the venv's
`acad-electrical-mcp` if it is not on PATH):

```json
{
  "mcpServers": {
    "acad-electrical": {
      "command": "acad-electrical-mcp",
      "env": { "ACAD_MCP_WORKSPACE": "/path/to/my/drawings" }
    }
  }
}
```

## Use with ChatGPT (or any remote MCP client)

ChatGPT connects to MCP servers over HTTPS, so run the HTTP transport and expose it:

```bash
acad-electrical-mcp --transport http --port 8000
ngrok http 8000                                   # or any tunnel / your own server
# restart with the public host allowed:
acad-electrical-mcp --transport http --port 8000 --allowed-host abc123.ngrok-free.app
```

Then in ChatGPT: *Settings → Connectors → (enable Developer mode) → Create*, and use
`https://abc123.ngrok-free.app/mcp` as the MCP server URL. Connector availability depends on your
ChatGPT plan. The HTTP endpoint has **no authentication**; do not expose it publicly beyond a
short-lived tunnel, and keep `ACAD_MCP_ALLOW_COMMANDS` unset.

## Live mode: edit the drawing open in AutoCAD while you chat

Windows + AutoCAD / AutoCAD Electrical running with a drawing open. The `live_*` tools edit
that **open drawing directly** (no export step), so every instruction in the chat appears on
screen, and you can keep adjusting: *"move the DB to the corridor", "add a socket on the north
wall of the Classroom", "re-route L03", "undo that"*. Full guide: [docs/live.md](docs/live.md).

## Troubleshooting

First prove the server itself works, independent of any client:

```bash
acad-electrical-mcp --selftest      # prints "SELFTEST OK ... 20 tools" and exits 0
```

- `SELFTEST FAILED`: the install is broken (wrong Python, or `pip install -e .` not run in the
  active venv). Re-run the install steps.
- Selftest OK but no tools in Claude Desktop: fully quit it (tray icon → Quit), reopen, start a
  **new** chat, make sure the connector toggle is on, and ask "list the tools from
  acad-electrical" (tools may load on demand).
- In `claude_desktop_config.json` use the full path to `acad-electrical-mcp(.exe)` inside your venv.

## Quick walk-through (say this to your assistant)

> Register `sample_floor.dxf` as floor 4F of project `demo` with rooms 4-A OFFICE
> (0,0,6000,5000), 4-B MEETING ROOM (6000,0,10000,5000), 4-C CORRIDOR (0,5000,10000,7000).
> Put a DB at (5000,6000), create lighting circuit L1 on it, propose a lighting grid in 4-A at
> 3000×2500 spacing on L1, route L1, apply, validate and export the package.

## Tools

| Group | Tools |
| --- | --- |
| Inspect | `register_reference`, `inspect_drawing`, `list_devices`, `list_floors`, `get_preview_image` |
| Prepare | `prepare_floor_model`, `prepare_template` |
| Plan | `plan_devices`, `propose_lighting_grid`, `set_circuit_assignment`, `plan_routes` |
| Safe write | `preview_changes`, `apply_changes`, `undo_last`, `sync_from_drawing` |
| Output | `generate_views`, `export_package`, `validate_drawing` |
| **Live editing (Windows)** | `live_connect`, `live_selftest`, `live_scan`, `live_adopt`, `live_list_devices`, `live_texts`, `live_place`, `live_move`, `live_delete`, `live_assign`, `live_route`, `live_add_text`, `live_add_polyline`, `live_zoom`, `live_undo`, `live_save` |
| **Schematic mode (Windows, AutoCAD Electrical)** | `live_set_mode`, `sch_detect`, `sch_read`, `sch_probe`, `sch_run_lisp` (read/probe only for now) |
| Live AutoCAD (Windows) | `acad_status`, `acad_open`, `acad_run_command` (disabled unless `ACAD_MCP_ALLOW_COMMANDS=1`) |

Device types: `luminaire`, `switch`, `socket`, `data`, `ac`, `emergency`, `db`. Layers (all
configurable via `prepare_template`): `Wall Doors Lift Stairs FURNITURE TEXT LIGHTING SWITCHES
LIGHT_WIRING SOCKETS POWER_WIRING DATA AC AC_WIRING DB EMERGENCY NOTES`. Layers that already exist
in your reference drawing keep their own colours.

Details: [docs/tools.md](docs/tools.md).

## What validation checks

Unique floor-prefixed IDs; every device on a circuit of the right kind bound to an existing DB;
routes tied to their circuit and devices in the model (crossing lines imply no connectivity);
devices inside their rooms; all layers present; every device drawn exactly once per view and
views reconciling with the model; architectural layer entity counts equal to the reference;
reference hash unchanged; label overlaps; status note; files reopen; manual edits detected.

## Verified vs not verified

- **Verified** (automated tests, CI): the `dxf` backend end to end — planning, guarded apply,
  repeat-run idempotence, stale/manual-edit conflicts, undo, sync, export of DXF/PNG/PDF/manifest,
  reopen validation, and the stdio MCP protocol; HTTP transport starts and answers `initialize`.
- **Not verified**: the live COM tools (`live_*`) and the `autocad` backend are tested only against an in-memory fake of the AutoCAD object model and against your reference drawings loaded into it; run `live_selftest` on a scratch drawing first. The `autocad` COM backend has not been run against a licensed AutoCAD
  Electrical host (it cannot run in CI). Treat it as experimental and test on a disposable copy.
  Native DWG output without it needs the ODA File Converter; otherwise `export_package` reports
  DWG as skipped with the reason.
- **Out of scope**: AutoCAD Electrical *project* semantics (intelligent wires/components,
  WDBLOCK/project reports), DIALux, load/cable/protection schedules, SLD and BOQ. Floor-plan
  routes here are drawing geometry, not an AutoCAD Electrical wire network.
- Units: if a reference declares no `$INSUNITS`, you are warned; confirm units before trusting
  any dimension or area.

## Development

```bash
pip install -e ".[dev]"
ruff check . && pytest -q
```

MIT licensed.
