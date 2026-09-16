# Facial likeness controls: investigation

## September 16 implementation update

The MCP now exposes deterministic anatomy, sculpt and refinement tools in `src/tools/fitting.ts`. These are control primitives: no critic, rating, landmark prediction or automatic likeness choices.

### Anatomy

- `refresh_anatomy_morphs`: invokes CC5 **Refresh Sliders**. This restored the full head/body catalog on the reopened test project, which initially exposed only eye-occlusion/tear-line morphs. Showing the morph panel alone did not fix that state.
- `show_headshot_morphs`: opens the Headshot morph panel.
- `get_anatomy_morphs`: fresh IDs, names, categories, weights and slider-specific native min/max values. SWIG FloatPair values require `.first`/`.second`, not tuple unpacking. Observed ranges can change after a catalog refresh; always query current metadata.
- `snapshot_anatomy_morphs`: serializable snapshot, optionally restricted to specified IDs.
- `set_anatomy_morphs`: absolute weights; rejects invalid, duplicate, nonfinite, out-of-range or stale expected values before writing. Checks native status and final readback; attempts rollback on error and reports whether the attempted changes were restored.
- `restore_anatomy_morphs`: restores the exact snapshot on the same live avatar ID. This restores weights, not arbitrary mesh refinement, textures, cameras or an entire project. Reopening a project changes avatar IDs; snapshots must be re-established.

Legacy single/batch morph setters now use the same validated Python setter. Prefer the new tools for structured before/requested/actual results and explicit avatar selection. No automatic retries are introduced.

### Sculpt controls

`get_sculpt_settings` and `configure_sculpt` cover enabled state, front/side, all six regions, symmetry, control-area visibility, dark mode, overlay opacity and zoom-to-area. Use numerical morph setters for reproducible anatomical changes; these tools select the sculpt interface and its settings, not an AI-chosen viewport gesture.

### Front and side refinement

- `open_face_refinement`, `get_face_refinement`, `close_face_refinement` control the editor lifecycle.
- `load_refinement_side_reference` fills the native file picker opened by that command with an existing absolute local image. No diffusion is invoked.
- `configure_face_refinement` sets available alignment/overlay numbers and part/mirror toggles. Field IDs, readable labels, ranges and enabled states come from `get_face_refinement`. Side alignment IDs: `qtRotateXSlider` = Rotate; `qtTranslateXSlider` = Move X; `qtTranslateYSlider` = Move Y; `qtTranslateZSlider` = Scale. Values are native UI units.
- `move_face_refinement_point` sends a native press/multiple-move/release sequence to the editor viewport. It uses **scene coordinates** and returns actual coordinates plus a tolerance derived from viewport pixel size. CC5 can constrain a movement, so clients must inspect success/readback. This is not an exact floating-point mesh-vertex setter.
- `face_refinement_action` invokes an explicit available preview, edit, apply, reset, align, adjust or finish action. Apply is a long native operation. A returned action is not proof of artistic quality.
- `get_headshot_landmarks` reads the plugin's native arrays; point indexing remains native/opaque. The Qt editor path avoids guessing the undocumented `RefineMesh` array contract.

Read fresh refinement state after each stage change and before each edit. Graphics point IDs are session-local and must not be saved as a portable character recipe. A revision checks the current avatar, visible points, controls and numeric settings; stale calls fail before mutation. Viewport quantization, dependent controls and asynchronous rendering can require another state read. Scene/sculpt changes are blocked while refinement is open, even when the editor is nonmodal. Unrelated modal dialogs remain blocked by the bridge.

Closing the editor does not undo any already-applied refinement. Save a separate project checkpoint before applying. A morph-weight snapshot alone is insufficient for this operation.

### Recovery dialog

Workspace `tools/launch_cc5_clean.py` starts the hidden, PID-scoped `tools/cc5_recovery_guard.ps1`. It selects **Cancel** only for the exact “Unsaved project data found…” recovery prompt, preserving the saved project rather than restoring unsaved crash-session data. It watches that launched process until exit and also handles later project-open prompts. It does not disable CC5 recovery globally or automatically affect launches through other shortcuts. Other dialogs are untouched.

The following September 15 sections describe discovery history; the implementation above supersedes their not-implemented notes.

### Verification, September 16

- Actual MCP stdio / authenticated HTTP / CC5 queue: refresh, catalog, snapshot, chin-depth change, native readback, exact restoration, out-of-range rejection, sculpt configuration/restoration and landmark readback all passed. Private local evidence: `fitting-mcp-smoke.json`.
- Actual MCP transport: front point move, native preview, native Apply All and close passed. Private local evidence: `refinement-mcp-smoke.json`. The coordinates returned reflect actual native movement, not the requested value echoed back.
- GUI-thread adapter: side reference load, rotate/move/scale set and restore, alignment finish, side point move, preview and Apply All passed. After applying, native side landmarks became available. Private local evidence: `fitting-loadside.json`, `fitting-sidealignset.json`, `fitting-sidealignrestore.json`, `fitting-sidepoint.json`, `fitting-sidepreview.json`, `fitting-sideapply.json`, `fitting-sideappliedlandmarks.json`.
- One earlier preview trial crashed CC5. A fresh session and corrected Qt-wrapper lifetime handling subsequently completed front and side tests; this does not establish that every native combination is crash-free. Operation-status handling and separate project checkpoints remain necessary.
- Build, 473 TypeScript tests and 35 Python tests pass. Tests cover native FloatPair decoding, ranges/nonfinite input, stale state, duplicate IDs, rollback failure, wrong-avatar restoration and modal isolation.
- Updated source is built and loaded in the isolated lab bridge on port 5102. Permanent startup/MCP registration is not changed. Keep the Node build and Python plugin files in sync when activating outside the lab.
- The final disposable result saved successfully to workspace `builds/character-preview/headshot-lab/fitting-controls-20260916.ccProject` (178,728,489 bytes). This checkpoint has not been separately reopened.

