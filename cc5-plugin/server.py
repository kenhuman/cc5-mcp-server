"""
HTTP bridge server for CC5 MCP plugin.

Uses Python's built-in http.server — no external dependencies needed.
All RLPy calls are queued and executed on the main thread via QTimer.
"""

from __future__ import annotations

import hmac
import importlib
import json
import os
import queue
import sys
import threading
import traceback
import time
import re
from operations import Operations
from http.server import BaseHTTPRequestHandler, HTTPServer, ThreadingHTTPServer
from typing import Any
from urllib.parse import urlparse

import cc5_api
import headshot
import morph_control
import fitting
from capabilities import get_capabilities

RELOAD_SECRET = os.environ.get("CC5_RELOAD_SECRET", "")
DEV_MODE = os.environ.get("CC5_DEV_MODE", "0") == "1"  # Development surfaces disabled by default
API_VERSION = "1.2.0"
BRIDGE_TOKEN = os.environ.get("CC5_BRIDGE_TOKEN", "")
READ_ONLY = os.environ.get("CC5_READ_ONLY", "1") != "0"
PAUSE_FILE = os.environ.get("CC5_PAUSE_FILE", os.path.join(os.path.expanduser("~"), ".cc5-mcp", "PAUSED"))
operations = Operations()
EXPERIMENTAL_ACTIONS = {
    "export_fbx", "exec_python", "bake_skin_textures", "export_head_metahuman",
    "silent_install_filter", "silent_trigger_dialog", "silent_configure_and_click",
    "silent_finalize", "create_actor_mixer",
}


def execution_block(action):
    if paused():
        return "Automation pause marker is present"
    if READ_ONLY and action not in READ_ACTIONS:
        return "Bridge is read-only"
    if action in EXPERIMENTAL_ACTIONS and os.environ.get("CC5_ALLOW_EXPERIMENTAL") != "1":
        return "Operation requires live qualification; CC5_ALLOW_EXPERIMENTAL is disabled"
    return None


def paused():
    return bool(PAUSE_FILE and os.path.exists(PAUSE_FILE))


# Thread-safe command queue: HTTP thread -> main thread
command_queue: queue.Queue = queue.Queue(maxsize=100)
_processing = False  # Re-entrance guard for process_command_queue

MAX_REQUEST_BYTES = 1 * 1024 * 1024  # 1 MB

# Module-level reference for shutdown
_httpd: HTTPServer | None = None


# --- Required parameters per action (validated before queue dispatch) ---

REQUIRED_PARAMS: dict[str, list[str]] = {
    'headshot_configure': ['front', 'generate_hair', 'body'],
    'headshot_generate': ['prepared_id'],
    "search_morphs":        ["query"],
    "get_morph_value":      ["morph_id"],
    "set_morph_value":      ["morph_id", "value"],
    "set_multiple_morphs":  ["morphs"],
    "load_asset":           ["file_path"],
    "export_fbx":           ["output_path"],
    "set_subdivision_level": ["level"],
    "set_camera_focal_length": ["focal_length"],
    "set_light_color":      ["light_name", "r", "g", "b"],
    "get_light_info":       ["light_name"],
    "set_light_multiplier": ["light_name", "multiplier"],
    "set_light_active":     ["light_name", "active"],
    "set_light_shadow":     ["light_name"],
    "set_ambient":          ["r", "g", "b"],
    "set_expression":       ["expressions"],
    "get_diffuse_color":    ["mesh_name", "material_name"],
    "set_diffuse_color":    ["mesh_name", "material_name", "r", "g", "b"],
    "get_material_properties": ["mesh_name", "material_name"],
    "set_material_opacity":    ["mesh_name", "material_name", "opacity"],
    "set_material_glossiness": ["mesh_name", "material_name", "glossiness"],
    "set_material_specular":   ["mesh_name", "material_name", "specular"],
    "get_shader_parameters":   ["mesh_name", "material_name"],
    "set_shader_parameter":    ["mesh_name", "material_name", "parameter_name", "values"],
    # Tier 1: Content Management
    "remove_scene_item":    ["item_name"],
    # Tier 3: Convenience Color Shortcuts
    "set_eye_color":        ["r", "g", "b"],
    "set_hair_color":       ["r", "g", "b"],
    "set_lip_color":        ["r", "g", "b"],
    "set_skin_color":       ["r", "g", "b"],
    # Tier 4: Visibility
    "set_item_visible":     ["item_name", "visible"],
    "exec_python":          ["code"],
    # Mesh-to-MetaHuman pipeline helpers
    "export_head_metahuman":   ["output_dir", "character_name"],
    "silent_install_filter":   ["output_dir", "character_name"],
    # ActorMIXER PRO: Create Mixer Assets (safety gate)
    "create_actor_mixer":      ["confirm_create"],
}

