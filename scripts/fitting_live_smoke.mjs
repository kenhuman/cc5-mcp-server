// Explicit isolated-lab test. Restores modified morphs and sculpt settings.
import {Client} from '@modelcontextprotocol/sdk/client/index.js';
import {StdioClientTransport} from '@modelcontextprotocol/sdk/client/stdio.js';
import fs from 'node:fs/promises';
import {lab, token, bridgeUrl, frontReference} from './smoke_config.mjs';
const client=new Client({name:'fitting-smoke',version:'1'});
const transport=new StdioClientTransport({command:process.execPath,args:['build/index.js'],
  env:{...process.env,CC5_BRIDGE_URL:bridgeUrl,CC5_BRIDGE_TOKEN:token},stderr:'pipe'});
const report={};let saved,sculpt;
async function call(name,args={}){
  const r=await client.callTool({name,arguments:args});
  if(r.isError)throw new Error(JSON.stringify(r));
  return JSON.parse(r.content[0].text);
}
try {
  await client.connect(transport);
  report.refresh=await call('refresh_anatomy_morphs');
  report.panel=await call('show_headshot_morphs');
  report.catalog=await call('get_anatomy_morphs',{query:'Chin Depth',category:'Actor/Headshot'});
  if(!report.catalog.morphs.length) {
    report.catalog_fallback='Reopened character exposes only accessory shaping categories; testing an available native slider';
    report.catalog=await call('get_anatomy_morphs');
  }
  const morph=report.catalog.morphs.find(m=>m.display_name==='Chin Depth')??report.catalog.morphs[0];
  if(!morph)throw new Error('Test morph missing');
  const avatar_id=report.catalog.avatar_id;
  saved=(await call('snapshot_anatomy_morphs',{avatar_id,morph_ids:[morph.morph_id]})).snapshot;
  report.changed=await call('set_anatomy_morphs',{avatar_id,morphs:[{morph_id:morph.morph_id,value:0.05,expected_value:morph.value}]});
  if(Math.abs(report.changed.changes[0].actual-0.05)>1e-6)throw new Error('Wrong native readback');
  report.restored=await call('restore_anatomy_morphs',{snapshot:saved});saved=null;
  const invalid=await client.callTool({name:'set_anatomy_morphs',arguments:{avatar_id,morphs:[{morph_id:morph.morph_id,value:morph.minimum-0.1}]}});
  if(!invalid.isError)throw new Error('Native range failure not propagated');
  report.invalid_rejected=true;
  sculpt=await call('get_sculpt_settings');
  report.sculpt=await call('configure_sculpt',{settings:{enabled:true,view:'side',region:'nose',symmetrical:true,show_area:true,opacity:30,zoom_to_area:false}});
  if(!report.sculpt.selected.some(s=>s.view==='side'&&s.region==='nose')||report.sculpt.opacity!==30)throw new Error('Sculpt readback mismatch');
  report.landmarks=await call('get_headshot_landmarks',{view:'front'});
  report.success=true;
} catch(error){report.error=String(error);process.exitCode=1;}
finally {
  try {
    if(saved)report.restore_after_error=await call('restore_anatomy_morphs',{snapshot:saved});
    if(sculpt){
      await call('configure_sculpt',{settings:{...sculpt.settings,enabled:true,...sculpt.selected[0],opacity:sculpt.opacity}});
      await call('configure_sculpt',{settings:{enabled:sculpt.settings.enabled}});
      report.sculpt_restored=await call('get_sculpt_settings');
    }
  }catch(error){report.cleanup_error=String(error);report.success=false;process.exitCode=1;}
  await fs.writeFile(`${lab}/fitting-mcp-smoke.json`,JSON.stringify(report,null,2));
  console.log(JSON.stringify({success:report.success,error:report.error,cleanup_error:report.cleanup_error,
    morphs:report.catalog?.morphs.length,changed:report.changed?.changes,sculpt:report.sculpt,landmark_count:report.landmarks?.points.length}));
  await client.close();
}
