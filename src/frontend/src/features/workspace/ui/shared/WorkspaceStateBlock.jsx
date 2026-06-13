import { LoaderCircle } from "lucide-react";

export function WorkspaceStateBlock({
  eyebrow,
  title,
  description,
  children,
  tone = "default",
  loading = false,
  dashed = false,
  centered = true,
}) {
  const toneClassName =
    tone === "accent"
      ? "workspace-accent-panel"
      : tone === "elevated"
        ? "workspace-elevated-panel"
        : "workspace-muted-panel";

  return (
    <div
      className={`${toneClassName} flex min-h-[320px] rounded-3xl border mt-10 p-6 ${
        centered ? "items-center justify-center text-center" : ""
      } ${dashed ? "border-dashed" : ""}`}
    >
      <div className={`${centered ? "max-w-md" : "w-full"}`}>
        {loading ? (
          <div className="mx-auto mb-4 inline-flex h-12 w-12 items-center justify-center rounded-2xl bg-white/90 text-accent shadow-sm dark:bg-stone-950/90">
            <LoaderCircle size={20} strokeWidth={2.2} className="animate-spin" />
          </div>
        ) : null}
        {eyebrow ? (
          <p className="text-xs font-bold uppercase tracking-widest text-stone-500 dark:text-stone-400">{eyebrow}</p>
        ) : null}
        <h3 className="mt-3 text-2xl font-bold text-stone-900 dark:text-stone-100">{title}</h3>
        {description ? (
          <p className="mt-3 text-sm leading-relaxed text-stone-500 dark:text-stone-400">{description}</p>
        ) : null}
        {children ? <div className="mt-5">{children}</div> : null}
      </div>
    </div>
  );
}
