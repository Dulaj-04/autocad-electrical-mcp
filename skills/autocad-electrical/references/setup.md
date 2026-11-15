# Setup and first run

## Install the server

**Windows (recommended; needed for live AutoCAD work)**: download the repository, then in
PowerShell inside it run `powershell -ExecutionPolicy Bypass -File scripts\install-windows.ps1`.
It creates a virtual environment, installs, runs the self-test and adds the server to Claude
Desktop.

**Claude Code plugin**: `/plugin marketplace add Dulaj-04/autocad-electrical-mcp`, then
`/plugin install autocad-electrical`. The plugin starts the server with `uvx`, so
[uv](https://docs.astral.sh/uv/) must be installed.

**Any OS, offline only**: `pip install git+https://github.com/Dulaj-04/autocad-electrical-mcp`, then
`claude mcp add acad-electrical -- acad-electrical-mcp`.

## Check it works

1. In a terminal: `acad-electrical-mcp --selftest` prints `SELFTEST OK` and the tool count.
2. With AutoCAD open on a **new scratch drawing**: ask for `live_selftest`, then
   `live_acceptance_run` (pass `confirm_scratch=true` only after the user confirmed the drawing is
   a scratch copy). The acceptance run saves a pass/fail report under `<workspace>/captures/`.
3. With an AutoCAD Electrical schematic open: `ae_capture_install` saves what the install exposes.

## Common problems

| Symptom | Cause | Fix |
| --- | --- | --- |
| Tools missing in the chat | Client not restarted, or wrong path in its config | Quit the client fully and reopen; check the command path |
| "AutoCAD did not answer" | AutoCAD is inside a command or dialog | Press Esc in AutoCAD, retry |
| DWG "needs the ODA File Converter" | Offline DWG reading | Install the free ODA File Converter, save as DXF, or open it and use `source="open"` |
| Live tools refuse to write | The active drawing is a registered base | Open the working copy made by `floor_from_base` |

Environment variables: `ACAD_MCP_WORKSPACE` (output folder), `ACAD_MCP_REQUIRE_PLAN=1` (strict
plan-first), `ACAD_MCP_ALLOW_COMMANDS=1` (enables raw commands; leave off unless needed).
