import {useEffect,useRef} from 'react';
import {WorkspaceProvider,useWorkspaceRuntime} from './WorkspaceProvider';
import {useWorkspaceController} from '../workspace/model/useWorkspaceController';
import {WorkspacePage} from '../workspace/ui/WorkspacePage';
import {buildWorkspacePageModel} from '../workspace/ui/workspacePageModel';

export function WorkspaceApplication() {
  const {host}=useWorkspaceRuntime();
  const controller=useWorkspaceController();
  const page=buildWorkspacePageModel(controller);
  const deepLinkHandled=useRef(false);
  useEffect(()=>{
    if(deepLinkHandled.current || !controller.state.library) return;
    const parameters=new URLSearchParams(window.location.search);
    const seriesId=parameters.get('series'),videoId=parameters.get('video');
    deepLinkHandled.current=true;
    const series=controller.state.library.series.find(item=>item.id===seriesId);
    if(series?.videos.some(video=>video.id===videoId))controller.onSelectVideo(seriesId,videoId);
  },[controller.state.library,controller.onSelectVideo]);
  const Effects=host.Effects;
  return <>
    {Effects && <Effects state={controller.state} dispatch={controller.dispatch}/>}
    <WorkspacePage page={page} panels={host.panels} toolbarExtras={host.renderToolbar?.(controller,page)} sidebarFooter={host.renderSidebarFooter?.(controller,page)}/>
  </>;
}

export function WorkspaceApp({host}) {
  return <WorkspaceProvider host={host}><WorkspaceApplication/></WorkspaceProvider>;
}
