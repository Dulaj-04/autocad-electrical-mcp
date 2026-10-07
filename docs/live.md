# Live mode: work on the drawing that is open in AutoCAD

The `live_*` tools talk to the running AutoCAD / AutoCAD Electrical through COM and edit the
**active drawing in place**. Nothing is exported: you watch the drawing change as you chat.

## Requirements
- Windows, AutoCAD or AutoCAD Electrical running, a drawing open (the active tab is edited).
- `pip install -e .` in the venv (`pywin32` is installed as a dependency of `mcp` on Windows;
  otherwise `pip install pywin32`).
- Run the MCP server on the **same PC and Windows user** as AutoCAD (stdio via Claude Desktop is fine).
- Don't leave AutoCAD in the middle of a command or dialog: it rejects outside calls while busy
  (the server retries for a few seconds, then reports an error).

## First run (do this once)
1. Open a **scratch/new drawing** in AutoCAD.
2. In the chat: *"Run live_selftest."* It draws a DB, a luminaire and a route, moves them, reads
   them back and deletes them. You should see them flash up and disappear.
3. Then open your real drawing, e.g. `4F_Electrical_Complete.dwg`, and say *"live_connect"*.

## How it keeps track of things
- Devices and routes are drawn as plain LINE/polyline/TEXT geometry in the reference style, on the
  reference layers (`LIGHTING`, `SWITCHES`, `SOCKETS`, `DATA`, `AC`, `DB`, `EMERGENCY`,
  `LIGHT_WIRING`, `POWER_WIRING`, `AC_WIRING`), and each is wrapped in a named AutoCAD **group**
  `ACADE_<id>` (see the `GROUP` command). The group is the stable id; it survives saving and manual edits.
- `live_adopt` groups the symbols already in your drawing (loose LINEs, no blocks) so they get ids
  such as `4F-LUM-01`, `4F-SKT-03`, `DB-4F`. Geometry is not changed. IDs are numbered bottom-to-top,
  left-to-right.
- Circuit labels follow your drawings (`4F-L01`, `4F-P01`, `4F-AC01` label a *circuit route*);
  device ids use `LUM/SW/SKT/DAT/ACU/EXT` so the two never clash.
- If you move something by hand, `live_list_devices` shows `moved_by_hand: true` and the next tool
  uses the real position. Routes through a moved or deleted device are flagged stale; ask for the
  route to be redrawn.
- Each tool call is one undo step (`live_undo`, or Ctrl+Z in AutoCAD).
- Units: the reference DXF headers say metres but the geometry is millimetres. The tools size
  symbols from the geometry (`unit_scale_vs_mm` in `live_connect`), not from the header.

## Example conversation
> live_connect, then live_adopt for floor 4F ignoring pieces smaller than 100 mm.
> Where is the Classroom? Put a socket on its north wall, 1 m in from the left corner, and assign it
> to circuit 4F-P02 on DB-4F. Redraw route 4F-P02. Zoom there.
> Undo that. Move DB-4F 2 m left.

## Limits
- These are **plan-level symbols**, not AutoCAD Electrical schematic components: no AE wire
  numbers, component tags, project database or reports. `acad_run_command` (needs
  `ACAD_MCP_ALLOW_COMMANDS=1`) can send AutoCAD/AE commands, and AE-specific automation can be
  added once the workflow is agreed.
- Model space only. No layouts/viewports yet.
- Validated against an in-memory fake of AutoCAD's object model and your reference drawings, not
  yet against a live AutoCAD: report any COM error text so it can be fixed.
