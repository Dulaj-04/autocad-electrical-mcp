# AutoCAD Electrical projects: read, report, audit

These tools work on **AutoCAD Electrical schematics**: the `.wdp` project, its drawings, components,
terminals, wires and wire numbers. They are all read-only except the Excel workbook `ae_report`
writes into your workspace.

They read from either source:

| Source | How | Needs |
| --- | --- | --- |
| Files on disk | `target` = a `.wdp` project (every drawing in it), one `.dxf`/`.dwg`, or a folder | DXF files, or the free [ODA File Converter](https://www.opendesign.com/guestfiles/oda_file_converter) for DWG |
| The drawing open in AutoCAD | `source="open"` | Windows, AutoCAD Electrical running |

Both give the same result for the same drawing (there is a test that checks this).

## Tools

| Tool | What you get |
| --- | --- |
| `ae_project` | The `.wdp` project: description lines, settings, drawing list with description, section and sub-section, drawings missing on disk, duplicates, and any line the reader did not recognise. |
| `ae_read` | Per drawing: parent and child components, terminals, wire numbers, signal arrows, ladders, wire networks, unconnected pins. `detail="full"` lists the items. |
| `ae_report` | Bill of materials, component list, terminal list, wire number list, wire from/to list, parent/child cross-reference. One Excel workbook with a sheet per report plus the audit. |
| `ae_audit` | Problems sorted error > warning > info, with the drawing and tag for each. |
| `ae_capture_install` | One JSON file describing *your* install: modules, which Electrical commands exist, AutoLISP functions, and the block and attribute names your symbols use. |

## Try

> *"Read C:\Projects\Line3\LINE3.wdp, tell me which drawings are missing, then audit the project."*
>
> *"Give me the BOM and the from/to list for this project as Excel."*
>
> *"Audit the drawing that is open."* (uses `source="open"`)

## What the audit checks

| Code | Severity | Meaning |
| --- | --- | --- |
| `drawing_missing` | error | Listed in the `.wdp` but not on disk |
| `drawing_unreadable` | warning | Could not be read (a DWG without the ODA converter, a damaged file) |
| `duplicate_tag` | error | Two parent components with the same tag (and the same INST/LOC) |
| `duplicate_terminal` | error | The same strip and terminal number twice |
| `duplicate_wire_number` | error / warning | One wire number on separate wires: error within a drawing, warning across drawings (fine only when joined by signal arrows) |
| `child_without_parent` | warning | A child contact refers to a tag with no parent in the drawings read |
| `missing_catalog` | warning | A parent with no manufacturer or catalog number: missing from the BOM |
| `unnumbered_wire` | warning | A wire that joins two or more devices but carries no wire number |
| `several_wire_numbers` | warning | One wire carries more than one number |
| `unpaired_signal` | warning | A signal arrow code with no partner |
| `untagged_component` | warning | A component block with an empty tag |
| `missing_description` | info | A parent with no description |
| `unconnected_pin` | info | A pin with no wire: normal for spare contacts |
| `wire_number_off_wire` | info | A wire number block that sits on no wire |
| `no_wd_m` | info | No `WD_M` block: not set up as an AutoCAD Electrical drawing |

## How it reads a schematic

- **Components** are blocks with `TAG1` (parent), `TAG1F` (fixed tag) or `TAG2` (child), plus
  `DESC1-3`, `INST`, `LOC`, `MFG`, `CAT`, `ASSYCODE`, `FAMILY`, `RATINGn`. The family falls back to
  characters 2-3 of the block name (`HCR1` → `CR`).
- **Pins** are `TERMnn` attributes. Where a wire attaches is the insertion point of the matching
  `X?TERMnn` attribute; the digit is the wire direction (1 right, 2 top, 4 left, 8 bottom).
- **Terminals** carry `TAGSTRIP` and `TERM01`. **Wire numbers** are blocks with `WIRENO`
  (`WIRENOF` = fixed). **Signal arrows** carry `SIGCODE`. `WD_M` is the drawing settings block.
- **Wires** are LINEs (and polyline segments) on wire layers: by default any layer whose name
  contains `WIRE`; pass `wire_layers` if yours differ.

**Wire networks are derived from geometry**: wire ends that touch, or end on another wire (a T),
form one network; pins and wire numbers are attached by position. `tolerance` is the snapping
distance (default: 0.05 % of the drawing's size). This is a strong check, but it is not AutoCAD
Electrical's own wire database: confirm important wiring findings with its reports.

## The `.wdp` reader

The project file is read without AutoCAD. Lines it recognises: `*[n]` description, `+[n]` setting,
`?[n]` property, `=`-prefixed lines that describe the next drawing (`=====SEC=`, `=====SUB=`,
other `KEY=value`, or description text), and drawing file lines. Anything else is listed under
`unrecognised` with its line number rather than guessed at. If your version writes a line the
reader does not know, send the `unrecognised` list so it can be added.

## Building schematic writing for your version

Inserting components, drawing wires and numbering them must call AutoCAD Electrical's own commands,
which differ between versions. Run `ae_capture_install` once with a typical schematic open and
send the JSON file back: those write tools are built against what it contains.
