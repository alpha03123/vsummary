import { useEffect, useRef, useState } from "react";
import { Pencil } from "lucide-react";
import { AnimatePresence, motion } from "framer-motion";

export function WorkspaceRenameDialog({ open, entityLabel, initialTitle, pending = false, onConfirm, onCancel }) {
  const [title, setTitle] = useState(initialTitle ?? "");
  const inputRef = useRef(null);

  useEffect(() => {
    if (!open) return;
    setTitle(initialTitle ?? "");
    requestAnimationFrame(() => inputRef.current?.focus());
  }, [initialTitle, open]);

  if (!open) return null;
  const normalizedTitle = title.trim();

  return (
    <AnimatePresence>
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        className="fixed inset-0 z-[70] flex items-center justify-center bg-black/45 p-4 backdrop-blur-sm"
        onClick={(event) => {
          if (event.target === event.currentTarget && !pending) onCancel?.();
        }}
      >
        <motion.form
          initial={{ opacity: 0, scale: 0.96, y: 12 }}
          animate={{ opacity: 1, scale: 1, y: 0 }}
          exit={{ opacity: 0, scale: 0.96, y: 12 }}
          transition={{ type: "spring", stiffness: 360, damping: 28 }}
          className="workspace-panel w-full max-w-md rounded-[2rem] border p-6 shadow-2xl"
          onSubmit={(event) => {
            event.preventDefault();
            if (normalizedTitle && !pending) onConfirm?.(normalizedTitle);
          }}
        >
          <div className="flex items-start gap-4">
            <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl border border-accent/20 bg-accent/10 text-accent">
              <Pencil size={19} />
            </div>
            <div className="min-w-0 flex-1">
              <p className="text-xs font-semibold text-stone-500 dark:text-stone-400">{entityLabel}</p>
              <h3 className="mt-1 text-lg font-bold text-stone-900 dark:text-stone-100">重命名</h3>
              <label className="mt-5 block text-sm font-medium text-stone-700 dark:text-stone-300" htmlFor="workspace-rename-title">新名称</label>
              <input
                ref={inputRef}
                id="workspace-rename-title"
                value={title}
                maxLength={200}
                disabled={pending}
                onChange={(event) => setTitle(event.target.value)}
                className="workspace-input-surface mt-2 w-full rounded-xl border px-3 py-2.5 text-sm text-stone-900 outline-none transition-colors focus:border-accent dark:text-stone-100"
              />
            </div>
          </div>
          <div className="mt-6 flex justify-end gap-3">
            <button type="button" onClick={onCancel} disabled={pending} className="rounded-xl bg-stone-100 px-4 py-2.5 text-sm font-semibold text-stone-600 transition-colors hover:bg-stone-200 disabled:cursor-not-allowed disabled:opacity-50 dark:bg-neutral-800 dark:text-zinc-300 dark:hover:bg-neutral-700">取消</button>
            <button type="submit" disabled={!normalizedTitle || pending} className="rounded-xl bg-accent px-4 py-2.5 text-sm font-bold text-white transition-colors hover:bg-accent/90 disabled:cursor-not-allowed disabled:opacity-50">{pending ? "保存中..." : "保存名称"}</button>
          </div>
        </motion.form>
      </motion.div>
    </AnimatePresence>
  );
}
