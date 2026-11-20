import {lazy,Suspense,useEffect,useState} from 'react';
import {WorkspaceProvider,WorkspaceApplication} from '@alpha03123/vsummary-workspace-ui';
import {createLocalHost} from './local-features/workspace/localHost';
import {WorkspaceVideoScopeEmbed} from './local-features/workspace/ui/WorkspaceVideoScopeEmbed';
import {EXAMPLE_HASH_PREFIX} from './local-features/examples/ExampleCards';
import {MotionShowcase} from './dev/MotionShowcase';
const ExamplePage=lazy(()=>import('./local-features/examples/ExamplePage'));

function useHash(){
 const [hash,setHash]=useState(()=>window.location.hash);
 useEffect(()=>{
  const update=()=>setHash(window.location.hash);
  window.addEventListener('hashchange',update);
  return ()=>window.removeEventListener('hashchange',update);
 },[]);
 return hash;
}

function closeExample(){
 window.history.replaceState(null,'',window.location.pathname+window.location.search);
 window.dispatchEvent(new HashChangeEvent('hashchange'));
}

export function App(){
 const [host]=useState(createLocalHost);
 const hash=useHash();
 const embedded=new URLSearchParams(window.location.search).get('embed')==='video-scope';
 const exampleSlug=hash.startsWith(EXAMPLE_HASH_PREFIX)?hash.slice(EXAMPLE_HASH_PREFIX.length).match(/^[a-z0-9-]+/)?.[0]??null:null;
 return <WorkspaceProvider host={host}>
  {hash==='#test'?<MotionShowcase/>:embedded?<WorkspaceVideoScopeEmbed/>:<WorkspaceApplication/>}
  {exampleSlug&&!embedded?<Suspense fallback={null}><ExamplePage slug={exampleSlug} onClose={closeExample}/></Suspense>:null}
 </WorkspaceProvider>;
}
