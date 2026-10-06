import {fireEvent, render, screen} from '@testing-library/react';
import {describe, expect, it, vi} from 'vitest';
import {WorkspaceUsageAnalytics, WorkspaceUsagePage} from '@workspace/workspace/ui/WorkspaceUsagePage';

describe('composable usage views',()=>{
 it('keeps host check-in actions and analytics range controls usable in the same page',async()=>{
  const checkIn=vi.fn(),changeRange=vi.fn();
  render(<WorkspaceUsagePage onClose={vi.fn()}>
   <button onClick={checkIn}>签到</button>
   <WorkspaceUsageAnalytics usage={{total:{promptTokens:10,completionTokens:20,totalTokens:30}}} range="7d" onChangeRange={changeRange}/>
  </WorkspaceUsagePage>);
  fireEvent.click(screen.getByRole('button',{name:'签到',exact:true}));
  expect(checkIn).toHaveBeenCalledTimes(1);
  fireEvent.click(await screen.findByRole('button',{name:'30 天',exact:true}));
  expect(changeRange).toHaveBeenCalledWith('30d');
  expect(screen.getByRole('button',{name:'签到',exact:true})).toBeEnabled();
 });
});
