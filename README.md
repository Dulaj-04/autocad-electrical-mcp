# autocad-electrical-mcp

**An MCP server that lets Claude (or ChatGPT) draw and edit electrical floor plans, live, in AutoCAD Electrical.**

Ask in plain language: *"add a socket on the north wall of the Classroom, put it on circuit 4F-P02, redraw the route, and undo that"*. With AutoCAD open the change appears on screen as you chat. Without it, the same assistant builds the drawings offline as editable DXF files with PNG/PDF previews.

[![CI](https://github.com/Dulaj-04/autocad-electrical-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/Dulaj-04/autocad-electrical-mcp/actions/workflows/ci.yml)

> Everything produced is a **DRAFT drawing aid**. The server does not perform lighting, load, cable or protection calculations and implies no engineering approval.

---

## What it does

| | |
| --- | --- |
| **Live editing** | Edits the drawing **open in AutoCAD / AutoCAD Electrical** through COM: place, move, delete and re-route devices, add text, zoom to show you, undo one chat instruction at a time. Works on your existing drawings: `live_adopt` gives their symbols stable ids without changing the geometry. |
| **Offline drawing generation** | No AutoCAD needed. Builds four views per floor (architectural, lighting, power/socket/AC, combined) from one floor model, with safe preview → apply → undo, and exports DXF, PNG, A3 PDF and a `manifest.json` (DWG with live AutoCAD or the ODA File Converter). |
| **DIALux import** | Imports a DIALux DWG/DXF layout (luminaire blocks) into the model or straight into the open AutoCAD drawing, aligns it to your architecture, attaches wattage from a luminaire list, and produces a lighting schedule. See [docs/dialux.md](docs/dialux.md). |
| **Schematic mode** | Optional, off by default. Reads AutoCAD Electrical schematics (components, tags, wire numbers) and probes your install's AutoLISP commands. Writing schematic content is the next step. |
| **Validation** | Unique ids, circuits of the right kind on an existing DB, routes tied to circuits in the model, devices inside their rooms, layers present, architecture unchanged vs the reference, files reopen, hand edits detected. |

It uses your drawing conventions (layers `WALL DOORS LIFT STAIRS FURNITURE TEXT LIGHTING SWITCHES LIGHT_WIRING SOCKETS POWER_WIRING DATA AC AC_WIRING DB EMERGENCY NOTES`, labels such as `4F-L01`, `4F-P01`, `4F-AC01`, `DB-4F`) and never modifies your reference drawings.

## Three ways to work

| Mode | Use it when | Needs | Status |
| --- | --- | --- | --- |
| **Live (plan symbols)** — `live_*` tools | You want to see changes in AutoCAD while you chat | Windows, AutoCAD Electrical running with a drawing open | Self-test passed on AutoCAD Electrical 2026 |
| **Offline** — `plan_*`, `apply_changes`, `export_package` … | You want drawing files without AutoCAD, or repeatable batch output | Any OS, Python only | Built and tested |
| **Schematic** — `sch_*` tools (`live_set_mode('schematic')`) | You are working with AutoCAD Electrical schematics | Same as Live | Read and probe only |

Switching is explicit: say *"switch to schematic mode"* and the plan-symbol tools are blocked until you say *"back to plan mode"*, so the two are never mixed by accident.

---

## Quick start

> Naming: the repository is `autocad-electrical-mcp`; the Python package and the command it installs are `acad-electrical-mcp`.

### Windows (recommended, includes live AutoCAD)
1. Download this repo (*Code → Download ZIP*), extract to a permanent folder such as `C:\Tools\autocad-electrical-mcp`.
2. In PowerShell, inside that folder:
   ```powershell
   powershell -ExecutionPolicy Bypass -File scripts\install-windows.ps1
   ```
   It creates the venv, installs, runs the self-test and adds the server to Claude Desktop's config.
3. Quit Claude Desktop from the tray, reopen, start a **new** chat.

Step-by-step with troubleshooting: [docs/windows-setup.md](docs/windows-setup.md).

### Any OS (offline mode)
```bash
git clone https://github.com/Dulaj-04/autocad-electrical-mcp.git && cd autocad-electrical-mcp
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -e .
acad-electrical-mcp --selftest                         # prints "SELFTEST OK ... 50 tools"
acad-electrical-mcp --make-sample sample_floor.dxf     # optional demo drawing
```
Python 3.10+. Output goes to `./acad_mcp_workspace` (change with `ACAD_MCP_WORKSPACE` or `--workspace`).

## Connect to an AI client

**Claude Desktop** — add to `claude_desktop_config.json` (full path to the venv's executable, doubled backslashes on Windows; the Windows installer does this for you):
```json
{
  "mcpServers": {
    "acad-electrical": {
      "command": "C:\\Tools\\autocad-electrical-mcp\\.venv\\Scripts\\acad-electrical-mcp.exe",
      "env": { "ACAD_MCP_WORKSPACE": "C:\\Users\\YOU\\Documents\\acad_drawings" }
    }
  }
}
```

**Claude Code**
```bash
claude mcp add acad-electrical -- /full/path/to/.venv/bin/acad-electrical-mcp
```

**ChatGPT / any remote MCP client** — needs HTTPS, so run the HTTP transport behind a tunnel:
```bash
acad-electrical-mcp --transport http --port 8000 --allowed-host abc123.ngrok-free.app
```
Then add `https://abc123.ngrok-free.app/mcp` as a connector (ChatGPT *Settings → Connectors*, developer mode; availability depends on your plan). The HTTP endpoint has **no authentication**, so keep the tunnel short-lived. Live AutoCAD tools only work when the server runs on the same Windows PC as AutoCAD.

---

## Example prompts

**Live, on the open drawing**
> `live_connect`, then `live_adopt` for floor 4F ignoring pieces under 100 mm.
> Where is the Classroom? Put a socket on its north wall 1 m in from the left corner on circuit 4F-P02 / DB-4F, redraw route 4F-P02, and zoom there.
> Undo that. Move DB-4F 2 m left.

**Offline, from a reference DXF**
> Register `sample_floor.dxf` as floor 4F of project `demo` with rooms 4-A OFFICE (0,0,6000,5000), 4-B MEETING ROOM (6000,0,10000,5000), 4-C CORRIDOR (0,5000,10000,7000). Put a DB at (5000,6000), create lighting circuit L1 on it, propose a lighting grid in 4-A at 3000×2500 spacing on L1, route L1, apply, validate and export the package.

**Schematic**
> Switch to schematic mode, run `sch_detect`, then `sch_read`.

---

## Commands

### MCP tools (50) — what the assistant can call
Full parameters for every tool: **[docs/tools.md](docs/tools.md)** (generated from the running server).

| Group | Tool | What it does |
| --- | --- | --- |
| **Live editing** (Windows + AutoCAD) | `live_connect` | Attach to the open drawing; report name, layers, entity counts, unit scale. Start here. |
| | `live_selftest` | Create, move, route and delete test objects to prove the connection works. |
| | `live_scan` | Find symbols (touching LINEs clustered per layer) in the open drawing. |
| | `live_adopt` | Give existing symbols stable ids (`4F-LUM-01`, `DB-4F`) without changing geometry. |
| | `live_list_devices` | Tracked devices/routes with live positions; flags hand-moved or deleted ones. |
| | `live_texts` | Read TEXT (room names, labels) with positions. |
| | `live_place` | Draw a luminaire / switch / socket / data / ac / emergency / db symbol at x,y. Idempotent. |
| | `live_import_luminaires` | Draw a DIALux export's luminaires into the open drawing as ONE undo step (dry run first). |
| | `live_move` | Move a device to x,y or by dx,dy; marks its routes stale. |
| | `live_delete` | Delete a tracked device. |
| | `live_assign` | Record a device's circuit and DB. |
| | `live_route` | Draw or redraw an orthogonal DB → devices route, labelled with the circuit id. |
| | `live_add_text` / `live_add_polyline` | Add a note or a polyline on a layer. |
| | `live_zoom` | Pan/zoom AutoCAD to a spot so you can see the change. |
| | `live_undo` | Undo the last instruction (one undo step per call). |
| | `live_save` | Save, or Save As. |
| **Mode** | `live_set_mode` | `plan` (default) or `schematic`. |
| **Schematic** (AutoCAD Electrical) | `sch_detect` | Product/version, Electrical loaded?, AutoLISP bridge OK?, counts of components/wire numbers/wires. |
| | `sch_check_commands` | Ask AutoCAD whether command names (e.g. `AEPROJECT`) are registered, including compiled Electrical commands. |
| | `sch_modules` | List loaded compiled modules (ARX); shows whether Electrical's own modules are active. |
| | `sch_read` | Components (tag, description, location, manufacturer, catalog, terminals), wire numbers, wire layers. |
| | `sch_probe` | List the AutoLISP commands/functions your install exposes (`c:ae`, `c:wd`, …). |
| | `sch_run_lisp` | Run AutoLISP (**off** unless `ACAD_MCP_ALLOW_COMMANDS=1`). |
| **Inspect** (offline) | `register_reference` | Hash and inventory a DXF: layers, entities, blocks, units, extents, text. |
| | `inspect_drawing` | Inventory a generated view. |
| | `list_devices` / `list_floors` | Show the floor model / the project's floors. |
| | `get_preview_image` | Render a PNG of a view. |
| **DIALux import** (offline) | `dialux_inspect` | Look inside a DIALux DWG/DXF export: block names, counts, layers, attributes, units. Run first. |
| | `dialux_align` | Shift/rotation/scale that maps the DIALux file onto your architectural drawing, from two matching points. |
| | `import_luminaire_list` | Read a DIALux/Excel luminaire list (CSV/XLSX): type, quantity, wattage, flux. Missing wattage is reported, never guessed. |
| | `dialux_import` | Import luminaires into the floor model as a changeset (rooms assigned, wattage attached, re-import updates in place, scale/units check). |
| | `lighting_schedule` | Luminaires and installed watts per room and floor (W/m² when areas are known), flagging missing wattages. |
| **Prepare** | `prepare_floor_model` | Register the architectural reference and rooms; reports name differences instead of overwriting. |
| | `prepare_template` | Layer colours/lineweights, symbol and text size, status note, title block. |
| **Plan** | `plan_devices` | Propose devices; repeats create no duplicates. |
| | `propose_lighting_grid` | Draft luminaire grid in a room (placement only, no lux calculation). |
| | `set_circuit_assignment` | Create/update a circuit, bind to a DB, assign devices. |
| | `plan_routes` | Propose an orthogonal route tied to its circuit and DB. |
| **Apply** | `preview_changes` | Show a changeset: operations, assumptions, conflicts. |
| | `apply_changes` | Guarded apply (revision, reference hash, hand-edit detection), regenerate, read back. |
| | `undo_last` | Restore the previous revision. |
| | `sync_from_drawing` | Adopt device moves made by hand in the CAD file. |
| **Output** | `generate_views` | Regenerate the four DXF views from the model. |
| | `export_package` | DXF, DWG (if possible), PNG, A3 PDF and `manifest.json` with hashes and validation. |
| | `validate_drawing` | Issues with severity, code and message. |
| **AutoCAD utilities** (Windows) | `acad_status` / `acad_open` | Report the running AutoCAD / open a drawing read-only. |
| | `acad_run_command` | Send a command line (**off** unless `ACAD_MCP_ALLOW_COMMANDS=1`). |

### Command line
| Command | Purpose |
| --- | --- |
| `acad-electrical-mcp` | Start the MCP server on stdio (what Claude Desktop/Code launches). |
| `acad-electrical-mcp --transport http --port 8000 [--host H] [--allowed-host NAME]` | Streamable HTTP for remote clients such as ChatGPT. |
| `acad-electrical-mcp --selftest` | Start the server, list its tools, exit 0 if healthy. Run this first when anything is wrong. |
| `acad-electrical-mcp --make-sample FILE.dxf` | Write a small demo architectural floor. |
| `acad-electrical-mcp --workspace DIR` / `--backend dxf\|autocad` | Choose the project/output folder / drawing backend. |
| `acad-electrical-mcp --version` | Print the version. |
| `python scripts/gen_tool_docs.py [--check]` | Regenerate (or verify) `docs/tools.md`. |
| `scripts\install-windows.ps1 [-Workspace DIR] [-NoConfig]` | One-shot Windows setup. |

### Environment variables
| Variable | Meaning |
| --- | --- |
| `ACAD_MCP_WORKSPACE` | Folder for models and outputs (default `./acad_mcp_workspace`). |
| `ACAD_MCP_BACKEND` | `dxf` (default, offline) or `autocad` (COM) for the offline generator. |
| `ACAD_MCP_ALLOW_COMMANDS` | `1` enables `acad_run_command` and `sch_run_lisp`. Off by default because they can change any open drawing. |

---

## How it works
- **Offline:** one JSON *floor model* per floor (rooms, devices, circuits, routes) is the source of truth; all four views are generated from it so they always agree. Edits are *changesets*: plan → `preview_changes` → `apply_changes`, guarded by model revision, the reference file hash and hand-edit detection, with a snapshot for `undo_last`. Deterministic ids make repeated plans idempotent.
- **Live:** each device or route is drawn as plain LINE/polyline/TEXT in your reference style on your layers and wrapped in a named AutoCAD **group** `ACADE_<id>`, a stable id that survives saves and hand edits. Every call is wrapped in an undo mark. Symbol size is taken from the geometry (your reference drawings are millimetres although their header says metres).
- **Schematic:** reads AutoCAD Electrical blocks and attributes, and talks to AutoLISP by sending an expression and reading the answer back through a system variable.

## Repository layout
```
.
├── README.md
├── pyproject.toml                 package metadata, dependencies, lint config
├── LICENSE
├── .github/workflows/ci.yml       lint + tests on Python 3.10 and 3.12
├── src/acad_electrical_mcp/
│   ├── server.py                  MCP tools, CLI, transports (stdio / HTTP)
│   ├── live.py                    LIVE editing of the open AutoCAD drawing (COM)
│   ├── schematic.py               AutoCAD Electrical schematic read + AutoLISP probe
│   ├── symbols.py                 plan-symbol geometry in your reference style
│   ├── dialux.py                  DIALux export import, alignment, luminaire list, lighting schedule
│   ├── planner.py  model.py       changesets and the floor model store (offline)
│   ├── views.py  export.py        generate the four views; DXF/PNG/PDF/manifest
│   ├── validate.py  inspection.py checks and drawing inventory
│   ├── template.py  ids.py        layers/colours and id rules
│   ├── config.py  sample.py       settings, demo drawing
│   └── backends/                  dxf_backend.py (ezdxf) · autocad_backend.py (COM)
├── scripts/
│   ├── install-windows.ps1        one-shot Windows setup
│   └── gen_tool_docs.py           builds docs/tools.md from the server
├── docs/
│   ├── windows-setup.md           install + troubleshooting
│   ├── dialux.md                  importing a DIALux lighting layout
│   ├── live.md                    live mode and schematic mode guide
│   └── tools.md                   every tool and parameter (generated)
├── examples/claude_desktop_config.json
└── tests/                         offline workflow, live (fake AutoCAD), schematic, stdio smoke
```

## Status: what is verified
- **Verified by automated tests (CI on Python 3.10 and 3.12):** the offline workflow (planning, guarded apply, idempotence, stale/hand-edit conflicts, undo, sync, DXF/PNG/PDF/manifest export, reopen validation); the MCP protocol over stdio; the live and schematic logic against an in-memory simulation of AutoCAD's object model, including your real 4F drawing loaded into it (68 luminaires, 33 sockets, 11 emergency symbols, 9 AC units and 4 switches recognised).
- **Confirmed on a real PC:** the server installs on Windows and Claude Desktop lists and runs its tools. `live_selftest` passed on **AutoCAD Electrical 2026**: it placed a board and a luminaire, moved one, drew a route, read everything back and cleaned up, leaving the existing drawing contents (devices and routes) untouched.
- **Not yet individually confirmed on real AutoCAD:** `live_adopt`, `live_delete`, `live_undo`, `live_zoom`, `live_texts`, `live_add_text`, `live_add_polyline`, `live_save`, and the `sch_*` schematic tools (the AutoLISP link itself works on real AutoCAD). Try them on a scratch copy first and report any error text.
- **DIALux import:** tested on synthetic DIALux-style exports (block inserts with attributes, nested blocks, metres, shifted/rotated frames), including the live one-undo-step import. **Not yet run on a real DIALux export**; send one and the importer can be adjusted to its exact structure.
- **Not built yet:** inserting AutoCAD Electrical schematic components, drawing connected wires, wire numbering, reports. These must call Electrical's own commands, so they will be built from `sch_probe` output for your version. Model space only (no layouts yet).
- **Out of scope:** DIALux, load/cable/protection schedules, SLD and BOQ. Floor-plan routes are drawing geometry, not an Electrical wire network.
- DWG output offline needs the free [ODA File Converter](https://www.opendesign.com/guestfiles/oda_file_converter); otherwise `export_package` lists DWG as skipped with the reason.

## Troubleshooting
Run `acad-electrical-mcp --selftest` first: `SELFTEST OK` means the server is fine and the problem is in the client or AutoCAD. See [docs/windows-setup.md](docs/windows-setup.md#common-problems) for the common errors (folder moved, mcp 2.x, no tools in chat) and [docs/live.md](docs/live.md) for live-mode requirements (AutoCAD idle, same Windows user).

## Development
```bash
pip install -e ".[dev]"
ruff check . && pytest -q
python scripts/gen_tool_docs.py --check     # docs/tools.md must match the server
```
When you add or change a tool, run `python scripts/gen_tool_docs.py` and add it to the README table (a test fails if the README misses a tool).

## License
MIT
