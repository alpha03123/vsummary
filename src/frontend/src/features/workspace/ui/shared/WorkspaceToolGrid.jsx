import { ArrowRight, Lock } from "lucide-react";

/**
 * Status chip colours. Keys match the `tone` values returned by
 * `describeToolState` / `SOURCE_MISSING_STATUS` in workspaceToolMeta.js.
 */
const STATUS_TONES = {
  ready:
    "border-emerald-200/80 bg-emerald-50 text-emerald-700 dark:border-emerald-900/70 dark:bg-emerald-950/40 dark:text-emerald-300",
  pending:
    "border-stone-200 bg-stone-100 text-stone-600 dark:border-stone-700 dark:bg-neutral-800 dark:text-stone-300",
  blocked:
    "border-amber-200/80 bg-amber-50 text-amber-800 dark:border-amber-900/70 dark:bg-amber-950/40 dark:text-amber-300",
  loading:
    "border-stone-200 bg-stone-100 text-stone-500 dark:border-stone-700 dark:bg-neutral-800 dark:text-stone-400",
};

/**
 * Disabled tiles keep readable text instead of fading the whole card with
 * `opacity-60` (which took the label and its explanation down with it). The
 * dashed border + lock icon carry "you can't use this yet", and the status
 * chip says why.
 */
const DISABLED_VISUALS = {
  palette: "border border-dashed border-stone-300 bg-stone-50/70 dark:border-stone-700 dark:bg-neutral-900/40",
  iconShell: "border border-stone-200 bg-stone-100 text-stone-400 dark:border-stone-800 dark:bg-neutral-800 dark:text-stone-500",
  arrowShell: "border border-dashed border-stone-300 bg-transparent text-stone-400 dark:border-stone-700 dark:text-stone-500",
};

function ToolStatusChip({ label, tone }) {
  return (
    <span
      className={`mt-3 inline-flex w-fit items-center rounded-full border px-2 py-0.5 text-[11px] font-semibold ${
        STATUS_TONES[tone] ?? STATUS_TONES.pending
      }`}
    >
      {label}
    </span>
  );
}

export function WorkspaceToolGrid({ items, onSelect }) {
  return (
    <div className="grid gap-3 [grid-template-columns:repeat(auto-fit,minmax(min(100%,17rem),1fr))]">
      {items.map(({ id, meta, status = null, description, disabled = false }, index) => {
        const Icon = meta.icon;
        return (
          <button
            key={id}
            type="button"
            onClick={() => onSelect(id)}
            disabled={disabled}
            className={`motion-stagger group rounded-[1.5rem] p-5 text-left transition-all duration-200 ${
              disabled ? `cursor-not-allowed ${DISABLED_VISUALS.palette}` : `cursor-pointer ${meta.palette}`
            }`}
            style={{ "--stagger-index": index }}
          >
            <div className="relative pr-12">
              <div className="flex min-w-0 items-start gap-3">
                <span
                  className={`flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl shadow-sm shadow-slate-950/10 ${
                    disabled
                      ? DISABLED_VISUALS.iconShell
                      : `${meta.iconShell} transition-colors group-hover:brightness-105`
                  }`}
                >
                  <Icon size={18} />
                </span>
                <span className="flex min-w-0 flex-col">
                  <span className={`text-base font-bold ${disabled ? "text-stone-500 dark:text-stone-400" : ""}`}>
                    {meta.label}
                  </span>
                  <span
                    className={`mt-1 text-xs ${
                      disabled ? "text-stone-400 dark:text-stone-500" : "text-stone-600 dark:text-stone-400"
                    }`}
                  >
                    {description ?? meta.description}
                  </span>
                  {status ? <ToolStatusChip {...status} /> : null}
                </span>
              </div>
              <span
                className={`absolute right-0 top-0 flex h-11 w-11 items-center justify-center rounded-2xl transition-colors ${
                  disabled
                    ? DISABLED_VISUALS.arrowShell
                    : `motion-arrow-shift border border-white/40 dark:border-stone-800 group-hover:brightness-105 ${meta.arrowShell}`
                }`}
              >
                {disabled ? <Lock size={16} aria-hidden="true" /> : <ArrowRight size={18} />}
              </span>
            </div>
          </button>
        );
      })}
    </div>
  );
}