# --- Dynamic dispatch tables (can be hot-patched at runtime) ---

ACTION_MAP: dict[str, Any] = {
    'morph_refresh': lambda p: morph_control.refresh(),
    'fitting_morph_panel': lambda p: fitting.show_morph_panel(),
    'fitting_load_side': lambda p: fitting.load_side_reference(**p),
    'fitting_configure': lambda p: fitting.configure_refine(**p),
    'morph_catalog_live': lambda p: morph_control.catalog(**p),
    'morph_snapshot': lambda p: morph_control.snapshot(**p),
    'morph_apply': lambda p: morph_control.apply(**p),
    'morph_restore': lambda p: morph_control.restore(**p),
    'fitting_sculpt_state': lambda p: fitting.sculpt_state(),
    'fitting_sculpt_configure': lambda p: fitting.configure_sculpt(**p),
    'fitting_open': lambda p: fitting.open_refine(**p),
    'fitting_state': lambda p: fitting.refine_state(),
    'fitting_move_point': lambda p: fitting.move_refine_point(**p),
    'fitting_action': lambda p: fitting.refine_action(**p),
    'fitting_close': lambda p: fitting.close_refine(),
    'fitting_landmarks': lambda p: fitting.landmarks(**p),
    'headshot_catalog': lambda p: headshot.catalog(),
    'headshot_state': lambda p: headshot.state(),
    'headshot_open': lambda p: headshot.open_dialog(p.get('front')),
    'headshot_configure': lambda p: headshot.configure(p),
    'headshot_generate': lambda p: headshot.generate(p['prepared_id']),
    "get_avatars":           lambda p: cc5_api.get_avatars(),
    "get_avatar_info":       lambda p: cc5_api.get_avatar_info(),
    "get_morph_catalog":     lambda p: cc5_api.get_morph_catalog(),
    "search_morphs":         lambda p: cc5_api.search_morphs(p["query"], p.get("category", "")),
    "get_morph_value":       lambda p: cc5_api.get_morph_value(p["morph_id"]),
    "set_morph_value":       lambda p: cc5_api.set_morph_value(p["morph_id"], p["value"]),
    "set_multiple_morphs":   lambda p: cc5_api.set_multiple_morphs(p["morphs"]),
    "create_default_avatar": lambda p: cc5_api.create_default_avatar(),
    "delete_avatar":         lambda p: cc5_api.delete_avatar(p.get("name", "")),
    "load_asset":            lambda p: cc5_api.load_asset(p["file_path"]),
    "export_fbx":            lambda p: cc5_api.export_fbx(
        p["output_path"],
        int(p.get("options", 0)),
        target_tool=p.get("target_tool", ""),
        sub_d_level=(int(p["sub_d_level"]) if p.get("sub_d_level") is not None else None),
        include_current_pose=bool(p.get("include_current_pose", False)),
        delete_hidden_faces=bool(p.get("delete_hidden_faces", False)),
        use_smooth_mesh=bool(p.get("use_smooth_mesh", False)),
        remove_eyelash=bool(p.get("remove_eyelash", False)),
        remove_tearline_occlusion=bool(p.get("remove_tearline_occlusion", False)),
        embed_textures=bool(p.get("embed_textures", False)),
        export_motion=bool(p.get("export_motion", True)),
        fps=(int(p["fps"]) if p.get("fps") is not None else None),
        motion_range=p.get("motion_range"),
        convert_image_format=bool(p.get("convert_image_format", False)),
        texture_size=(int(p["texture_size"]) if p.get("texture_size") is not None else None),
    ),
    "capture_viewport":      lambda p: cc5_api.capture_viewport(p.get("output_path", ""), int(p.get("width", 1280)), int(p.get("height", 720))),
    "set_subdivision_level": lambda p: cc5_api.set_subdivision_level(int(p["level"])),
    "undo":                  lambda p: cc5_api.undo(),
    "redo":                  lambda p: cc5_api.redo(),
    "get_camera_info":       lambda p: cc5_api.get_camera_info(),
    "set_camera_focal_length": lambda p: cc5_api.set_camera_focal_length(float(p["focal_length"])),
    "frame_camera":          lambda p: cc5_api.frame_camera(p.get("view", "face")),
    "get_lights":            lambda p: cc5_api.get_lights(),
    "set_light_color":       lambda p: cc5_api.set_light_color(p["light_name"], float(p["r"]), float(p["g"]), float(p["b"])),
    "get_light_info":        lambda p: cc5_api.get_light_info(p["light_name"]),
    "set_light_multiplier":  lambda p: cc5_api.set_light_multiplier(p["light_name"], float(p["multiplier"])),
    "set_light_active":      lambda p: cc5_api.set_light_active(p["light_name"], bool(p["active"])),
    "set_light_shadow":      lambda p: cc5_api.set_light_shadow(
        p["light_name"],
        (bool(p["cast_shadow"]) if p.get("cast_shadow") is not None else None),
        (float(p["darken_strength"]) if p.get("darken_strength") is not None else None),
    ),
    "get_visual_settings":   lambda p: cc5_api.get_visual_settings(),
    "set_ambient":           lambda p: cc5_api.set_ambient(float(p["r"]), float(p["g"]), float(p["b"])),
    "set_ibl":               lambda p: cc5_api.set_ibl(p.get("image_path", ""), bool(p.get("enable", True))),
    "get_expression_info":   lambda p: cc5_api.get_expression_info(),
    "set_expression":        lambda p: cc5_api.set_expression(p["expressions"]),
    "reset_expression":      lambda p: cc5_api.reset_expression(),
    "reset_all_morphs":      lambda p: cc5_api.reset_all_morphs(p.get("avatar_name", "")),
    "get_material_info":     lambda p: cc5_api.get_material_info(p.get("avatar_name", "")),
    "get_diffuse_color":     lambda p: cc5_api.get_diffuse_color(p["mesh_name"], p["material_name"]),
    "set_diffuse_color":     lambda p: cc5_api.set_diffuse_color(p["mesh_name"], p["material_name"], float(p["r"]), float(p["g"]), float(p["b"])),
    "get_material_properties": lambda p: cc5_api.get_material_properties(p["mesh_name"], p["material_name"]),
    "set_material_opacity":  lambda p: cc5_api.set_material_opacity(p["mesh_name"], p["material_name"], float(p["opacity"])),
    "set_material_glossiness": lambda p: cc5_api.set_material_glossiness(p["mesh_name"], p["material_name"], float(p["glossiness"])),
    "set_material_specular": lambda p: cc5_api.set_material_specular(p["mesh_name"], p["material_name"], float(p["specular"])),
    "get_shader_parameters": lambda p: cc5_api.get_shader_parameters(p["mesh_name"], p["material_name"]),
    "set_shader_parameter": lambda p: cc5_api.set_shader_parameter(p["mesh_name"], p["material_name"], p["parameter_name"], list(p["values"])),
    # Tier 1: Content Management
    "list_clothes":          lambda p: cc5_api.list_clothes(),
    "list_hair":             lambda p: cc5_api.list_hair(),
    "list_accessories":      lambda p: cc5_api.list_accessories(),
    "remove_scene_item":     lambda p: cc5_api.remove_scene_item(p["item_name"]),
    "browse_content":        lambda p: cc5_api.browse_content(p.get("folder_type", "cloth_upper")),
    # Tier 3: Convenience Color Shortcuts
    "set_eye_color":         lambda p: cc5_api.set_eye_color(float(p["r"]), float(p["g"]), float(p["b"])),
    "set_hair_color":        lambda p: cc5_api.set_hair_color(float(p["r"]), float(p["g"]), float(p["b"])),
    "set_lip_color":         lambda p: cc5_api.set_lip_color(float(p["r"]), float(p["g"]), float(p["b"])),
    "set_skin_color":        lambda p: cc5_api.set_skin_color(float(p["r"]), float(p["g"]), float(p["b"])),
    # Tier 4: Visibility & Scene
    "set_item_visible":      lambda p: cc5_api.set_item_visible(p["item_name"], bool(p["visible"])),
    "get_scene_objects":     lambda p: cc5_api.get_scene_objects(),
    "exec_python":           lambda p: cc5_api.exec_python(p["code"]),
    # Mesh-to-MetaHuman pipeline helpers
    "bake_skin_textures":    lambda p: cc5_api.bake_skin_textures(int(p.get("resolution", 4096))),
    "export_head_metahuman": lambda p: cc5_api.export_head_metahuman(
        p["output_dir"], p["character_name"], p.get("gender", "Female"),
    ),
    "silent_install_filter": lambda p: cc5_api.silent_install_filter(
        p["output_dir"], p["character_name"],
    ),
    "silent_trigger_dialog": lambda p: cc5_api.silent_trigger_dialog(),
    "silent_configure_and_click": lambda p: cc5_api.silent_configure_and_click(
        p.get("gender", "Female"), int(p.get("max_texture_size", 4096)),
    ),
    "silent_finalize": lambda p: cc5_api.silent_finalize(),
    "get_export_status": lambda p: cc5_api.get_export_status(),
    # ActorMIXER PRO: Create Mixer Assets
    "create_actor_mixer": lambda p: cc5_api.create_actor_mixer(p),
    "get_mixer_status":   lambda p: cc5_api.get_mixer_status(),
}

