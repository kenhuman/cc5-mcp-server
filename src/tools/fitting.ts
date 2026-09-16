import { z } from "zod";
import type { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import type { CC5Bridge } from "../cc5-bridge.js";

const avatar_id = z.string().optional().describe("Exact avatar ID; required when multiple avatars exist");
const view = z.enum(["front", "side"]);
const revision = z.string().min(1).describe("Revision returned by a fresh get_face_refinement call");
const weight = z.number().finite();
const morph = z.object({morph_id:z.string().min(1),value:weight,expected_value:weight.optional()}).strict();
const snapshot = z.object({version:z.literal(1),avatar_id:z.string(),avatar_name:z.string().optional(),
  morphs:z.array(z.object({morph_id:z.string(),value:weight}).strict()).min(1).max(10000)}).strict();

export function registerFittingTools(server:McpServer, bridge:CC5Bridge) {
  const call = async (group:"morph-control"|"fitting", action:string, args:Record<string,unknown>={}) => {
    try {
      const result=await bridge.fittingControl(group,action,args);
      return {content:[{type:"text" as const,text:JSON.stringify(result,null,2)}],isError:result.success===false};
    } catch(error) {
      return {content:[{type:"text" as const,text:String(error)}],isError:true};
    }
  };
  server.tool("refresh_anatomy_morphs","Run CC5 Refresh Sliders after loading a project to populate the installed morph catalog. Does not reset weights.",{},()=>call("morph-control","refresh"));
  server.tool("show_headshot_morphs","Open the Headshot morph panel.",{},()=>call("fitting","morph-panel"));
  server.tool("get_anatomy_morphs","Read live anatomy morph IDs, native limits, categories and actual values. No cached assumptions.",
    {avatar_id,query:z.string().optional(),category:z.string().optional()},args=>call("morph-control","catalog",args));
  server.tool("snapshot_anatomy_morphs","Snapshot exact morph values for later restoration; defaults to all available sliders including zero values.",
    {avatar_id,morph_ids:z.array(z.string()).min(1).max(10000).optional()},args=>call("morph-control","snapshot",args));
  server.tool("set_anatomy_morphs","Set absolute native morph weights, validate limits, check expected values and readback. Attempts rollback on failure; inspect rollback_complete. Does not choose adjustments.",
    {avatar_id,morphs:z.array(morph).min(1).max(10000)},args=>call("morph-control","apply",args));
  server.tool("restore_anatomy_morphs","Restore a snapshot on the same live avatar ID. Not a project/mesh/texture restore.",
    {snapshot},args=>call("morph-control","restore",args));
  server.tool("get_sculpt_settings","Read Headshot sculpt mode, region, symmetry and overlay settings.",{},()=>call("fitting","sculpt-state"));
  server.tool("configure_sculpt","Set Headshot sculpt mode and region. Numeric anatomy morph tools perform reproducible shape changes.",
    {settings:z.object({enabled:z.boolean().optional(),view:view.optional(),region:z.enum(["contour","face","eyes","nose","mouth","ears"]).optional(),
      symmetrical:z.boolean().optional(),show_area:z.boolean().optional(),dark_mode:z.boolean().optional(),zoom_to_area:z.boolean().optional(),
      opacity:z.number().int().min(0).max(100).optional()}).strict()},args=>call("fitting","sculpt-configure",args));
  server.tool("open_face_refinement","Open Headshot Refine Face front or side. Read state after opening.",{view},args=>call("fitting","open",args));
  server.tool("get_face_refinement","Read current refinement stage, visible scene controls and their coordinates. Point IDs are session-local; refresh after every action.",{},()=>call("fitting","state"));
  server.tool("move_face_refinement_point","Move a visible refinement control to scene coordinates via native mouse events; returns actual position with viewport-pixel tolerance. Does not apply to the character until Apply.",
    {revision,point_id:z.string(),x:z.number().finite(),y:z.number().finite()},args=>call("fitting","move-point",args));
  server.tool("face_refinement_action","Run an explicit native preview/apply/reset/finish action if available in the current refinement stage. Apply may be a long native operation; do not retry an unknown outcome.",
    {revision,action:z.enum(["preview_all","preview_parts","apply_all","apply_parts","edit","reset_view","reset_points","align","adjust_alignment","finish_alignment"])},args=>call("fitting","action",args));
  server.tool("load_refinement_side_reference","Load an existing local side image into an open side refinement panel through its native file picker.",
    {path:z.string().min(1)},args=>call("fitting","load-side",args));
  server.tool("configure_face_refinement","Set native alignment/overlay numbers using IDs and limits from get_face_refinement, or select face parts and mirror mode.",
    {revision,numbers:z.record(z.string(),z.number().finite()).optional(),toggles:z.object({mirror:z.boolean().optional(),skull:z.boolean().optional(),eyes:z.boolean().optional(),nose:z.boolean().optional(),lips:z.boolean().optional()}).strict().optional()},args=>call("fitting","configure",args));
  server.tool("close_face_refinement","Close refinement without pressing Apply; does not undo previously applied refinement.",{},()=>call("fitting","close"));
  server.tool("get_headshot_landmarks","Read native front/side landmark arrays. Coordinates and indexing belong to Headshot, not a generic detector.",{view},args=>call("fitting","landmarks",args));
}
