import { X } from "lucide-react";

export function WorkspaceFeedbackBanner({ feedback, onDismiss }) {
  if (!feedback) {
    return null;
  }

  const toneClassName =
    feedback.tone === "success"
      ? "border-success bg-success-subtle text-success"
      : "border-stone-200/80 bg-stone-50/80 text-stone-700 dark:border-stone-800 dark:bg-stone-950/50 dark:text-stone-200";


  return (
    <div className={`flex items-start gap-3 rounded-[1.5rem] border px-5 py-4 text-sm ${toneClassName}`}>
      <span className="min-w-0 flex-1">{feedback.message}</span>
      {typeof onDismiss === "function" ? (
        <button
          type="button"
          onClick={onDismiss}
          className="inline-flex h-6 w-6 shrink-0 items-center justify-center rounded-full opacity-70 transition-colors hover:bg-white/70 hover:opacity-100 dark:hover:bg-black/20"
          title="关闭提示"
          aria-label="关闭提示"
        >
          <X size={14} />
        </button>
      ) : null}
    </div>
  );
}