# POST path -> action name
POST_ROUTES: dict[str, str] = {
    '/morph-control/refresh': 'morph_refresh',
    '/fitting/morph-panel': 'fitting_morph_panel',
    '/fitting/load-side': 'fitting_load_side',
    '/fitting/configure': 'fitting_configure',
    '/morph-control/catalog': 'morph_catalog_live',
    '/morph-control/snapshot': 'morph_snapshot',
    '/morph-control/apply': 'morph_apply',
    '/morph-control/restore': 'morph_restore',
    '/fitting/sculpt-state': 'fitting_sculpt_state',
    '/fitting/sculpt-configure': 'fitting_sculpt_configure',
    '/fitting/open': 'fitting_open',
    '/fitting/state': 'fitting_state',
    '/fitting/move-point': 'fitting_move_point',
    '/fitting/action': 'fitting_action',
    '/fitting/close': 'fitting_close',
    '/fitting/landmarks': 'fitting_landmarks',
    '/headshot/open': 'headshot_open',
    '/headshot/configure': 'headshot_configure',
    '/headshot/generate': 'headshot_generate',
    "/morphs/search":    "search_morphs",
    "/morph/get":        "get_morph_value",
    "/morph/set":        "set_morph_value",
    "/morphs/set":       "set_multiple_morphs",
    "/morphs/reset":     "reset_all_morphs",
    "/avatar/create":    "create_default_avatar",
    "/avatar/delete":    "delete_avatar",
    "/asset/load":       "load_asset",
    "/export/fbx":       "export_fbx",
    "/viewport/capture": "capture_viewport",
    "/subdivision":      "set_subdivision_level",
    "/undo":             "undo",
    "/redo":             "redo",
    "/camera/focal":     "set_camera_focal_length",
    "/camera/frame":     "frame_camera",
    "/light/color":      "set_light_color",
    "/light/info":       "get_light_info",
    "/light/multiplier": "set_light_multiplier",
    "/light/active":     "set_light_active",
    "/light/shadow":     "set_light_shadow",
    "/visual/ambient":   "set_ambient",
    "/visual/ibl":       "set_ibl",
    "/expression/set":   "set_expression",
    "/expression/reset": "reset_expression",
    "/material/info":    "get_material_info",
    "/material/color/get": "get_diffuse_color",
    "/material/color/set": "set_diffuse_color",
    "/material/properties": "get_material_properties",
    "/material/opacity":    "set_material_opacity",
    "/material/glossiness": "set_material_glossiness",
    "/material/specular":   "set_material_specular",
    "/material/shader/get": "get_shader_parameters",
    "/material/shader/set": "set_shader_parameter",
    # Tier 1: Content Management
    "/item/remove":      "remove_scene_item",
    "/content/browse":   "browse_content",
    # Tier 3: Convenience Color Shortcuts
    "/color/eye":        "set_eye_color",
    "/color/hair":       "set_hair_color",
    "/color/lip":        "set_lip_color",
    "/color/skin":       "set_skin_color",
    # Tier 4: Visibility
    "/item/visible":     "set_item_visible",
    "/exec/python":      "exec_python",
    # Mesh-to-MetaHuman pipeline helpers
    "/skin/bake":        "bake_skin_textures",
    "/export/head_mh":   "export_head_metahuman",
    "/export/head_mh/silent/install_filter":  "silent_install_filter",
    "/export/head_mh/silent/trigger_dialog":  "silent_trigger_dialog",
    "/export/head_mh/silent/configure_click": "silent_configure_and_click",
    "/export/head_mh/silent/finalize":        "silent_finalize",
    # ActorMIXER PRO: Create Mixer Assets
    "/actor_mixer/create":                    "create_actor_mixer",
}

