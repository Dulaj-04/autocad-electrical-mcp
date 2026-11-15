---
name: autocad-electrical
description: Work with AutoCAD Electrical and electrical installation drawings through the acad-electrical MCP server. Use when the user wants to read, audit or report on an AutoCAD Electrical project (.wdp, schematics, BOM, wire from/to, terminals), edit the drawing open in AutoCAD from chat, draw lighting/power/socket layouts for building floors, import a DIALux lighting layout, or build load schedules and maximum demand from Excel. Not for general AutoCAD drafting unrelated to electrical design.
---

# AutoCAD Electrical companion

The `acad-electrical` MCP server does the work; this skill says when to use which tools and the
rules that keep the user's drawings safe. Everything produced is a **DRAFT** drawing and
calculation aid: never invent ratings, demand factors or table values. Ask, or record the gap.

## First: is the server there and healthy?

If no `ae_*`, `plan_*` or `live_*` tools are available, the server is not connected: see
[references/setup.md](references/setup.md). If the tools exist but fail on AutoCAD, run
`live_connect` and read the error to the user in plain words.

## Pick the job

| The user wants to... | Start with | Guide |
| --- | --- | --- |
| Check or report on an AutoCAD Electrical project or schematic | `ae_project`, `ae_audit`, `ae_report` | [electrical-projects.md](references/electrical-projects.md) |
| Change the drawing open in AutoCAD and watch it happen | `live_connect` | [live-editing.md](references/live-editing.md) |
| Floor layouts, DIALux lighting, load schedule, multi-floor jobs | `plan_show`, then `plan_define` | [building-services.md](references/building-services.md) |

## Rules that always apply

1. **Look before touching.** Read-only tools first (`ae_project`, `ae_read`, `live_connect`,
   `live_inventory`, `intake_scan`). Tell the user what you found before proposing changes.
2. **Big request, plan first.** More than one drawing, a calculation, or data needed from the user:
   `plan_define`, show it, and call `plan_approve` only after the user says yes.
3. **Ask once, with defaults.** Put open questions in a short list, each with a recommended default,
   so the user can answer "defaults".
4. **Base drawings are never written.** `base_register` architectural bases and templates; draw in
   a copy (`floor_from_base`). Heavy DIALux exports: sanitise a copy, never the original.
5. **One floor at a time** on multi-floor work: open it with `plan_approve_floor`, show the result,
   and wait for the user before `plan_confirm_floor`.
6. **Confirm before destructive tools.** Deleting, undoing, saving over a file, sanitising,
   overwriting a workbook or running raw commands (`acad_run_command`, `sch_run_lisp`, both off by
   default) need the user's go-ahead in this conversation.
7. **Wiring found from geometry is a check.** `ae_report` from/to lists and `ae_audit` wire findings
   are derived from line geometry; say so, and suggest confirming with AutoCAD Electrical's reports.
8. **Say what changed.** After each change: what, where (`work_log`), and what is still open.

## When something is not supported yet

Writing AutoCAD Electrical schematics (inserting components, wiring, wire numbering) is not built.
Offer `ae_capture_install` instead: it saves one JSON file about the user's install so those
tools can be built for their version. Never fake it with `sch_run_lisp`.
