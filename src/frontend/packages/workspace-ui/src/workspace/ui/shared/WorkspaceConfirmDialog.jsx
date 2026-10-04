import {AlertTriangle} from 'lucide-react';
import {WorkspaceDialog} from './WorkspaceDialog';
export function WorkspaceConfirmDialog({open,title,description,confirmLabel='确认',cancelLabel='取消',destructive=false,pending=false,onConfirm,onCancel}) {
 return <WorkspaceDialog open={open} title={title} description={description} icon={<AlertTriangle size={20}/>} pending={pending} onClose={onCancel} footer={<>
  <button type="button" onClick={onCancel} disabled={pending} className="rounded-2xl bg-stone-100 px-5 py-2.5 text-sm font-semibold text-stone-600 transition-colors hover:bg-stone-200 disabled:opacity-50 dark:bg-neutral-800 dark:text-zinc-300">{cancelLabel}</button>
  <button type="button" onClick={onConfirm} disabled={pending} className={`rounded-2xl px-5 py-2.5 text-sm font-bold text-white disabled:opacity-50 ${destructive?'btn-danger':'bg-stone-900 hover:bg-black dark:bg-white dark:text-stone-900'}`}>{pending?'处理中...':confirmLabel}</button>
 </>}/>;
}