# GET path -> action name (None = handle inline)
GET_ROUTES: dict[str, str | None] = {
    '/headshot/catalog': 'headshot_catalog',
    '/headshot/state': 'headshot_state',
    "/health":         None,
    "/reload":         None,
    "/api":            None,
    "/avatars":        "get_avatars",
    "/avatar/info":    "get_avatar_info",
    "/morphs/catalog": "get_morph_catalog",
    "/camera/info":    "get_camera_info",
    "/lights":         "get_lights",
    "/visual/settings": "get_visual_settings",
    "/expressions":    "get_expression_info",
    "/material/info":  "get_material_info",
    # Tier 1: Content Management
    "/clothes":        "list_clothes",
    "/hair":           "list_hair",
    "/accessories":    "list_accessories",
    # Tier 4: Scene
    "/scene/objects":  "get_scene_objects",
    # Silent export polling
    "/export/head_mh/status": "get_export_status",
    # ActorMIXER PRO: Create Mixer Assets polling
    "/actor_mixer/status": "get_mixer_status",
}


# Explicit allowlist: unknown/new operations default to mutating.
READ_ACTIONS = {
    'morph_catalog_live', 'morph_snapshot', 'fitting_state', 'fitting_landmarks', 'fitting_sculpt_state',
    'headshot_catalog', 'headshot_state',
    "get_avatars", "get_avatar_info", "get_morph_catalog", "search_morphs",
    "get_morph_value", "get_camera_info", "get_lights", "get_visual_settings",
    "get_expression_info", "get_material_info", "list_clothes", "list_hair",
    "list_accessories", "get_scene_objects", "get_light_info", "get_diffuse_color",
    "get_material_properties", "get_shader_parameters", "browse_content",
    "get_export_status", "get_mixer_status",
}


