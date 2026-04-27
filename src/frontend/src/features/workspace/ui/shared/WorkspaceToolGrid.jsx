import { ArrowRight } from "lucide-react";

export function WorkspaceToolGrid({ items, onSelect }) {
  return (
    <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
      {items.map(({ id, meta, disabled = false, hint }, index) => {
        const Icon = meta.icon;
        return (
          <button
            key={id}
            type="button"
            onClick={() => onSelect(id)}
            disabled={disabled}
            className={`motion-stagger group rounded-[1.5rem] p-5 text-left transition-all duration-200 hover:-translate-y-0.5 hover:bg-white dark:hover:bg-neutral-800 hover:shadow-[0_10px_24px_rgba(15,23,42,0.08)] dark:hover:shadow-[0_10px_24px_rgba(0,0,0,0.26)] ${meta.palette} ${
              disabled ? "cursor-not-allowed opacity-60" : "cursor-pointer"
            }`}
            style={{ "--stagger-index": index }}
          >
            <div className="flex items-start justify-between gap-4">
              <div className="flex items-start gap-3">
                <span className={`flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl shadow-sm shadow-slate-950/10 transition-colors group-hover:brightness-105 ${meta.iconShell}`}>
                  <Icon size={18} />
                </span>
                <span className="flex flex-col">
                  <span className="text-base font-bold">{meta.label}</span>
                  <span className="mt-1 text-xs text-stone-500 dark:text-stone-400">{meta.description}</span>
                  {hint ? <span className="mt-3 text-xs font-semibold text-stone-600 dark:text-stone-300">{hint}</span> : null}
                </span>
              </div>
              <span className={`motion-arrow-shift flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl border border-white/40 dark:border-stone-800 transition-colors group-hover:brightness-105 ${meta.arrowShell}`}>
                <ArrowRight size={18} />
              </span>
            </div>
          </button>
        );
      })}
    </div>
  );
}
