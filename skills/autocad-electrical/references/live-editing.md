# Live editing in AutoCAD

Windows only, with the server on the same PC and user as AutoCAD. Every `live_*` call edits the
**active drawing** immediately and is one undo step.

1. `live_connect`: drawing name, layers, `unit_scale_vs_mm` (trust it over the header units),
   and whether the drawing is a protected base (if so, stop and open the working copy).
2. Existing symbols: `live_scan` to see them, `live_adopt` to give them ids without moving them.
   `live_texts` finds room names and positions.
3. Changes: `live_place`, `live_move`, `live_assign`, `live_route`, `live_add_text`,
   `live_add_polyline`. Use `live_zoom` to show the user each change.
4. Mistake: `live_undo` reverts the last instruction. `live_delete` removes a tracked device:
   confirm first.
5. Many devices: `live_place_from_table` in batches, then `live_verify_placement`.
6. After a crash or reconnect: `live_resync`; `work_log` shows what was done.
7. `live_save` only when the user asks; never over a registered base.

`live_set_mode` switches between plan symbols (`plan`, default) and AutoCAD Electrical schematics
(`schematic`, where the `sch_*` tools apply and plan drawing tools are blocked).