def process_command_queue() -> None:
    """Execute at most one command per tick, with cancellation checked atomically."""
    global _processing
    if _processing:
        return
    operations.heartbeat = time.monotonic()
    controlled_headshot_modal = operations.modal_dialog_open and headshot.owns_modal()
    controlled_fitting_modal = operations.modal_dialog_open and fitting.owns_modal()
    if operations.modal_dialog_open and not (controlled_headshot_modal or controlled_fitting_modal):
        return
    _processing = True
    try:
        try:
            job = command_queue.get_nowait()
        except queue.Empty:
            return
        try:
            if ((controlled_headshot_modal and not job['action'].startswith('headshot_')) or
                (controlled_fitting_modal and not job['action'].startswith('fitting_'))):
                command_queue.put_nowait(job)
                return
            if not operations.start(job):
                return
            block = execution_block(job['action'])
            if block:
                operations.finish(job, {"success": False, "error": block})
                return
            handler = ACTION_MAP.get(job["action"])
            try:
                result = handler(job["params"]) if handler else {"success": False, "error": "Unknown action"}
            except Exception as error:
                result = {"success": False, "error": str(error)}
            operations.finish(job, result)
        finally:
            command_queue.task_done()
    finally:
        _processing = False
        operations.heartbeat = time.monotonic()


