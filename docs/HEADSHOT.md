# Headshot 3 tools

Implemented for CC5 5.13 / Headshot 3. The controls omitted by the public RLPy2 method use the real Generate Character dialog through named Qt widgets and its `GenerateHead` slot. No screen-coordinate clicking, text-to-image diffusion, or paid image generation is used.

## Tools

1. `get_headshot_options`: enumerate all 64 presets in seven tabs from the installed UI resource, including native exclusive groups, readable labels, and body choices.
2. `open_headshot`: open Generate Character using an existing local front image. The Headshot 3 IMAGE panel must be visible. Poll settings until `open` is true.
3. `configure_headshot`: load front, optional side, and optional body references; set hair, face presets, and body controls. Returns selected settings and a single-use `prepared_id`.
4. `get_headshot_settings`: inspect selected settings and enabled controls.
5. `generate_headshot`: generate the prepared character. Rejects a stale ID or changed selections/thumbnails. Consumes the ID before entering native generation.

All actions retain the bridge's authentication, read-only mode, pause marker, operation IDs and deduplication. During the Headshot modal dialog, only Headshot actions may execute; other scene mutations wait. Unrelated modal dialogs still block all queued work. Generation can exceed HTTP timeout: inspect `get_operation_status` using the returned operation ID; never repeat it with a new ID while the outcome is unknown.

## Coverage

| Control | Values |
|---|---|
| References | Front required; side optional; full-body required in photo mode |
| Generate Hair | `true` / `false` |
| Face tabs | `face`, `forehead`, `cheeks` (includes mouth), `chin`, `eyes`, `nose`, `ears` |
| Body mode | `type`, `photo` |
| Body type | `current`, `neutral`, `male`, `female`, `child`, `baby` |
| Type age | `adult`, `elder`, `teen` |
| Type shape | `normal`, `skinny`, `heavy`, `strong` |
| Photo shape | `average`, `heavy`, `slim` |
| Photo gender | `male`, `female` |
| Photo physique | `normal`, `muscular` |

Use preset IDs from the catalog, not guessed labels. Catalog IDs retain stable resource keys (e.g. `oval`); labels reflect the installed UI (e.g. “Oval Face”). Options in one exclusive group cannot be combined. Options without an exclusive group support multiple selections. Face options reset through the dialog's Clear All control before applying a configuration; omitted face tabs use Normal/default. An omitted side reference clears a previously loaded side reference. Body fields are applied in native order; omitted body fields retain the dialog's selection. Provide explicit applicable body fields for reproducible recipes.

CC5's enabled-state rules are authoritative. For example, Elder disables type-body shape controls; request Elder without a shape override. Child/Baby and Current also restrict applicable controls. Invalid or disabled choices raise an error. A failed configuration may leave a partially edited dialog but never starts generation and never retains a usable prepared ID.

### Example

```json
{
  "front": "G:/references/female-front.png",
  "side": "G:/references/female-side.png",
  "generate_hair": false,
  "face": {"face": ["oval"], "chin": ["jaw_line_define"]},
  "body": {"mode": "type", "type": "female", "age": "adult", "shape": "normal"}
}
```

Photo body mode replaces the body object with `{"mode":"photo","photo_shape":"slim","photo_gender":"female","photo_physique":"normal"}` and requires `body_image`.

## Verification (September 15, 2026)

- Live generation: front + side, hair off, oval face, Female/Adult/Normal type body. Generated bald character visually confirmed; application remained responsive.
- Live generation: front + side + body photo, hair on, selected presets in every face tab, Slim/Female/Normal photo body. Returned, remained responsive, and saved successfully as a 175,533,899-byte project. This is a functional test character, not approved art.
- MCP stdio → TypeScript client → authenticated HTTP → CC5 main thread: five tools listed, all 64 catalog entries returned, configuration and readback passed. Adult/Strong and hair-off settings confirmed. Elder/Strong correctly rejected because the native control is disabled.
- Build passes; 470 TypeScript tests and 20 Python tests pass, including no-retry behavior, stale preparation, exclusive selections, required references and modal isolation.

Private local evidence (not distributed): workspace `builds/character-preview/headshot-lab/ui-configure4.json`, `ui-generate1.json`, `ui-configureAll.json`, `ui-generateAll.json`, `mcp-headshot-smoke.json`, `side-hair-off-generated.png`, `all-tabs-photo-body-hair-on.png`, and `headshotAllOptions66584.ccProject`.

The 64 choices are mapped from the installed dialog; every possible preset combination has not been generated. Layout changes fail on missing/ambiguous named controls. No claim is made that a successful dialog return proves final likeness, good hair, export quality or animation quality. Project reopening was previously qualified for the simpler native Headshot 3 case; this combined-options sample has been saved but not separately reopened.

## Running

Use the rebuilt `build/index.js` with the matching `cc5-plugin` files. The existing bridge token/read-only/pause configuration still applies; source updates do not replace an already loaded Python module. Restart the bridge/CC5 to load updated plugin code. The isolated live test used port 5102 and a temporary local token, with the production pause marker untouched. `scripts/headshot_live_smoke.mjs` is an explicit lab test, not an automatic startup task.
