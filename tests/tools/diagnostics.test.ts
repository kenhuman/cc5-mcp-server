import { describe, it, expect, vi } from "vitest";
import { registerDiagnosticsTools } from "../../src/tools/diagnostics.js";
import { createMockServer } from "../helpers/mock-server.js";
import type { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import type { CC5Bridge } from "../../src/cc5-bridge.js";

describe("diagnostic tools", () => {
  it("reports unknown outcome without retrying", async () => {
    const server = createMockServer();
    const bridge = { getOperationStatus: vi.fn().mockResolvedValue({ state: "outcome_unknown" }) };
    registerDiagnosticsTools(server as unknown as McpServer, bridge as unknown as CC5Bridge);
    const result = await server.getRegisteredTool("get_operation_status")({ operation_id: "test" });
    expect(result.content[0].text).toContain("outcome_unknown");
    expect(bridge.getOperationStatus).toHaveBeenCalledTimes(1);
  });
  it("labels morph recipe incomplete", async () => {
    const server = createMockServer();
    const bridge = { getAvatarInfo: vi.fn().mockResolvedValue({ name: "Lemuria", active_morphs: {} }) };
    registerDiagnosticsTools(server as unknown as McpServer, bridge as unknown as CC5Bridge);
    const result = await server.getRegisteredTool("get_character_morph_recipe")({});
    const recipe = JSON.parse(result.content[0].text);
    expect(recipe.complete).toBe(false);
    expect(recipe.missing).toContain("measured_height");
  });
});
