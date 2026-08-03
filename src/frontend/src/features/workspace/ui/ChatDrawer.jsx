import { useEffect } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { X } from "lucide-react";

import { WorkspaceChatPanel } from "./WorkspaceChatPanel";

export function ChatDrawer({ isOpen, onClose, width, onWidthChange, ...chatPanelProps }) {
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

  function beginResize(startEvent) {
    startEvent.preventDefault();
    startEvent.stopPropagation();
    const startX = startEvent.clientX;
    const startWidth = width;

    function handlePointerMove(event) {
      onWidthChange(startWidth + startX - event.clientX);
    }

    function handlePointerUp() {
      window.removeEventListener("pointermove", handlePointerMove);
      window.removeEventListener("pointerup", handlePointerUp);
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
    }

    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";
    window.addEventListener("pointermove", handlePointerMove);
    window.addEventListener("pointerup", handlePointerUp, { once: true });
  }

  function handleResizeKeyDown(event) {
    if (event.key === "ArrowLeft") {
      event.preventDefault();
      onWidthChange(width + 32);
    } else if (event.key === "ArrowRight") {
      event.preventDefault();
      onWidthChange(width - 32);
    }
  }

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
            className="workspace-panel fixed right-0 top-0 bottom-0 z-40 border-l border-stone-200/80 shadow-xl dark:border-stone-800"
            style={{ width: `min(${width}px, calc(100vw - 32px))` }}
            initial={{ x: "100%" }}
            animate={{ x: 0 }}
            exit={{ x: "100%" }}
            transition={{ type: "tween", duration: 0.22 }}
            role="dialog"
            aria-label="分析助手"
          >
            <div
              role="separator"
              tabIndex={0}
              aria-orientation="vertical"
              aria-label="调整分析助手宽度"
              onPointerDown={beginResize}
              onKeyDown={handleResizeKeyDown}
              className="group absolute -left-2 top-0 z-10 flex h-full w-4 cursor-col-resize touch-none items-center justify-center outline-none"
            >
              <div className="h-16 w-1 rounded-full bg-stone-300/90 transition-colors group-hover:bg-accent group-focus-visible:bg-accent dark:bg-stone-700 dark:group-hover:bg-accent" />
            </div>
            <div className="flex items-center justify-end border-b border-stone-200/70 px-4 py-2 dark:border-stone-800">
              <button
                type="button"
                onClick={onClose}
                aria-label="关闭对话"
                className="inline-flex h-8 w-8 items-center justify-center rounded-full text-stone-600 transition-colors hover:bg-stone-100 dark:text-stone-400 dark:hover:bg-stone-800"
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
