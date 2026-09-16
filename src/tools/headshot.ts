import { z } from "zod";
import type { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import type { CC5Bridge } from "../cc5-bridge.js";

export const headshotSettings = {
  front: z.string().min(1).describe("Absolute local front reference image path"),
  side: z.string().min(1).optional().describe("Absolute local side profile image path"),
  body_image: z.string().min(1).optional(),
  generate_hair: z.boolean(),
  face: z.object(Object.fromEntries(["face", "forehead", "cheeks", "chin", "eyes", "nose", "ears"].map(
    tab => [tab, z.array(z.string()).optional()]))).strict().optional()
    .describe("Preset IDs from get_headshot_options, grouped by all seven tabs. Exclusive choices are validated."),
  body: z.object({
    mode: z.enum(["type", "photo"]),
    type: z.enum(["current", "neutral", "male", "female", "child", "baby"]).optional(),
    age: z.enum(["adult", "elder", "teen"]).optional(),
    shape: z.enum(["normal", "skinny", "heavy", "strong"]).optional(),
    photo_shape: z.enum(["average", "heavy", "slim"]).optional(),
    photo_gender: z.enum(["male", "female"]).optional(),
    photo_physique: z.enum(["normal", "muscular"]).optional(),
  }).strict(),
};

export function registerHeadshotTools(server: McpServer, bridge: CC5Bridge) {
  const call = async (action: "catalog" | "state" | "open" | "configure" | "generate", args = {}) => {
    try {
      const result = await bridge.headshot(action, args);
      return { content: [{ type: "text" as const, text: JSON.stringify(result, null, 2) }], isError: result.success === false };
    } catch (error) {
      return { content: [{ type: "text" as const, text: String(error) }], isError: true };
    }
  };
  server.tool("get_headshot_options", "Read every preset in the seven Headshot 3 face tabs and the body controls from the installed dialog resource.", {}, () => call("catalog"));
  server.tool("get_headshot_settings", "Read back Headshot dialog selections, enabled controls and prepared ID.", {}, () => call("state"));
  server.tool("open_headshot", "Open Headshot Generate Character using an existing front image. Requires the Headshot IMAGE panel. Does not generate diffusion images or a character.", {front:z.string().min(1)}, args => call("open", args));
  server.tool("configure_headshot", "Load existing front/side/body references and configure Generate Hair, seven face tabs, and body options. Returns readback plus prepared_id. Does not generate yet.", headshotSettings, args => call("configure", args));
  server.tool("generate_headshot", "Generate using a previously prepared Headshot 3 dialog. Long native operation: inspect operation status after a timeout; never blindly retry. Success still needs visual and save/reopen verification.", {prepared_id:z.string().min(1)}, args => call("generate", args));
}
