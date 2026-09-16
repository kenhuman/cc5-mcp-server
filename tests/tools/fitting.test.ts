import {describe,it,expect,vi} from 'vitest';
import {registerFittingTools} from '../../src/tools/fitting.js';
import {createMockServer} from '../helpers/mock-server.js';
describe('deterministic fitting tools',()=>{
  it('forwards exact weights and expected state without guessing or retrying',async()=>{
    const s=createMockServer();const bridge={fittingControl:vi.fn().mockResolvedValue({success:true,changes:[{actual:0.05}]})};
    registerFittingTools(s as any,bridge as any);
    const args={avatar_id:'7',morphs:[{morph_id:'chin',value:0.05,expected_value:0}]};
    const result=await s.getRegisteredTool('set_anatomy_morphs')(args);
    expect(bridge.fittingControl).toHaveBeenCalledWith('morph-control','apply',args);
    expect(JSON.parse(result.content[0].text).changes[0].actual).toBe(0.05);
  });
  it('keeps native failure machine-readable',async()=>{
    const s=createMockServer();const bridge={fittingControl:vi.fn().mockResolvedValue({success:false,rollback_complete:false})};
    registerFittingTools(s as any,bridge as any);
    const result=await s.getRegisteredTool('restore_anatomy_morphs')({snapshot:{}});
    expect(result.isError).toBe(true);expect(bridge.fittingControl).toHaveBeenCalledTimes(1);
  });
  it('forwards revision and exact point target',async()=>{
    const s=createMockServer();const bridge={fittingControl:vi.fn().mockResolvedValue({success:true})};
    registerFittingTools(s as any,bridge as any);
    const args={revision:'fresh',point_id:'p',x:10.5,y:27};
    await s.getRegisteredTool('move_face_refinement_point')(args);
    expect(bridge.fittingControl).toHaveBeenCalledWith('fitting','move-point',args);
  });
});
