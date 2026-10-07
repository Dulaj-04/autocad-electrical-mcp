# Tool reference

All 42 MCP tools, generated from the running server (`python scripts/gen_tool_docs.py`). Do not edit by hand.

Floor tools take `project` and `floor` (letters, digits, `_`, `-`). Coordinates are in the drawing's units.

| Group | Tools |
| --- | --- |
| Inspect | `register_reference`, `inspect_drawing`, `list_devices`, `list_floors`, `get_preview_image` |
| Prepare | `prepare_floor_model`, `prepare_template` |
| Plan | `plan_devices`, `propose_lighting_grid`, `set_circuit_assignment`, `plan_routes` |
| Apply, undo, sync | `preview_changes`, `apply_changes`, `undo_last`, `sync_from_drawing` |
| Output | `generate_views`, `export_package`, `validate_drawing` |
| Live editing (plan symbols) | `live_connect`, `live_selftest`, `live_scan`, `live_adopt`, `live_list_devices`, `live_texts`, `live_place`, `live_move`, `live_delete`, `live_assign`, `live_route`, `live_add_text`, `live_add_polyline`, `live_zoom`, `live_undo`, `live_save` |
| Mode switch | `live_set_mode` |
| Schematic mode (AutoCAD Electrical) | `sch_detect`, `sch_read`, `sch_probe`, `sch_run_lisp` |
| AutoCAD utilities (Windows) | `acad_status`, `acad_open`, `acad_run_command` |

## Inspect

Read drawings and models. Nothing is changed.

### `register_reference`

Hash and inventory a reference DXF (or DWG with ODA converter): layers, entity counts, blocks, units, extents, layouts and text entities (candidate room labels). Read-only.

| Parameter | Type | Required | Default |
| --- | --- | --- | --- |
| `path` | string | yes |  |

### `inspect_drawing`

Inventory a generated output drawing of a floor (layers, entity counts, device ids).

| Parameter | Type | Required | Default |
| --- | --- | --- | --- |
| `project` | string | yes |  |
| `floor` | string | yes |  |
| `view` | `architectural` \| `lighting` \| `power` \| `combined` | no | `combined` |

### `list_devices`

List the logical devices, circuits, routes and rooms of a floor model.

| Parameter | Type | Required | Default |
| --- | --- | --- | --- |
| `project` | string | yes |  |
| `floor` | string | yes |  |

### `list_floors`

List floors that have a model in a project.

| Parameter | Type | Required | Default |
| --- | --- | --- | --- |
| `project` | string | yes |  |

### `get_preview_image`

Render a PNG of a generated view so the drawing can be looked at.

| Parameter | Type | Required | Default |
| --- | --- | --- | --- |
| `project` | string | yes |  |
| `floor` | string | yes |  |
| `view` | `architectural` \| `lighting` \| `power` \| `combined` | no | `combined` |

## Prepare

Create the floor model and set the drawing template.

### `prepare_floor_model`

Create/update the floor model: register the architectural reference (hash + units check) and rooms. Each room is {"id","name","bounds":[minx,miny,maxx,maxy]} in drawing units. Existing rooms are kept unless replace_rooms=true; differing names are reported, not overwritten silently. The reference file itself is never modified.

| Parameter | Type | Required | Default |
| --- | --- | --- | --- |
| `project` | string | yes |  |
| `floor` | string | yes |  |
| `reference_path` | string | no | `None` |
| `rooms` | list of object | no | `None` |
| `replace_rooms` | boolean | no | `False` |

### `prepare_template`

Customise the drawing template. Keys: layers {name:{color,lineweight,description}}, symbol_size, text_height (drawing units), status, title_block {project,drawn_by,notes[]}. Regenerate views afterwards with generate_views.

| Parameter | Type | Required | Default |
| --- | --- | --- | --- |
| `project` | string | yes |  |
| `floor` | string | yes |  |
| `overrides` | object | yes |  |

## Plan

Propose devices, circuits and routes. Each call returns a changeset; nothing is drawn until `apply_changes`.

### `plan_devices`

