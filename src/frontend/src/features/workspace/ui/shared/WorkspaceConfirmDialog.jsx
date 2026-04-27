import { AlertTriangle } from "lucide-react";
import { AnimatePresence, motion } from "framer-motion";

export function WorkspaceConfirmDialog({
  open,
  title,
  description,
  confirmLabel = "确认",
  cancelLabel = "取消",
  destructive = false,
  pending = false,
  onConfirm,
  onCancel,
}) {
  if (!open) {
    return null;
  }

  return (
    <AnimatePresence>
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        className="fixed inset-0 z-[70] flex items-center justify-center bg-black/45 p-4 backdrop-blur-sm"
        onClick={(event) => {
          if (event.target === event.currentTarget && !pending) {
            onCancel?.();
          }
        }}
      >
        <motion.div
          initial={{ opacity: 0, scale: 0.96, y: 12 }}
          animate={{ opacity: 1, scale: 1, y: 0 }}
          exit={{ opacity: 0, scale: 0.96, y: 12 }}
          transition={{ type: "spring", stiffness: 360, damping: 28 }}
          className="workspace-panel w-full max-w-md rounded-[2rem] border p-6 shadow-2xl"
        >
          <div className="flex items-start gap-4">
            <div className={`flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl border ${
              destructive
                ? "border-red-200 bg-red-50 text-red-600 dark:border-red-900/60 dark:bg-red-950/30 dark:text-red-300"
                : "border-stone-200 bg-stone-50 text-stone-600 dark:border-stone-700 dark:bg-neutral-900 dark:text-stone-300"
            }`}>
              <AlertTriangle size={20} />
            </div>
            <div className="min-w-0">
              <h3 className="text-lg font-bold text-stone-900 dark:text-stone-100">{title}</h3>
              <p className="mt-2 text-sm leading-relaxed text-stone-500 dark:text-stone-400">{description}</p>
            </div>
          </div>

          <div className="mt-6 flex justify-end gap-3">
            <button
              type="button"
              onClick={onCancel}
              disabled={pending}
              className="rounded-2xl bg-stone-100 px-5 py-2.5 text-sm font-semibold text-stone-600 transition-colors hover:bg-stone-200 disabled:cursor-not-allowed disabled:opacity-50 dark:bg-neutral-800 dark:text-zinc-300 dark:hover:bg-neutral-700"
            >
              {cancelLabel}
            </button>
            <button
              type="button"
              onClick={onConfirm}
              disabled={pending}
              className={`rounded-2xl px-5 py-2.5 text-sm font-bold text-white transition-colors disabled:cursor-not-allowed disabled:opacity-50 ${
                destructive
                  ? "btn-danger"
                  : "bg-stone-900 hover:bg-black dark:bg-white dark:text-stone-900 dark:hover:bg-stone-100"
              }`}
            >
              {pending ? "处理中..." : confirmLabel}
            </button>
          </div>
        </motion.div>
      </motion.div>
    </AnimatePresence>
  );
}
