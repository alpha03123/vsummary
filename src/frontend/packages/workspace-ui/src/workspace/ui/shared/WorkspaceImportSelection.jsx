import {useMemo,useState} from 'react';
import {Square,CheckSquare,Search} from 'lucide-react';
import {WorkspaceDialog} from './WorkspaceDialog';

/** Hosts own the selection and commit; this surface never imports anything. */
export function WorkspaceImportSelection({open,items,selectedIds,onChange,onConfirm,onClose,pending=false,title='确认导入',confirmLabel='导入所选视频'}){
 const [search,setSearch]=useState('');
 const selected=new Set(selectedIds);
 const visible=useMemo(()=>items.filter(item=>item.title.toLocaleLowerCase().includes(search.trim().toLocaleLowerCase())),[items,search]);
 return <WorkspaceDialog open={open} title={title} onClose={onClose} pending={pending} className="max-w-2xl max-h-[85vh] overflow-y-auto"
  footer={<><button type="button" disabled={pending} onClick={onClose} className="rounded-xl border px-4 py-2 text-sm">取消</button><button type="button" disabled={pending||selectedIds.length===0} onClick={()=>onConfirm(selectedIds)} className="rounded-xl bg-accent px-4 py-2 text-sm font-semibold text-white disabled:opacity-40">{pending?'正在准备…':confirmLabel}</button></>}>
  <div className="mb-4 flex flex-wrap items-center gap-3 text-sm"><span>已选 {selectedIds.length} / {items.length}</span><button type="button" disabled={pending} onClick={()=>onChange(items.map(item=>item.id))} className="text-accent">全选</button><button type="button" disabled={pending} onClick={()=>onChange([])} className="text-stone-500">全不选</button>
   <label className="ml-auto flex items-center gap-2 rounded-xl border px-3 py-2"><Search size={15}/><input aria-label="搜索待导入视频" value={search} onChange={event=>setSearch(event.target.value)} className="min-w-0 bg-transparent text-sm outline-none" placeholder="搜索视频"/></label>
  </div>
  <div className="max-h-[45vh] space-y-2 overflow-y-auto">{visible.map(item=><button key={item.id} type="button" role="checkbox" aria-checked={selected.has(item.id)} disabled={pending} onClick={()=>onChange(selected.has(item.id)?selectedIds.filter(id=>id!==item.id):[...selectedIds,item.id])} className={`flex w-full items-center gap-3 rounded-2xl border p-4 text-left ${selected.has(item.id)?'border-accent/30 bg-accent/5':'border-stone-200 dark:border-stone-700'}`}>
   <span className={selected.has(item.id)?'text-accent':'text-stone-400'}>{selected.has(item.id)?<CheckSquare size={20}/>:<Square size={20}/>}</span><span className="min-w-0"><strong className="block truncate text-sm">{item.title}</strong>{item.duration_seconds!=null&&<span className="text-xs text-stone-500">{Math.floor(Math.ceil(item.duration_seconds)/60)} 分 {Math.ceil(item.duration_seconds)%60} 秒</span>}</span>
  </button>)}{visible.length===0&&<p className="py-8 text-center text-sm text-stone-500">没有匹配的视频</p>}</div>
 </WorkspaceDialog>;
}
