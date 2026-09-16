# Implementation status

September 16, 2026. Standalone development fork; initial upstream base `d842cf241bf6888860c9fbf9f198ad33fe4e11dd`.

## Implemented

- Authenticated localhost HTTP, browser-origin rejection, read-only default, pause file, experimental and execution opt-ins.
- Operation IDs, same-ID deduplication, queued cancellation and unknown-outcome tracking. A bounded 1,000-entry journal refuses new work when full; history is session-local and does not survive CC5 crashes.
- Independent HTTP health and GUI-thread heartbeat; modal-dialog isolation and one queued job per timer tick.
- Headshot generation settings and deterministic morph/sculpt/front-and-side refinement controls. See [Headshot](HEADSHOT.md) and [refinement](MORPH_REFINEMENT.md).

## Verification

473 TypeScript tests and 35 Python tests passed before standalone packaging. Focused live tests ran against CC5 5.13 / Headshot 3: two character-generation combinations, morph write/read/restore, sculpt settings, front refinement through MCP transport, and side reference/alignment/point movement/preview/apply through the GUI-thread adapter.

Detailed live reports and project checkpoints remain private local artifacts, not downloadable fixtures. No CC5 character assets, input photos or credentials are bundled.

## Limits

- Native plugin calls can crash CC5. One refinement preview trial crashed; later trials passed after Qt-wrapper lifetime fixes. This is not proof all native combinations are stable.
- The legacy `RLPy.RHeadshot.CreateHeadFromPhoto` path is not used by these Headshot 3 tools: a debugger investigation found a missing legacy interface on the tested installation.
- Not every face/body/preset, partial-apply, reset or mirror combination has been live-tested. UI resource/widget changes in other versions may require adapter updates.
- Point movement has viewport-pixel precision; IDs and revisions are live-session state. Snapshots restore morph weights, not refinement geometry or entire projects.
- Full export/import, rig deformation, materials and checkpoints from combined-option tests are not fully qualified. Export remains experimental.
- No automated likeness critic, fit optimization, custom-hair generator, full portable character recipe, or durable crash-recovery job manager is included.
- Separate game-project launch/debugging helpers are not part of this MCP. Installing it does not automatically dismiss CC5 recovery dialogs.

The public repository is suitable for development and controlled testing; production character batches need further qualification.
