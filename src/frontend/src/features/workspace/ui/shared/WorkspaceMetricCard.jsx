export function WorkspaceMetricCard({
  label,
  value,
  accent = "muted",
  className = "",
  labelClassName = "",
  valueClassName = "",
}) {
  const toneClassName =
    accent === "accent"
      ? "workspace-accent-panel"
      : accent === "info"
        ? "border border-sky-200/80 bg-sky-50/80 dark:border-sky-900/60 dark:bg-sky-950/25"
        : "workspace-muted-panel";

  return (
    <article className={`${toneClassName} rounded-3xl border p-6 ${className}`.trim()}>
      <p
        className={`text-sm font-semibold uppercase tracking-widest ${
          accent === "accent"
            ? "text-stone-700 dark:text-zinc-300"
            : accent === "info"
              ? "text-sky-700 dark:text-sky-300"
              : "text-stone-500 dark:text-stone-400"
        } ${labelClassName}`.trim()}
      >
        {label}
      </p>
      <strong
        className={`mt-3 block text-4xl font-bold ${
          accent === "info"
            ? "text-sky-900 dark:text-sky-100"
            : "text-stone-900 dark:text-stone-100"
        } ${valueClassName}`.trim()}
      >
        {value}
      </strong>
    </article>
  );
}
