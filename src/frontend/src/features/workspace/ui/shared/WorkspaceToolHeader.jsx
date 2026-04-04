import { ArrowLeft } from "lucide-react";

export function WorkspaceToolHeader({ meta, onBack, backLabel = "返回工具页" }) {
  return (
    <div className="flex items-start justify-between gap-4">
      <div>
        <p className="text-xs font-bold text-stone-500 dark:text-stone-400 uppercase mb-1">Tool Page</p>
        <h2 className="text-2xl font-bold text-stone-900 dark:text-stone-100 leading-snug">{meta?.label}</h2>
        <p className="mt-2 text-sm text-stone-500 dark:text-stone-400">{meta?.description}</p>
      </div>
      <button
        type="button"
        onClick={onBack}
        className="workspace-elevated-panel inline-flex items-center gap-2 rounded-2xl border px-4 py-2 text-sm font-semibold text-stone-700 dark:text-stone-200 transition-all hover:border-stone-300 dark:hover:border-white/16 hover:bg-white dark:hover:bg-[#1f1f1f] hover:text-stone-900 dark:hover:text-stone-100 hover:-translate-y-0.5"
      >
        <ArrowLeft size={16} />
        {backLabel}
      </button>
    </div>
  );
}
