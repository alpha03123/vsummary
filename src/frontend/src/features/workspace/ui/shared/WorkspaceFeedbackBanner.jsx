export function WorkspaceFeedbackBanner({ feedback }) {
  if (!feedback) {
    return null;
  }

  const toneClassName =
    feedback.tone === "success"
      ? "border-emerald-200/80 bg-emerald-50/80 text-emerald-900 dark:border-emerald-900/60 dark:bg-emerald-950/20 dark:text-emerald-100"
      : "border-stone-200/80 bg-stone-50/80 text-stone-700 dark:border-stone-800 dark:bg-stone-950/50 dark:text-stone-200";

  return (
    <div className={`rounded-[1.5rem] border px-5 py-4 text-sm ${toneClassName}`}>
      {feedback.message}
    </div>
  );
}
