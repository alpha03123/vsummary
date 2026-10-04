import {useState} from 'react';
import {WorkspaceProvider,WorkspaceApplication} from '@alpha03123/vsummary-workspace-ui';
import {createLocalHost} from './local-features/workspace/localHost';
import {WorkspaceVideoScopeEmbed} from './local-features/workspace/ui/WorkspaceVideoScopeEmbed';
import {MotionShowcase} from './dev/MotionShowcase';
export function App(){
 const [host]=useState(createLocalHost);
 const embedded=new URLSearchParams(window.location.search).get('embed')==='video-scope';
 return <WorkspaceProvider host={host}>{window.location.hash==='#test'?<MotionShowcase/>:embedded?<WorkspaceVideoScopeEmbed/>:<WorkspaceApplication/>}</WorkspaceProvider>;
}
