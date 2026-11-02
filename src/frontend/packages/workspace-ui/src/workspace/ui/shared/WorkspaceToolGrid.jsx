import { ArrowRight, Lock } from "lucide-react";

/**
 * Status chip colours. Keys match the `tone` values returned by
 * `describeToolState` / `SOURCE_MISSING_STATUS` in workspaceToolMeta.js.
 */
const STATUS_TONES = {
  ready:
    "border-success-border/80 bg-success-subtle text-success",
  pending:
    "border-line bg-soft text-subtle",
  blocked:
    "border-warning-border/80 bg-warning-subtle text-warning",
  loading:
    "border-line bg-soft text-faint",
};

/**
 * Disabled tiles keep readable text instead of fading the whole card with
 * `opacity-60` (which took the label and its explanation down with it). The
 * dashed border + lock icon carry "you can't use this yet", and the status
 * chip says why.
 */
const DISABLED_VISUALS = {
  palette: "border border-dashed border-line-strong bg-muted/70",
  iconShell: "border border-line bg-soft text-faint",
  arrowShell: "border border-dashed border-line-strong bg-transparent text-faint",
};

function ToolStatusChip({ label, tone }) {
  return (
    <span
      className={`mt-3 inline-flex w-fit shrink-0 whitespace-nowrap items-center rounded-full border px-2 py-0.5 text-xs font-semibold ${
        STATUS_TONES[tone] ?? STATUS_TONES.pending
      }`}
    >
      {label}
    </span>
  );
}

export function WorkspaceToolGrid({ items, onSelect }) {
  return (
    /* Column count is driven by one threshold. It was `17rem` (272px), which
       needed ~556px of container before a second column appeared — but the
       middle pane defaults to 640px and is user-resizable, so any width between
       roughly 460–556px fell back to a single full-bleed column: a 380px-wide
       card holding three lines of text and a lot of dead space. At `14rem`
       (224px) two columns fit from ~460px, so the default 640px pane shows a
       balanced pair (314px each) and the single-column case only survives in
       genuinely narrow panes. */
    <div className="grid gap-3 [grid-template-columns:repeat(auto-fit,minmax(min(100%,14rem),1fr))]">
      {items.map(({ id, meta, status = null, description, disabled = false }, index) => {
        const Icon = meta.icon;
        return (
          <button
            key={id}
            type="button"
            onClick={() => onSelect(id)}
            disabled={disabled}
            className={`motion-stagger group rounded-2xl p-5 text-left transition-all duration-200 ${
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
                  <span className={`text-base font-bold ${disabled ? "text-faint" : ""}`}>
                    {meta.label}
                  </span>
                  <span
                    className={`mt-1 text-xs ${
                      disabled ? "text-faint" : "text-subtle"
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
                    : `motion-arrow-shift border border-white/40 dark:border-line group-hover:brightness-105 ${meta.arrowShell}`
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