Remaining limits: not every sculpt region/preset/part combination was exercised; partial apply, reset and mirror combinations are mapped but not individually live-qualified. The undocumented direct `RefineMesh` argument contract, viewport sculpt-drag-to-morph mapping, photo reprojection tooling and automated likeness assessment are not implemented here. Refinement is controlled through the verified editor path. The test character is functional evidence, not accepted art.

## Historical discovery notes (superseded by the implementation above)

September 15, 2026. Investigated installed CC5/Headshot 3 in disposable lab PID 66584. This is discovery and a native morph roundtrip test, not a completed automated fitting system.

## Live findings

- `RIAvatarShapingComponent` enumerates categories, exact morph IDs, display names, current weights, and per-slider limits (`GetShapingMorphMinMax`). Use shaping morphs for persistent anatomy, not expression animation keys.
- The current character exposes 1,084 entries in `Actor/Headshot` including dedicated chin, cheek, jaw, nose, eye and head controls. Categories also contain descendants, so deduplicate by ID. Display names alone are not unique.
- Observed limits include 0..1, -0.5..1 and -1..1. Do not assume negative weights are supported or always mean smaller.
- Native Chin Height, Chin Width and Chin Depth were each changed from 0 to 0.05, read back as 0.05000000074505806, then restored to 0. Native statuses were successful. No crash occurred. This verifies numeric mutation/restoration, not the size or direction of the visible anatomical change.
- Existing MCP setters clamp to -1..1 and echo requested values without checking native status or actual readback. Before automated iteration, expose native limits, reject invalid/nonfinite values, return before/requested/actual values, and restore exact snapshots rather than zeroing all morphs. A zero reset can erase intentional identity settings.

## Headshot refinement

Runtime exposes `GetLandmarks(bFront)` and `RefineMesh(array2D, array2D, arrayBool)`. This character returned 635 front points and zero side points. Example front coordinates were (84,158), (85,185), (88,211); units, indexing and boolean-mask semantics remain unverified. Do not assume they are normalized coordinates or correspond to a generic face detector. Search did not surface an authoritative public contract for RefineMesh.

The front refinement dialog opened successfully through `qtLandmarkEditorPushButton`. No refinement was applied. The installed `CCCreateHeadStageTwoDlg` exposes front `StageTwoFix`, side `SideStageTwoFix`, preview methods, `AutoAlignHeadMesh`, `SideViewMove`, and `ExportLandmarks` Qt signatures. Discovery of signatures does not establish Python-callable argument types or safe semantics. The side application path is visibly distinct from front; do not assume the two RefineMesh arrays mean front and side.

Next refinement experiment: establish front/side landmark export format and coordinate mapping, align a side reference through the normal UI, verify landmark readback, then test a no-change refinement before a small reversible edit on a saved disposable copy. Side-reference presence during generation is not proof that side landmarks are initialized for refinement.

## Recommended sequence

1. Save the generated baseline and snapshot its exact anatomy morph weights. Keep expressions neutral.
2. Establish reproducible front and strict profile captures: fixed pose, framing, lens/projection, lighting and visibility. Camera mismatch must not become an anatomy correction.
3. Use numeric morphs for broad shape: head proportions, cheek fullness, jaw width, chin projection, nose dimensions. Start with a small curated subset, symmetry enabled where appropriate, and small changes relative to each slider's range.
4. Refine front contour curves, then align and refine side depth. Recheck both views after each accepted change, plus a three-quarter view for distortions hidden in two projections.
5. Reproject the source texture after shape fitting, if texture features drift. This changes texture alignment, not geometry.
6. Only then assess skin, hair and lighting separately. Front and side AI references may disagree; neither guarantees a unique 3D solution.

Sculpt Morph is a useful interactive region-based interface: Contour, Face, Eyes, Nose, Mouth and Ears. The side tool adjusts depth only. Prefer explicit numeric sliders for reproducible automation; mapping sculpt gestures to slider changes remains untested. External Blender sculpt/custom morphs are a fallback for shapes the available controls cannot express, and require a topology-preserving roundtrip qualification.

## Evidence and sources

Private local evidence (not distributed): `builds/character-preview/headshot-lab/morph-discovery.json`, `morph-roundtrip.json`, `refine-front-ui.json`. Probe scripts: `tools/cc5_morph_probe.py`, `cc5_morph_roundtrip.py`, `cc5_refine_probe.py`.

- [Front refinement](https://manual.reallusion.com/Headshot_Plugin/ENU/3.0/04-Image-Mode/Refining-Face.htm): broad sculpt first, then contour fitting; supports preview and apply.
- [Side refinement](https://manual.reallusion.com/Headshot_Plugin/ENU/3.0/04-Image-Mode/Refining-Side-Face.htm): eye/lip anchors, placement alignment, then control-point refinement.
- [Sculpt Morph Side](https://manual.reallusion.com/Headshot_Plugin/ENU/3.0/07-Shape-Adjustment/On-Screen-Sculpt-Morph-Design-Side.htm): six regions, depth editing.
- [Photo reprojection](https://manual.reallusion.com/Headshot_Plugin/ENU/3.0/04-Image-Mode/Photo-Re-Projection.htm): texture realignment after morph edits.

Not implemented in this investigation: critic/rating loop, standardized captures, production morph-setter changes, automated front/side point fitting, sculpt-gesture automation, or external sculpt roundtrip.