Propose luminaires, switches, sockets, data, ac, emergency and db devices. Each device: {"type","x","y"} plus optional id, rotation, room, circuit, db, note. Same-type devices at the same position (within tolerance) are treated as already present, so repeating a plan creates no duplicates. Returns a changeset to preview/apply.

| Parameter | Type | Required | Default |
| --- | --- | --- | --- |
| `project` | string | yes |  |
| `floor` | string | yes |  |
| `devices` | list of object | yes |  |
| `remove_ids` | list of string | no | `None` |
| `tolerance` | number | no | `0.01` |

### `propose_lighting_grid`

Propose a regular luminaire grid in a room (placement draft only, no lux calculation).

| Parameter | Type | Required | Default |
| --- | --- | --- | --- |
| `project` | string | yes |  |
| `floor` | string | yes |  |
| `room_id` | string | yes |  |
| `spacing_x` | number | yes |  |
| `spacing_y` | number | yes |  |
| `circuit` | string | no | `None` |
| `margin` | number | no | `0.0` |

### `set_circuit_assignment`

Create/update a circuit, bind it to a distribution board and assign devices to it.

| Parameter | Type | Required | Default |
| --- | --- | --- | --- |
| `project` | string | yes |  |
| `floor` | string | yes |  |
| `circuit_id` | string | yes |  |
| `kind` | `lighting` \| `power` \| `ac` | yes |  |
| `db` | string | no | `None` |
| `device_ids` | list of string | no | `None` |

### `plan_routes`

Propose an orthogonal route from the circuit's DB through its devices (nearest-first, or in the order given). The route is associated with the circuit/DB in the model; geometric crossings imply no connectivity. Draft drawing aid, not cable routing/sizing.

| Parameter | Type | Required | Default |
| --- | --- | --- | --- |
| `project` | string | yes |  |
| `floor` | string | yes |  |
| `circuit_id` | string | yes |  |
| `device_ids` | list of string | no | `None` |

## Apply, undo, sync

Guarded writes with undo and read-back.

### `preview_changes`

Show what a changeset would do (adds/updates/removals, assumptions, conflicts).

| Parameter | Type | Required | Default |
| --- | --- | --- | --- |
| `project` | string | yes |  |
| `floor` | string | yes |  |
| `changeset_id` | string | yes |  |

### `apply_changes`

Apply a changeset: guarded by model revision, reference hash and manual-edit detection; snapshots the previous revision (undo_last), regenerates all four DXF views and reads them back for validation.

| Parameter | Type | Required | Default |
| --- | --- | --- | --- |
| `project` | string | yes |  |
| `floor` | string | yes |  |
| `changeset_id` | string | yes |  |
| `overwrite_manual_edits` | boolean | no | `False` |

### `undo_last`

Restore the model to the revision before the last apply_changes and regenerate views.

| Parameter | Type | Required | Default |
| --- | --- | --- | --- |
| `project` | string | yes |  |
| `floor` | string | yes |  |
| `overwrite_manual_edits` | boolean | no | `False` |

### `sync_from_drawing`

Adopt manual edits: read device positions from an edited output DXF back into the model. Devices only in the drawing are reported (not adopted). Routes touching moved devices are dropped and must be re-planned. Use remove_missing=true to delete devices erased in CAD.

| Parameter | Type | Required | Default |
| --- | --- | --- | --- |
| `project` | string | yes |  |
| `floor` | string | yes |  |
| `view` | `lighting` \| `power` \| `combined` | no | `combined` |
| `remove_missing` | boolean | no | `False` |

## Output

Generate the drawing views and the export package.

### `generate_views`

(Re)generate DXF views from the canonical model, e.g. after prepare_template.

| Parameter | Type | Required | Default |
| --- | --- | --- | --- |
| `project` | string | yes |  |
| `floor` | string | yes |  |
| `views` | list of `architectural` \| `lighting` \| `power` \| `combined` | no | `None` |
| `overwrite_manual_edits` | boolean | no | `False` |

### `export_package`

Write the drawing package: DXF per view, DWG (needs live AutoCAD or ODA File Converter; otherwise reported as skipped), PNG previews, A3 PDF sheets and manifest.json with hashes and the validation result.

