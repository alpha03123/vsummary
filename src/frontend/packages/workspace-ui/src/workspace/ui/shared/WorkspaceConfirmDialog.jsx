import {AlertTriangle} from 'lucide-react';
import {WorkspaceDialog} from './WorkspaceDialog';
export function WorkspaceConfirmDialog({open,title,description,confirmLabel='确认',cancelLabel='取消',destructive=false,pending=false,onConfirm,onCancel}) {
 return <WorkspaceDialog open={open} title={title} description={description} icon={<AlertTriangle size={20}/>} pending={pending} onClose={onCancel} footer={<>
  <button type="button" onClick={onCancel} disabled={pending} className="rounded-2xl bg-soft px-5 py-2.5 text-sm font-semibold text-subtle transition-colors hover:bg-softer disabled:opacity-50">{cancelLabel}</button>
  <button type="button" onClick={onConfirm} disabled={pending} className={`rounded-2xl px-5 py-2.5 text-sm font-bold disabled:opacity-50 ${destructive?'btn-danger':'bg-inverse text-on-inverse hover:bg-inverse/90'}`}>{pending?'处理中...':confirmLabel}</button>
 </>}/>;
}
