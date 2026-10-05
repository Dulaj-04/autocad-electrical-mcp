# Tool reference

All floor tools take `project` and `floor` (letters, digits, `_`, `-`). Coordinates are in the
reference drawing's units. Planning tools return a `changeset_id`; nothing changes until
`apply_changes`.

## Inspect
- `register_reference(path)` – hash + inventory a DXF (DWG with ODA converter): layers, entities,
  blocks, units, extents, layouts, text (candidate room labels).
- `inspect_drawing(project, floor, view)` – same for a generated output view, plus device IDs.
- `list_devices(project, floor)` – model: rooms, devices, circuits, routes, revision.
- `list_floors(project)`; `get_preview_image(project, floor, view)` – PNG you can look at.

## Prepare
- `prepare_floor_model(project, floor, reference_path?, rooms?, replace_rooms?)` – register the
  architectural base and rooms (`{id, name, bounds:[minx,miny,maxx,maxy]}`). Existing room names
  are never silently replaced; differences are returned in `room_differences`.
- `prepare_template(project, floor, overrides)` – layer colours/lineweights, `symbol_size`,
  `text_height`, `status`, `title_block {project, drawn_by, notes[]}`.

## Plan
- `plan_devices(devices, remove_ids?, tolerance?)` – devices `{type, x, y, id?, rotation?, room?,
  circuit?, db?, note?}`; same type at the same spot is treated as already present.
- `propose_lighting_grid(room_id, spacing_x, spacing_y, circuit?, margin?)` – placement draft.
- `set_circuit_assignment(circuit_id, kind, db?, device_ids?)` – kind `lighting|power|ac`.
- `plan_routes(circuit_id, device_ids?)` – orthogonal route DB → devices, stored with its circuit/DB.

## Write
- `preview_changes(changeset_id)` – operations, assumptions, conflicts.
- `apply_changes(changeset_id, overwrite_manual_edits?)` – guarded apply + regenerate + read-back.
- `undo_last()` – restore the previous revision.
- `sync_from_drawing(view, remove_missing?)` – adopt device moves made by hand in CAD.

## Output
- `generate_views(views?)` – regenerate DXFs (e.g. after a template change).
- `export_package(views?)` – DXF, DWG (if possible), PNG, PDF, `manifest.json`.
- `validate_drawing()` – issues with severity, code, message and reference.

## Live AutoCAD (Windows)
`acad_status`, `acad_open` (read-only), `acad_run_command` (needs `ACAD_MCP_ALLOW_COMMANDS=1`).
Select the live drawing backend with `ACAD_MCP_BACKEND=autocad` or `--backend autocad`.

## Environment
| Variable | Meaning |
| --- | --- |
| `ACAD_MCP_WORKSPACE` | project/output folder (default `./acad_mcp_workspace`) |
| `ACAD_MCP_BACKEND` | `dxf` (default) or `autocad` |
| `ACAD_MCP_ALLOW_COMMANDS` | `1` enables `acad_run_command` |

Workspace layout: `<project>/<floor>/model.json` (+ `changesets/`, `history/`) and
`<project>/output/<floor>/` for the drawings.
