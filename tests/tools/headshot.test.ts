import { describe, it, expect, vi } from "vitest";
import { registerHeadshotTools, headshotSettings } from "../../src/tools/headshot.js";
import { createMockServer } from "../helpers/mock-server.js";
import type { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import type { CC5Bridge } from "../../src/cc5-bridge.js";
import { z } from "zod";

describe("Headshot controls", () => {
  it("preserves side reference, false hair flag, all seven tabs and photo body options", async () => {
    const settings = { front: "G:/front.png", side: "G:/side.png", body_image: "G:/body.png", generate_hair: false,
      face: Object.fromEntries(["face","forehead","cheeks","chin","eyes","nose","ears"].map(x=>[x,[]])),
      body: { mode: "photo", photo_shape: "slim", photo_gender: "female", photo_physique: "normal" } };
    const parsed = z.object(headshotSettings).parse(settings);
    expect(parsed).toEqual(settings);
    const server=createMockServer(); const bridge={headshot:vi.fn().mockResolvedValue({prepared_id:"p"})};
    registerHeadshotTools(server as unknown as McpServer,bridge as unknown as CC5Bridge);
    await server.getRegisteredTool("configure_headshot")(parsed);
    expect(bridge.headshot).toHaveBeenCalledWith("configure",settings);
  });
  it("does not retry unknown native outcomes and reports an MCP error", async () => {
    const server=createMockServer();const bridge={headshot:vi.fn().mockRejectedValue(new Error("outcome_unknown operation_id=abc"))};
    registerHeadshotTools(server as unknown as McpServer,bridge as unknown as CC5Bridge);
    const response=await server.getRegisteredTool("generate_headshot")({prepared_id:"p"});
    expect(response.isError).toBe(true);expect(bridge.headshot).toHaveBeenCalledTimes(1);
    expect(response.content[0].text).toContain("operation_id=abc");
  });
  it("rejects misspelled body settings",()=>{
    expect(()=>z.object(headshotSettings).parse({front:"G:/front.png",generate_hair:false,body:{mode:"type",age:"young"}})).toThrow();
  });
});