| Parameter | Type | Required | Default |
| --- | --- | --- | --- |
| `project` | string | yes |  |
| `floor` | string | yes |  |
| `views` | list of `architectural` \| `lighting` \| `power` \| `combined` | no | `None` |
| `overwrite_manual_edits` | boolean | no | `False` |

### `validate_drawing`

Validate model consistency and the generated files: devices/circuits/routes, labels, layers, architecture preserved vs reference, reference hash, manual edits, reopen check.

| Parameter | Type | Required | Default |
| --- | --- | --- | --- |
| `project` | string | yes |  |
| `floor` | string | yes |  |

## Live editing (plan symbols)

Windows + AutoCAD / AutoCAD Electrical running. These edit the **open drawing directly**.

### `live_connect`

LIVE (Windows): attach to the drawing open in AutoCAD / AutoCAD Electrical and report its name, entity counts per layer and unit scale. Start here. All live_* tools edit the open drawing directly, so the user sees every change on screen.

_No parameters._

### `live_selftest`

LIVE: prove the connection works. Creates a DB, luminaire and route on the ACTIVE drawing, moves and reads them back, then removes them. Run on a scratch drawing the first time.

_No parameters._

### `live_scan`

LIVE: find symbols in the open drawing (loose LINEs that touch are clustered per device layer, as in the reference drawings). Returns type, centre and size of each, not yet tracked.

| Parameter | Type | Required | Default |
| --- | --- | --- | --- |
| `layers` | list of string | no | `None` |

### `live_adopt`

LIVE: give the existing symbols in the open drawing stable ids (e.g. 4F-LUM-01, DB-4F) by grouping them, so they can be moved, deleted or assigned by id. Geometry is not changed. Use min_size/max_size (drawing units) to skip tiny pieces such as socket pins.

| Parameter | Type | Required | Default |
| --- | --- | --- | --- |
| `floor` | string | yes |  |
| `layers` | list of string | no | `None` |
| `min_size` | number | no | `0.0` |
| `max_size` | number | no | `1000000000000.0` |

### `live_list_devices`

LIVE: tracked devices/routes with positions read fresh from the drawing (flags devices the user moved by hand, and ones deleted by hand).

_No parameters._

### `live_texts`

LIVE: read TEXT in the open drawing with positions (e.g. layer 'TEXT' for room names, to work out where a room is before placing devices).

| Parameter | Type | Required | Default |
| --- | --- | --- | --- |
| `layer` | string | no | `None` |
| `contains` | string | no | `None` |

### `live_place`

LIVE: draw a device symbol (reference style, correct layer) at x,y in the open drawing now. Same type at the same spot is not duplicated. One undo step.

| Parameter | Type | Required | Default |
| --- | --- | --- | --- |
| `floor` | string | yes |  |
| `type` | `luminaire` \| `switch` \| `socket` \| `data` \| `ac` \| `emergency` \| `db` | yes |  |
| `x` | number | yes |  |
| `y` | number | yes |  |
| `rotation` | number | no | `0.0` |
| `circuit` | string | no | `None` |
| `db` | string | no | `None` |
| `room` | string | no | `None` |

### `live_move`

LIVE: move a tracked device to x,y or by dx,dy. Routes through it are flagged stale.

| Parameter | Type | Required | Default |
| --- | --- | --- | --- |
| `device_id` | string | yes |  |
| `x` | number | no | `None` |
| `y` | number | no | `None` |
| `dx` | number | no | `None` |
| `dy` | number | no | `None` |

### `live_delete`

LIVE: delete a tracked device from the open drawing (one undo step).

| Parameter | Type | Required | Default |
| --- | --- | --- | --- |
| `device_id` | string | yes |  |

### `live_assign`

LIVE: record which circuit / distribution board a device belongs to.

| Parameter | Type | Required | Default |
| --- | --- | --- | --- |
| `device_id` | string | yes |  |
| `circuit` | string | yes |  |
| `db` | string | no | `None` |

### `live_route`

LIVE: draw (or redraw, replacing the old one) an orthogonal route from the DB through the circuit's devices on the lighting/power/AC wiring layer, labelled with the circuit id.

