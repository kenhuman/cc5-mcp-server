import { Client } from '@modelcontextprotocol/sdk/client/index.js';
import { StdioClientTransport } from '@modelcontextprotocol/sdk/client/stdio.js';
import fs from 'node:fs/promises';
import {lab, token, bridgeUrl, frontReference} from './smoke_config.mjs';
const client=new Client({name:'headshot-smoke',version:'1'});
const transport=new StdioClientTransport({command:process.execPath,args:['build/index.js'],
  env:{...process.env,CC5_BRIDGE_URL:bridgeUrl,CC5_BRIDGE_TOKEN:token},stderr:'pipe'});
if (!frontReference) throw new Error('Set CC5_FRONT_REFERENCE to an existing front image');
const report={};
async function call(name,args={}){
  const result=await client.callTool({name,arguments:args});
  if(result.isError)throw new Error(JSON.stringify(result));
  return JSON.parse(result.content[0].text);
}
try {
  await client.connect(transport);
  report.tools=(await client.listTools()).tools.filter(t=>t.name.includes('headshot')).map(t=>t.name);
  report.catalog=await call('get_headshot_options');
  await call('open_headshot',{front:frontReference});
  for(let n=0;n<30;n++){
    const s=await call('get_headshot_settings');if(s.open)break;
    await new Promise(r=>setTimeout(r,300));
  }
  report.configured=await call('configure_headshot',{
    front:frontReference,
    generate_hair:false, face:{face:[],forehead:[],cheeks:[],chin:[],eyes:[],nose:[],ears:[]},
    body:{mode:'type',type:'female',age:'adult',shape:'strong'}});
  report.readback=await call('get_headshot_settings');
  if(!report.readback.body.age.includes('adult') || !report.readback.body.shape.includes('strong') || report.readback.generate_hair!==false)throw new Error('Readback mismatch');
  report.success=true;
  console.log(JSON.stringify({success:true,tools:report.tools,tabs:Object.keys(report.catalog.tabs),preset_count:Object.values(report.catalog.tabs).reduce((n,x)=>n+x.length,0)}));
} catch(e){report.error=String(e);console.error(String(e));process.exitCode=1;}
finally{await fs.writeFile(`${lab}/mcp-headshot-smoke.json`,JSON.stringify(report,null,2));await client.close();}
