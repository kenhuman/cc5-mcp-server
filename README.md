# CC5 MCP Server

Control Reallusion Character Creator 5 from an MCP client through a local Python bridge. Includes Headshot 3 generation from existing photos, deterministic morph controls, and front/side face refinement.

This is an independently maintained fork of [mackatwentytsuru/cc5-mcp-server](https://github.com/mackatwentytsuru/cc5-mcp-server). The upstream Git history is retained. See [provenance](NOTICE.md).

**Development status:** tested on Windows with CC5 5.13 and Headshot 3. Offline tests and focused live trials pass. Native UI integration remains version-sensitive; this is not a fully qualified unattended character-production system. See [status and limitations](docs/STATUS.md).

## Architecture

MCP client → Node.js/TypeScript (stdio) → authenticated localhost HTTP → Python/Qt inside CC5 → native character APIs.

All native calls run on CC5's GUI thread. Operation IDs distinguish queued cancellation from an unknown outcome after a native call has started. Never repeat a timed-out mutation blindly.

## Features

- Scene, avatar, assets, materials, lighting, camera, and expression tools inherited from upstream.
- Headshot: front/side/body reference images, Generate Hair, seven face-setting tabs and both body modes. Uses existing images, not text-to-image generation. [Headshot guide](docs/HEADSHOT.md).
- Anatomy morph catalog with native limits, validated values, actual readback, snapshots and restoration.
- Sculpt region, symmetry and display controls; front/side refinement reference alignment, point movement, preview and apply. [Refinement guide](docs/MORPH_REFINEMENT.md).
- Read-only startup, shared-token authentication, pause file, operation status, deduplication, capability inspection, and opt-in experimental functions.

## Requirements

- Windows, licensed Character Creator 5; Headshot tools additionally require Headshot 3.
- Node.js 22 or newer and npm.
- CC5's embedded Python, RLPy and PySide2. Ordinary Python is only needed for offline tests.

## Setup

```powershell
git clone https://github.com/kenhuman/cc5-mcp-server.git
cd cc5-mcp-server
npm ci
npm run build
```

1. Generate a random shared token of at least 32 characters. Set `CC5_BRIDGE_TOKEN` in **both the CC5 process environment and the MCP server environment**. Setting it only in the MCP client does not configure CC5.
2. For manual startup, load this repository's `start_bridge.py` through CC5's Python script loader. Load it once per CC5 session. For installed startup, close CC5 and run `./install-plugin.ps1` from an elevated PowerShell session, then restart CC5 with the environment configured. The installer copies every required Python module.
3. Configure your MCP client (replace the path and token):

```json
{
  "mcpServers": {
    "cc5": {
      "command": "node",
      "args": ["G:/development/cc5-mcp-server/build/index.js"],
      "env": {
        "CC5_BRIDGE_URL": "http://127.0.0.1:5101",
        "CC5_BRIDGE_TOKEN": "REPLACE_WITH_YOUR_RANDOM_SHARED_TOKEN"
      }
    }
  }
}
```

4. Call `check_cc5_connection` and `get_bridge_status`. Initially, native mutations are disabled. To enable them, launch **CC5** with `CC5_READ_ONLY=0`. Save a disposable project before live experimentation.

To update Python code, restart CC5 and load/install matching plugin files. Runtime hot reload is disabled. Rebuilding Node alone does not update an already loaded bridge.

## Configuration

| Variable | Meaning |
|---|---|
| `CC5_BRIDGE_TOKEN` | Required shared secret, at least 32 characters. Never commit it. |
| `CC5_BRIDGE_PORT` | CC5 plugin port, default `5101`. |
| `CC5_BRIDGE_URL` | Node client URL, default `http://127.0.0.1:5101`. Match the plugin port. |
| `CC5_READ_ONLY` | Plugin defaults to `1`; explicit `0` enables mutations. |
| `CC5_PAUSE_FILE` | Plugin defaults to `<user home>/.cc5-mcp/PAUSED`. Create the file to pause queued native work; remove it to resume. Does not interrupt an in-progress native call. |
| `CC5_ALLOW_EXPERIMENTAL` | `1` enables unqualified export, bake and selected plugin automation routes. Default off. |
| `CC5_ALLOW_EXEC` | Additional `1` required for arbitrary Python execution. Default off. |
| `CC5_ALLOW_WINDOW_CAPTURE` | `1` permits window-region screenshot fallback; may include overlapping windows. Default off. |
| `CC5_DEV_MODE` | API discovery detail, default `0`; does not enable reload or execution. |
| `CC5_REQUEST_TIMEOUT_MS` | Node client wait; a timeout does not prove native work failed. |

Authentication applies to health endpoints too. The bridge binds to localhost and rejects browser-origin requests. It is intended for trusted local clients, not exposure over a network.

## Development and tests

```powershell
npm ci
npm run build
npm test
python -m unittest discover -s tests -p 'test_*.py'
```

Offline tests do not launch CC5. CI runs them on Windows. Live tests are separate and may change the open character. Set `CC5_LIVE_TEST=1`, an absolute `CC5_LAB_DIR` for output, `CC5_BRIDGE_URL` and `CC5_BRIDGE_TOKEN`, then run one of:

```powershell
node scripts/headshot_live_smoke.mjs
node scripts/fitting_live_smoke.mjs
node scripts/refinement_live_smoke.mjs
```

The Headshot configuration test also requires `CC5_FRONT_REFERENCE`. It opens/configures the dialog; it does not generate a character. Fitting tests require an already-open disposable Headshot character. The refinement test applies an edit. Reference images, CC5 assets, live reports and credentials are not distributed here.

The older comprehensive `scripts/live_smoke_test.py` exercises experimental routes and is not a release acceptance suite. Full FBX/Blender round-trip, all UI combinations, and recovery after every possible native crash remain unqualified.