| Parameter | Type | Required | Default |
| --- | --- | --- | --- |
| `circuit` | string | yes |  |
| `kind` | `lighting` \| `power` \| `ac` | yes |  |
| `device_ids` | list of string | no | `None` |
| `db` | string | no | `None` |
| `label` | boolean | no | `True` |

### `live_add_text`

LIVE: add a TEXT note/label to the open drawing.

| Parameter | Type | Required | Default |
| --- | --- | --- | --- |
| `layer` | string | yes |  |
| `text` | string | yes |  |
| `x` | number | yes |  |
| `y` | number | yes |  |
| `height` | number | yes |  |

### `live_add_polyline`

LIVE: draw a polyline [[x,y],...] on a layer in the open drawing.

| Parameter | Type | Required | Default |
| --- | --- | --- | --- |
| `layer` | string | yes |  |
| `points` | list of list of number | yes |  |

### `live_zoom`

LIVE: pan/zoom AutoCAD's view to x,y so the user can see the change.

| Parameter | Type | Required | Default |
| --- | --- | --- | --- |
| `x` | number | yes |  |
| `y` | number | yes |  |
| `width` | number | yes |  |

### `live_undo`

LIVE: undo the last chat instruction in AutoCAD (each live_* call is one undo step).

_No parameters._

### `live_save`

LIVE: save the open drawing (or Save As to path).

| Parameter | Type | Required | Default |
| --- | --- | --- | --- |
| `path` | string | no | `None` |

## Mode switch

Choose between plan-symbol tools and AutoCAD Electrical schematic tools.

### `live_set_mode`

Choose what the live tools work with. 'plan' (default): floor-plan symbols and routes (live_place, live_route...). 'schematic': AutoCAD Electrical schematics (sch_* tools); the plan-level drawing tools are then blocked so the two are never mixed by accident. Only switch to 'schematic' when the user asks to work with schematics.

| Parameter | Type | Required | Default |
| --- | --- | --- | --- |
| `mode` | `plan` \| `schematic` | yes |  |

## Schematic mode (AutoCAD Electrical)

Read and probe only for now. Enabled with `live_set_mode('schematic')`.

### `sch_detect`

SCHEMATIC: check the open drawing / AutoCAD Electrical: product and version, whether the Electrical commands are loaded, whether the AutoLISP bridge works, and how many components, wire numbers and wire lines the drawing has. Run this first in schematic mode.

_No parameters._

### `sch_read`

SCHEMATIC: read the open schematic: components (tag, description, installation, location, manufacturer, catalog, terminals), wire numbers and wire-layer line counts. Read-only.

| Parameter | Type | Required | Default |
| --- | --- | --- | --- |
| `include_wires` | boolean | no | `True` |
| `limit` | integer | no | `500` |

### `sch_probe`

SCHEMATIC: list the AutoLISP functions/commands this AutoCAD Electrical install exposes whose name starts with prefix (try c:ae, c:wd, c:ace, wd_, ace_). Read-only; used to learn the real command names before insert/wire tools are built.

| Parameter | Type | Required | Default |
| --- | --- | --- | --- |
| `prefix` | string | no | `c:ae` |
| `limit` | integer | no | `400` |

### `sch_run_lisp`

SCHEMATIC (advanced): evaluate an AutoLISP expression in the open drawing and return its printed result. Can change the drawing, so it is disabled unless the server was started with ACAD_MCP_ALLOW_COMMANDS=1.

| Parameter | Type | Required | Default |
| --- | --- | --- | --- |
| `expression` | string | yes |  |

## AutoCAD utilities (Windows)

Direct AutoCAD COM helpers.

### `acad_status`

(Windows) Report the running AutoCAD / AutoCAD Electrical session via COM.

_No parameters._

### `acad_open`

(Windows) Open a drawing read-only in the running AutoCAD session.

| Parameter | Type | Required | Default |
| --- | --- | --- | --- |
| `path` | string | yes |  |

### `acad_run_command`

(Windows) Send a command line to the active AutoCAD document. Disabled unless the server was started with ACAD_MCP_ALLOW_COMMANDS=1 because commands can modify any open drawing.

| Parameter | Type | Required | Default |
| --- | --- | --- | --- |
| `command` | string | yes |  |
