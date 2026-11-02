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
            ? "text-body"
            : accent === "info"
              ? "text-info"
              : "text-subtle"
        } ${labelClassName}`.trim()}
      >
        {label}
      </p>
      <strong
        className={`mt-3 block text-4xl font-bold text-strong ${valueClassName}`.trim()}
      >
        {value}
      </strong>
    </article>
  );
}
