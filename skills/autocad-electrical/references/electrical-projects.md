# AutoCAD Electrical projects: read, audit, report

All of these are read-only (`ae_report` only writes a new Excel file into the workspace).

## Inputs

- A `.wdp` project file (best: every drawing in it is read), one `.dxf`/`.dwg`, or a folder.
- Or the drawing open in AutoCAD: `source="open"`.
- DWG files on disk need the ODA File Converter; otherwise save as DXF or use `source="open"`.

## Typical session

1. `ae_project` on the `.wdp`: report the drawing count, which are missing, and any
   `unrecognised` lines (ask the user to share those; they improve the reader).
2. `ae_audit` with the same target. Summarise errors first, then warnings, grouped by `code`;
   offer the full list rather than pasting hundreds of info items.
3. `ae_report` (`report="all"`, `project` = a short id) for the Excel workbook: BOM, components,
   terminals, wire numbers, from/to, cross-reference, audit. Give the user the workbook path.
4. For a single question ("what is K1 connected to?") use `ae_read` with `detail="full"`.

## Reading the results honestly

- Wire networks, from/to and wire audits come from **line geometry**. If many pins show as
  unconnected or wires as unnumbered, the wire layers may differ: ask for the layer names and pass
  `wire_layers`. If ends do not meet, raise `tolerance` slightly.
- `unconnected_pin` is normal for spare contacts; do not present it as an error.
- `duplicate_wire_number` across drawings is fine when the drawings are joined by signal arrows.
- BOM rows exist only for components with manufacturer or catalog data; `missing_catalog` lists
  the rest.

## Not built yet

Inserting components, wiring, wire numbering, retagging and panel layouts. Offer
`ae_capture_install` (a typical schematic open in AutoCAD Electrical) and ask the user to send the
saved JSON file so these can be built for their version.
