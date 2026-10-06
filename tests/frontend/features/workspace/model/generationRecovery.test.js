import {expect,it} from 'vitest';
import {createWorkspaceApi} from '@workspace/workspace/model/workspaceApi';

it('restores completed steps and parallel AI work from durable history',()=>{
 const api=createWorkspaceApi({});
 const snapshot=api.toProgressSnapshot({status:'running',stage:'finalize_ai_summary',progress:98,events:[
  {status:'running',stage:'summarize'},
  {status:'running',stage:'generate_ai_summary'},
  {status:'running',stage:'extract_screenshots'},
  {status:'running',stage:'finalize_ai_summary'},
 ]});
 expect(snapshot.steps.find(step=>step.id==='summarize').status).toBe('completed');
 expect(snapshot.steps.find(step=>step.id==='ai_summary').status).toBe('running');
 expect(snapshot.progress).toBe(98);
});
