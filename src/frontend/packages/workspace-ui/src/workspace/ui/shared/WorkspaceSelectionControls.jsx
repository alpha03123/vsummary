import {CheckCheck,X} from 'lucide-react';

const SURFACES={
 inset:'workspace-muted-panel',
 raised:'border-line/80 bg-surface/95 shadow-lg backdrop-blur-sm',
};

const ACTION_CLASS='inline-flex shrink-0 items-center gap-1.5 rounded-xl px-2.5 py-1.5 text-xs font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-45';

/**
 * Bulk-selection toolbar shared by the series shelf, the library video list and the
 * import dialog: a count chip plus select-all / clear actions.
 *
 * The count is the highest-contrast element (accent once everything is selected) so the
 * bar answers "how much is selected?" before any of the buttons answer "what next?".
 * Callers append their own destructive actions through `extra` so they keep the same
 * height and radius as the built-in buttons. The bar stays on one line: as it narrows (a slim
 * sidebar, a larger browser font) the built-in buttons drop their labels, then the "已选" word.
 * Breakpoints are in rem so they grow with the browser's font size.
 */
export function WorkspaceSelectionBar({
 selectedCount,totalCount,onSelectAll,onClear,
 selectAllLabel='全选',clearLabel='取消',label='选择操作',
 disabled=false,selectAllDisabled=disabled,clearDisabled=disabled,
 surface='inset',extra=null,className='',
}){
 const allSelected=Boolean(totalCount)&&selectedCount>=totalCount;
 return <div role="group" aria-label={label} className={`@container flex items-center justify-between gap-2 rounded-2xl border p-1.5 ${SURFACES[surface]??SURFACES.inset} ${className}`}>
  <span className="flex min-w-0 items-center gap-1 px-2.5 text-xs font-semibold text-faint">
   <span className="hidden @[12rem]:inline">已选</span>
   <b className={`tabular-nums ${allSelected?'text-accent':'text-strong'}`}>{selectedCount}</b>
   {totalCount!=null&&<span className="tabular-nums font-medium text-faint">/ {totalCount}</span>}
  </span>
  <div className="flex shrink-0 items-center gap-1">
   <button type="button" disabled={selectAllDisabled} onClick={onSelectAll} aria-label={selectAllLabel} title={selectAllLabel}
    className={`${ACTION_CLASS} text-subtle hover:bg-surface hover:shadow-sm`}>
    <CheckCheck size={14} aria-hidden="true"/><span className="hidden @[16.75rem]:inline">{selectAllLabel}</span>
   </button>
   <button type="button" disabled={clearDisabled||selectedCount===0} onClick={onClear} aria-label={clearLabel} title={clearLabel}
    className={`${ACTION_CLASS} text-faint hover:bg-surface hover:shadow-sm`}>
    <X size={14} aria-hidden="true"/><span className="hidden @[16.75rem]:inline">{clearLabel}</span>
   </button>
   {extra}
  </div>
 </div>;
}
