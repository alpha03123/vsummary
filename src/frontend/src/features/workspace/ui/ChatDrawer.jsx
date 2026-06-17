import { useEffect } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { X } from "lucide-react";

import { WorkspaceChatPanel } from "./WorkspaceChatPanel";

export function ChatDrawer({ isOpen, onClose, ...chatPanelProps }) {
  useEffect(() => {
    if (!isOpen) {
      return undefined;
    }
    function handleKey(event) {
      if (event.key === "Escape") {
        onClose();
      }
    }
    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
  }, [isOpen, onClose]);

  return (
    <AnimatePresence>
      {isOpen ? (
        <>
          <motion.div
            className="fixed inset-0 z-30 bg-black/20"
            onClick={onClose}
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.18 }}
            aria-hidden="true"
          />
          <motion.aside
            className="workspace-panel fixed right-0 top-0 bottom-0 z-40 w-[min(420px,90vw)] border-l border-stone-200/80 shadow-xl dark:border-stone-800"
            initial={{ x: "100%" }}
            animate={{ x: 0 }}
            exit={{ x: "100%" }}
            transition={{ type: "tween", duration: 0.22 }}
            role="dialog"
            aria-label="分析助手"
          >
            <div className="flex items-center justify-end border-b border-stone-200/70 px-4 py-2 dark:border-stone-800">
              <button
                type="button"
                onClick={onClose}
                aria-label="关闭对话"
                className="inline-flex h-8 w-8 items-center justify-center rounded-full text-stone-500 transition-colors hover:bg-stone-100 dark:text-stone-400 dark:hover:bg-stone-800"
              >
                <X size={16} />
              </button>
            </div>
            <div className="h-[calc(100%-3rem)]">
              <WorkspaceChatPanel {...chatPanelProps} />
            </div>
          </motion.aside>
        </>
      ) : null}
    </AnimatePresence>
  );
}