def _validate_params(action: str, params: dict) -> str | None:
    """Validate required parameters. Returns error message or None."""
    required = REQUIRED_PARAMS.get(action)
    if not required:
        return None
    missing = [f for f in required if f not in params]
    if missing:
        return f"Missing required field(s): {', '.join(missing)}"
    return None


def _execute_sync(action, params, timeout=30.0, operation_id=None):
    error = _validate_params(action, params)
    if error:
        return 400, {"error": error}
    block = execution_block(action)
    if block:
        return 403, {"error": block}
    if action not in READ_ACTIONS and operations.status()['active_operations']:
        return 409, {"error": "Another operation is running or has unknown outcome; inspect status first"}
    if operation_id and not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", operation_id):
        return 400, {"error": "Invalid operation ID"}
    try:
        job, fresh = operations.submit(action, params, operation_id)
    except ValueError as error:
        return 409, {"error": str(error)}
    except RuntimeError as error:
        return 503, {"error": str(error)}
    if fresh:
        try:
            command_queue.put_nowait(job)
        except queue.Full:
            operations.expire(job)
            return 503, {"error": "Command queue full", "operation": operations.snapshot(job['id'])}
    if not job['event'].wait(timeout):
        state = operations.expire(job)
        if state['state'] not in ('completed', 'failed'):
            return 504, {"error": "Operation timed out; inspect status, do not retry with a new ID", "operation": state}
    state = operations.snapshot(job['id'])
    if state['state'] == 'cancelled':
        return 409, {"error": "Operation cancelled before execution", "operation": state}
    if state['state'] == 'failed':
        return 400, {"error": state['result'].get('error', 'Operation failed'), "operation": state}
    return 200, {"result": state['result'], "operation": state}


def reload_modules() -> dict[str, Any]:
    """Hot-reload cc5_api so code changes take effect without server restart."""
    global cc5_api
    try:
        importlib.reload(cc5_api)
        cc5_api = sys.modules["cc5_api"]
        return {"success": True, "message": "cc5_api reloaded"}
    except Exception as e:
        print(f"[CC5 MCP Bridge] Reload failed: {traceback.format_exc()}")
        return {"success": False, "error": str(e)}


def _api_info() -> dict[str, Any]:
    """Return API discovery information."""
    return {
        "service": "cc5-mcp-bridge",
        "version": API_VERSION,
        "endpoints": {
            "GET": {p: a or "inline" for p, a in GET_ROUTES.items()},
            "POST": dict(POST_ROUTES),
        },
        "required_params": REQUIRED_PARAMS,
    }


