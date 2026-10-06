import {useMemo,useState} from 'react';
import {Check,Search,X} from 'lucide-react';
import {WorkspaceDialog} from './WorkspaceDialog';
import {WorkspaceSelectionBar} from './WorkspaceSelectionControls';

function formatDuration(seconds){
 const total=Math.ceil(seconds);
 return `${Math.floor(total/60)} 分 ${total%60} 秒`;
}

/** Hosts own the selection and commit; this surface never imports anything. */
export function WorkspaceImportSelection({open,items,selectedIds,onChange,onConfirm,onClose,pending=false,title='确认导入',confirmLabel='导入所选视频'}){
 const [search,setSearch]=useState('');
 const selected=new Set(selectedIds);
 const visible=useMemo(()=>items.filter(item=>item.title.toLocaleLowerCase().includes(search.trim().toLocaleLowerCase())),[items,search]);
 return <WorkspaceDialog open={open} title={title} onClose={onClose} pending={pending} className="max-w-2xl max-h-[85vh] overflow-y-auto"
  footer={<><button type="button" disabled={pending} onClick={onClose} className="rounded-2xl bg-stone-100 px-5 py-2.5 text-sm font-semibold text-stone-600 transition-colors hover:bg-stone-200 disabled:opacity-50 dark:bg-neutral-800 dark:text-zinc-300">取消</button><button type="button" disabled={pending||selectedIds.length===0} onClick={()=>onConfirm(selectedIds)} className="rounded-2xl bg-accent px-5 py-2.5 text-sm font-bold text-white shadow-sm transition-colors hover:bg-accent/90 disabled:cursor-not-allowed disabled:opacity-40">{pending?'正在准备…':confirmLabel}</button></>}>
  <div className="mb-4 flex flex-wrap items-center gap-2.5">
   <WorkspaceSelectionBar selectedCount={selectedIds.length} totalCount={items.length} disabled={pending} label="批量选择待导入视频" clearLabel="全不选"
    onSelectAll={()=>onChange(items.map(item=>item.id))} onClear={()=>onChange([])}/>
   <label className="workspace-input-surface ml-auto flex min-w-[10rem] flex-1 items-center gap-2 rounded-2xl border px-3.5 py-2.5 transition-colors focus-within:border-accent/50">
    <Search size={15} className="shrink-0 text-stone-400 dark:text-stone-500" aria-hidden="true"/>
    <input aria-label="搜索待导入视频" value={search} onChange={event=>setSearch(event.target.value)} placeholder="搜索视频" className="min-w-0 flex-1 bg-transparent text-sm text-stone-800 outline-none placeholder:text-stone-400 dark:text-stone-100 dark:placeholder:text-stone-500"/>
    {search&&<button type="button" onClick={()=>setSearch('')} aria-label="清空搜索" className="inline-flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-stone-400 transition-colors hover:bg-stone-200 hover:text-stone-600 dark:hover:bg-stone-700 dark:hover:text-stone-200"><X size={12}/></button>}
   </label>
  </div>
  <div className="max-h-[45vh] space-y-2 overflow-y-auto pr-1">{visible.map(item=>{
   const isSelected=selected.has(item.id);
   return <button key={item.id} type="button" role="checkbox" aria-checked={isSelected} disabled={pending}
    onClick={()=>onChange(isSelected?selectedIds.filter(id=>id!==item.id):[...selectedIds,item.id])}
    className={`flex w-full items-center gap-3 rounded-2xl border p-3.5 text-left transition-colors ${isSelected?'border-accent/40 bg-accent/5 hover:bg-accent/10':'border-stone-200 bg-white hover:border-stone-300 hover:bg-stone-50 dark:border-stone-700 dark:bg-transparent dark:hover:border-stone-600 dark:hover:bg-stone-800/40'}`}>
    <span aria-hidden="true" className={`inline-flex h-5 w-5 shrink-0 items-center justify-center rounded-md border transition-colors ${isSelected?'border-accent bg-accent text-white':'border-stone-300 bg-white text-transparent dark:border-stone-600 dark:bg-stone-900'}`}><Check size={13} strokeWidth={3}/></span>
    <span className="min-w-0 flex-1"><strong className="block truncate text-sm font-semibold text-stone-900 dark:text-stone-100">{item.title}</strong>{item.duration_seconds!=null&&<span className="mt-0.5 block text-xs text-stone-500 dark:text-stone-400">{formatDuration(item.duration_seconds)}</span>}</span>
   </button>;})}{visible.length===0&&<p className="py-10 text-center text-sm text-stone-500 dark:text-stone-400">没有匹配的视频</p>}</div>
 </WorkspaceDialog>;
}
