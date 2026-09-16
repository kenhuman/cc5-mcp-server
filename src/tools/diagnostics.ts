import { z } from "zod";
import type { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import type { CC5Bridge } from "../cc5-bridge.js";

export function registerDiagnosticsTools(server: McpServer, bridge: CC5Bridge) {
  const report = async (fn: () => Promise<unknown>) => {
    try {
      return { content: [{ type: "text" as const, text: JSON.stringify(await fn(), null, 2) }] };
    } catch (error) {
      return { isError: true, content: [{ type: "text" as const, text: String(error) }] };
    }
  };
  server.tool("get_bridge_status", "Inspect main-thread heartbeat, session, active jobs and pause/read-only state. Does not call CC5.", {},
    () => report(() => bridge.getBridgeStatus()));
  server.tool("get_operation_status", "Inspect an operation ID from a timeout/error. Never repeat a mutation with unknown outcome. IDs are session-local; a missing ID after restart does not mean the work never ran.",
    { operation_id: z.string().regex(/^[A-Za-z0-9_-]{1,128}$/) },
    ({ operation_id }) => report(() => bridge.getOperationStatus(operation_id)));
  server.tool("get_cc5_capabilities", "Inspect already-loaded API symbols and unresolved workflow limitations without invoking native generation.", {},
    () => report(() => bridge.getCapabilities()));
  server.tool("get_character_morph_recipe", "Return a partial character recipe containing the current avatar and active morphs. This does not capture textures, hair assets, height or a restorable project.", {},
    () => report(async () => ({ schema_version: 1, complete: false, avatar: await bridge.getAvatarInfo(),
      missing: ["reference_images", "materials", "hair_assets", "measured_height", "project_checkpoint"] })));
}
