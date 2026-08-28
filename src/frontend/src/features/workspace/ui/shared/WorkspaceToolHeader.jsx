import { useEffect, useRef, useState } from "react";
import { ArrowLeft, ChevronDown, Download } from "lucide-react";

export function WorkspaceToolHeader({ meta, onBack, backLabel = "返回工具页", exportActions = [], badge = null }) {
  return (
    <div className="flex flex-wrap items-start justify-between gap-4">
      <div className="min-w-[min(11rem,100%)] flex-1">
        <p className="mb-1 text-xs font-bold uppercase text-stone-600 dark:text-stone-400">Tool Page</p>
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5">
          <h1 className="text-2xl font-bold leading-snug text-stone-900 dark:text-stone-100">{meta?.label}</h1>
          {badge ? (
            <span className="inline-flex shrink-0 items-center rounded-full border border-stone-200 bg-stone-100/80 px-2.5 py-0.5 text-xs font-semibold text-stone-600 dark:border-stone-700 dark:bg-stone-800/70 dark:text-stone-300">
              {badge}
            </span>
          ) : null}
        </div>
        <p className="mt-2 text-sm text-stone-600 dark:text-stone-400">{meta?.description}</p>
      </div>
      <div className="ml-auto flex max-w-full shrink-0 flex-wrap justify-end gap-2">
        {exportActions.length ? <WorkspaceExportMenu exportActions={exportActions} /> : null}
        <button
          type="button"
          onClick={onBack}
          className="workspace-elevated-panel inline-flex shrink-0 items-center gap-2 whitespace-nowrap rounded-xl border px-4 py-2 text-sm font-semibold text-stone-700 transition-all hover:-translate-y-0.5 hover:border-stone-300 hover:bg-white hover:text-stone-900 dark:text-stone-200 dark:hover:border-white/16 dark:hover:bg-neutral-800 dark:hover:text-stone-100"
        >
          <ArrowLeft size={16} />
          {backLabel}
        </button>
      </div>
    </div>
  );
}

export function WorkspaceExportMenu({ exportActions, buttonLabel = "导出" }) {
  const [open, setOpen] = useState(false);
  const menuRef = useRef(null);
  const enabledActions = exportActions.filter((action) => action.enabled);
  const disabledReason = exportActions.find((action) => !action.enabled)?.disabledReason ?? "当前内容不可导出";
  const disabled = enabledActions.length === 0;
  const className = "workspace-elevated-panel inline-flex shrink-0 items-center gap-2 whitespace-nowrap rounded-xl border px-4 py-2 text-sm font-semibold transition-all";

  useEffect(() => {
    if (!open) {
      return undefined;
    }
    function handlePointerDown(event) {
      if (menuRef.current && !menuRef.current.contains(event.target)) {
        setOpen(false);
      }
    }
    window.addEventListener("pointerdown", handlePointerDown);
    return () => window.removeEventListener("pointerdown", handlePointerDown);
  }, [open]);

  if (disabled) {
    return (
      <button
        type="button"
        disabled
        title={disabledReason}
        className={`${className} cursor-not-allowed text-stone-500 opacity-50 dark:text-stone-500`}
      >
        <Download size={16} />
        {buttonLabel}
        <ChevronDown size={14} />
      </button>
    );
  }

  return (
    <div ref={menuRef} className="relative shrink-0">
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        className={`${className} text-stone-700 hover:-translate-y-0.5 hover:border-stone-300 hover:bg-white hover:text-stone-900 dark:text-stone-200 dark:hover:border-white/16 dark:hover:bg-neutral-800 dark:hover:text-stone-100`}
      >
        <Download size={16} />
        {buttonLabel}
        <ChevronDown size={14} className={`transition-transform ${open ? "rotate-180" : ""}`} />
      </button>
      {open ? (
        <div className="workspace-elevated-panel absolute right-0 z-30 mt-2 w-44 overflow-hidden rounded-2xl border p-1 shadow-xl">
          {exportActions.map((action) => action.enabled ? (
            <a
              key={action.href}
              href={action.href}
              download
              onClick={() => setOpen(false)}
              className="flex items-center gap-2 rounded-xl px-3 py-2 text-sm font-semibold text-stone-700 transition hover:bg-stone-100 hover:text-stone-900 dark:text-stone-200 dark:hover:bg-neutral-800"
            >
              <Download size={15} />
              {action.label ?? "导出 MD"}
            </a>
          ) : (
            <button
              key={action.href}
              type="button"
              disabled
              title={action.disabledReason ?? "当前内容不可导出"}
              className="flex w-full cursor-not-allowed items-center gap-2 rounded-xl px-3 py-2 text-left text-sm font-semibold text-stone-500 opacity-60 dark:text-stone-500"
            >
              <Download size={15} />
              {action.label ?? "导出 MD"}
            </button>
          ))}
        </div>
      ) : null}
    </div>
  );
}
