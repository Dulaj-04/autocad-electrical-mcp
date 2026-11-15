# Building services: floors, lighting, loads

## Start of any project conversation

`plan_show` for the project. If a plan exists, continue it; otherwise, for anything bigger than a
single action, `plan_templates` then `plan_define` and wait for the user's yes (`plan_approve`).
`plan_next` says exactly which files, Excel sheets and decisions to ask for.

## Offline floor drawings (no AutoCAD needed)

`prepare_floor_model` → `plan_devices` / `propose_lighting_grid` / `set_circuit_assignment` /
`plan_routes` (each returns a changeset) → `preview_changes` → `apply_changes` →
`validate_drawing` → `export_package` (DXF, PNG, A3 PDF and a manifest).

## DIALux lighting

`dialux_inspect` → `dialux_align` (two matching points) → `import_luminaire_list` →
`dialux_import` → `apply_changes` or `live_import_luminaires` → `lighting_schedule`.
Missing wattages are reported, never guessed.

## Multi-floor projects

`intake_scan` the input folder first; `base_register` the bases; `floor_from_base` per floor;
`plan_approve_floor` for ONE floor; `place_from_table` and `verify_placement`; show the result;
`plan_confirm_floor` only after the user accepts. `plan_impact` before changing a decided value.

## Loads and maximum demand

`workbook_create` (`load_schedule`) → the user fills it in → `workbook_read` → `load_summary`.
Demand uses only the user's factors; rows without one are listed and left out, never set to 1.
`export_circuit_lengths` and `export_quantities` feed cable sizing and the BOQ.
