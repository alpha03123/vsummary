import {act, renderHook} from '@testing-library/react';
import {beforeEach, describe, expect, it, vi} from 'vitest';
import {useWorkspaceController} from '@workspace/workspace/model/useWorkspaceController';
import {PLAYGROUND_SERIES_ID} from '@workspace/workspace/model/workspaceControllerConstants';

const runtime=vi.hoisted(()=>({current:null}));
vi.mock('@workspace/runtime/WorkspaceProvider',()=>({useWorkspaceRuntime:()=>runtime.current}));

beforeEach(()=>{
 window.localStorage.clear();
 runtime.current={
  host:{storage:window.localStorage},
  api:{getVideoPreviewUrl:vi.fn()},
  useDataEffects:()=>{},
  createContentActions:()=>({}),
 };
});

describe('workspace host action contract',()=>{
 it('lets a host intercept Playground selection without entering it',()=>{
  const requestLogin=vi.fn();
  runtime.current.host.createActions=()=>({onSelectSeries:requestLogin});
  const {result}=renderHook(()=>useWorkspaceController());
  act(()=>result.current.onSelectSeries(PLAYGROUND_SERIES_ID));
  expect(requestLogin).toHaveBeenCalledWith(PLAYGROUND_SERIES_ID);
  expect(result.current.state.selectedSeriesId).not.toBe(PLAYGROUND_SERIES_ID);
 });

 it('passes default actions separately so an override can delegate without recursion',()=>{
  const beforeSelect=vi.fn();
  runtime.current.host.createActions=({actions})=>({onSelectSeries(id){beforeSelect(id);actions.onSelectSeries(id);}});
  const {result}=renderHook(()=>useWorkspaceController());
  act(()=>result.current.onSelectSeries(PLAYGROUND_SERIES_ID));
  expect(beforeSelect).toHaveBeenCalledTimes(1);
  expect(result.current.state.selectedSeriesId).toBe(PLAYGROUND_SERIES_ID);
  expect(result.current.state.selectedContextType).toBe('playground');
 });
});
