// Explicit test on an already-open disposable Headshot character; applies a small front edit.
import {Client} from '@modelcontextprotocol/sdk/client/index.js';
import {StdioClientTransport} from '@modelcontextprotocol/sdk/client/stdio.js';
import fs from 'node:fs/promises';
import {lab, token, bridgeUrl, frontReference} from './smoke_config.mjs';
const client=new Client({name:'refinement-smoke',version:'1'});
const transport=new StdioClientTransport({command:process.execPath,args:['build/index.js'],
  env:{...process.env,CC5_BRIDGE_URL:bridgeUrl,CC5_BRIDGE_TOKEN:token},stderr:'pipe'});
const report={};
const delay=ms=>new Promise(r=>setTimeout(r,ms));
async function call(name,args={}) {
  const r=await client.callTool({name,arguments:args});
  if(!r.isError)return JSON.parse(r.content[0].text);
  const message=r.content[0].text;
  const id=message.match(/operation_id=([a-zA-Z0-9_-]+)/)?.[1];
  if(id){
    for(let i=0;i<120;i++){
      const s=await client.callTool({name:'get_operation_status',arguments:{operation_id:id}});
      if(s.isError)throw new Error(message);
      const op=JSON.parse(s.content[0].text);
      if(op.state==='completed'&&op.result?.success!==false)return op.result;
      if(!['running','outcome_unknown'].includes(op.state))break;
      await delay(1000);
    }
  }
  throw new Error(message);
}
async function stable(){
  let prev;
  for(let i=0;i<30;i++){
    const s=await call('get_face_refinement');
    if(s.open&&s.revision===prev)return s;
    prev=s.revision;await delay(500);
  }
  throw new Error('Refinement did not settle');
}
try {
  await client.connect(transport);
  await call('open_face_refinement',{view:'front'});
  const state=await stable();
  const point=state.views.BezierView.items.find(p=>p.movable&&p.x<400);
  if(!point)throw new Error('Visible test point missing');
  report.move=await call('move_face_refinement_point',{revision:state.revision,point_id:point.point_id,x:point.x+12,y:point.y+12});
  await call('face_refinement_action',{revision:(await stable()).revision,action:'preview_all'});
  report.apply=await call('face_refinement_action',{revision:(await stable()).revision,action:'apply_all'});
  report.success=true;
  await call('close_face_refinement');
}catch(error){report.error=String(error);process.exitCode=1;}
finally{
  await fs.writeFile(`${lab}/refinement-mcp-smoke.json`,JSON.stringify(report,null,2));
  console.log(JSON.stringify({success:report.success,error:report.error,point:report.move?.actual,applied:report.apply?.state}));
  await client.close();
}
