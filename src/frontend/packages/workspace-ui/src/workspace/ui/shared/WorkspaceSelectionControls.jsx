import {CheckCheck,X} from 'lucide-react';

const SURFACES={
 inset:'workspace-muted-panel',
 raised:'border-stone-200/80 bg-white/95 shadow-lg backdrop-blur-sm dark:border-stone-700 dark:bg-neutral-900/95',
};

const ACTION_CLASS='inline-flex shrink-0 items-center gap-1.5 rounded-xl px-2.5 py-1.5 text-xs font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-45';

/**
 * Bulk-selection toolbar shared by the series shelf, the library video list and the
 * import dialog: a count chip plus select-all / clear actions.
 *
 * The count is the highest-contrast element (accent once everything is selected) so the
 * bar answers "how much is selected?" before any of the buttons answer "what next?".
 * Callers append their own destructive actions through `extra` so they keep the same
 * height and radius as the built-in buttons.
 */
export function WorkspaceSelectionBar({
 selectedCount,totalCount,onSelectAll,onClear,
 selectAllLabel='全选',clearLabel='取消',label='选择操作',
 disabled=false,selectAllDisabled=disabled,clearDisabled=disabled,
 surface='inset',extra=null,className='',
}){
 const allSelected=Boolean(totalCount)&&selectedCount>=totalCount;
 return <div role="group" aria-label={label} className={`flex items-center justify-between gap-2 rounded-2xl border p-1.5 ${SURFACES[surface]??SURFACES.inset} ${className}`}>
  <span className="flex min-w-0 items-center gap-1 px-2.5 text-xs font-semibold text-stone-500 dark:text-stone-400">
   <span className="truncate">已选</span>
   <b className={`tabular-nums ${allSelected?'text-accent':'text-stone-900 dark:text-stone-100'}`}>{selectedCount}</b>
   {totalCount!=null&&<span className="tabular-nums font-medium text-stone-400 dark:text-stone-500">/ {totalCount}</span>}
  </span>
  <div className="flex shrink-0 items-center gap-1">
   <button type="button" disabled={selectAllDisabled} onClick={onSelectAll}
    className={`${ACTION_CLASS} text-stone-600 hover:bg-white hover:shadow-sm dark:text-stone-300 dark:hover:bg-stone-800`}>
    <CheckCheck size={14} aria-hidden="true"/>{selectAllLabel}
   </button>
   <button type="button" disabled={clearDisabled||selectedCount===0} onClick={onClear}
    className={`${ACTION_CLASS} text-stone-500 hover:bg-white hover:shadow-sm dark:text-stone-400 dark:hover:bg-stone-800`}>
    <X size={14} aria-hidden="true"/>{clearLabel}
   </button>
   {extra}
  </div>
 </div>;
}
