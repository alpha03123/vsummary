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
        ? "bg-info-subtle border-info/30"
        : "workspace-muted-panel";

  return (
    <article className={`${toneClassName} rounded-3xl border p-6 ${className}`.trim()}>
      <p
        className={`text-sm font-semibold uppercase tracking-widest ${
          accent === "accent"
            ? "text-stone-700 dark:text-zinc-300"
            : accent === "info"
              ? "text-info"
              : "text-stone-500 dark:text-stone-400"
        } ${labelClassName}`.trim()}
      >
        {label}
      </p>
      <strong
        className={`mt-3 block text-4xl font-bold text-stone-900 dark:text-stone-100 ${valueClassName}`.trim()}
      >
        {value}
      </strong>
    </article>
  );
}