class BridgeHandler(BaseHTTPRequestHandler):
    """HTTP request handler for the CC5 bridge API."""

    def log_message(self, format: str, *args: Any) -> None:
        # Log non-2xx responses for debugging
        if args and not str(args[0]).startswith("2"):
            print(f"[CC5 MCP Bridge] {format % args}")

    def _send_json(self, status: int, data: Any) -> None:
        body = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self) -> dict:
        raw_length = self.headers.get("Content-Length", "0")
        try:
            length = int(raw_length)
        except ValueError:
            raise ValueError(f"Invalid Content-Length: {raw_length!r}")
        if length <= 0:
            return {}
        if length > MAX_REQUEST_BYTES:
            raise ValueError(f"Request body too large: {length} bytes (max {MAX_REQUEST_BYTES})")
        try:
            data = self.rfile.read(min(length, MAX_REQUEST_BYTES))
            parsed = json.loads(data)
        except (json.JSONDecodeError, ValueError) as e:
            raise ValueError(f"Invalid JSON in request body: {e}") from e
        if not isinstance(parsed, dict):
            raise ValueError("Request body must be a JSON object")
        return parsed

    def _authorized(self):
        token = self.headers.get("Authorization", "")
        if not BRIDGE_TOKEN or not hmac.compare_digest(token, "Bearer " + BRIDGE_TOKEN):
            self._send_json(401, {"error": "Bridge token required"})
            return False
        if self.headers.get("Origin"):
            self._send_json(403, {"error": "Browser-origin requests are not supported"})
            return False
        return True

    def do_GET(self) -> None:
        if not self._authorized():
            return
        path = urlparse(self.path).path

        if path == "/health":
            self._send_json(200, {"result": dict(operations.status(), service="cc5-mcp-bridge",
                version=API_VERSION, paused=paused(), read_only=READ_ONLY)})
            return

        if path == "/capabilities":
            self._send_json(200, {"result": get_capabilities()})
            return

        if path.startswith("/operations/"):
            state = operations.snapshot(path.rsplit("/", 1)[-1])
            self._send_json(200 if state else 404, {"result": state} if state else {"error": "Unknown operation in this session"})
            return

        if path == "/api":
            if DEV_MODE:
                self._send_json(200, {"result": _api_info()})
            else:
                self._send_json(200, {"result": {"service": "cc5-mcp-bridge", "version": API_VERSION}})
            return

        if path == "/reload":
            self._send_json(403, {"error": "Runtime reload disabled; restart plugin after reviewing changes"})
            return

        action = GET_ROUTES.get(path)
        if action:
            status, data = _execute_sync(action, {}, operation_id=self.headers.get("X-Operation-ID"))
            self._send_json(status, data)
        else:
            self._send_json(404, {"error": f"Not found: {path}"})

    def do_POST(self) -> None:
        if not self._authorized():
            return
        path = urlparse(self.path).path

        try:
            params = self._read_json()
        except ValueError as e:
            self._send_json(400, {"error": str(e)})
            return

        action = POST_ROUTES.get(path)
        if action:
            if action == "exec_python" and os.environ.get("CC5_ALLOW_EXEC", "").strip().lower() not in ("1", "true", "yes"):
                self._send_json(403, {"error": "/exec/python disabled. Explicit CC5_ALLOW_EXEC=1 is required."})
                return
            status, data = _execute_sync(action, params, operation_id=self.headers.get("X-Operation-ID"))
            self._send_json(status, data)
        else:
            self._send_json(404, {"error": f"Not found: {path}"})


class ReusableHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def start_server(port: int = 5101) -> threading.Thread:
    """Start the HTTP bridge server in a background daemon thread."""
    global _httpd
    if len(BRIDGE_TOKEN) < 32:
        raise RuntimeError("Set CC5_BRIDGE_TOKEN to a random token of at least 32 characters")
    httpd = ReusableHTTPServer(("127.0.0.1", port), BridgeHandler)
    _httpd = httpd

    def run() -> None:
        httpd.serve_forever()

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    return thread


def stop_server() -> None:
    """Shut down the HTTP server gracefully."""
    global _httpd
    if _httpd is not None:
        _httpd.shutdown()
        _httpd.server_close()
        _httpd = None
    with operations.lock:
        for job in operations.jobs.values():
            if job['state'] in ('queued', 'running'):
                operations.expire(job)
