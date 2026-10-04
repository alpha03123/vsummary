import {useEffect,useRef,useState} from 'react';
import {Pencil} from 'lucide-react';
import {WorkspaceDialog} from './WorkspaceDialog';
export function WorkspaceRenameDialog({open,entityLabel,initialTitle,pending=false,onConfirm,onCancel}) {
 const [title,setTitle]=useState(initialTitle??'');const inputRef=useRef(null);
 useEffect(()=>{if(open){setTitle(initialTitle??'');requestAnimationFrame(()=>inputRef.current?.focus());}},[open,initialTitle]);
 const normalized=title.trim();
 return <WorkspaceDialog open={open} title="重命名" eyebrow={entityLabel} icon={<Pencil size={19}/>} pending={pending} onClose={onCancel} onSubmit={()=>normalized&&onConfirm?.(normalized)} footer={<>
 <button type="button" onClick={onCancel} disabled={pending} className="rounded-xl bg-stone-100 px-4 py-2.5 text-sm font-semibold text-stone-600 disabled:opacity-50 dark:bg-neutral-800 dark:text-zinc-300">取消</button>
 <button type="submit" disabled={!normalized||pending} className="rounded-xl bg-accent px-4 py-2.5 text-sm font-bold text-white disabled:opacity-50">{pending?'保存中...':'保存名称'}</button></>}>
 <label className="block text-sm font-medium text-stone-700 dark:text-stone-300" htmlFor="workspace-rename-title">新名称</label>
 <input ref={inputRef} id="workspace-rename-title" value={title} maxLength={200} disabled={pending} onChange={event=>setTitle(event.target.value)} className="workspace-input-surface mt-2 w-full rounded-xl border px-3 py-2.5 text-sm outline-none focus:border-accent"/>
 </WorkspaceDialog>;
}
