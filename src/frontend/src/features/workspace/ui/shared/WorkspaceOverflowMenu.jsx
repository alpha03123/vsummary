import { createPortal } from "react-dom";
import { useEffect, useRef, useState } from "react";
import { MoreHorizontal } from "lucide-react";

import { useOutsidePointerUp } from "../../../../shared/lib/useOutsidePointerUp";

/** A shared overflow menu that escapes scroll containers through a portal. */
export function WorkspaceOverflowMenu({
  open,
  onOpenChange,
  disabled = false,
  label = "更多操作",
  placement = "top",
  menuClassName = "min-w-[148px]",
  children,
}) {
  const triggerRef = useRef(null);
  const menuRef = useRef(null);
  const [position, setPosition] = useState(null);

  const updatePosition = () => {
    const bounds = triggerRef.current?.getBoundingClientRect();
    if (!bounds) {
      return;
    }
    setPosition({
      right: Math.max(16, window.innerWidth - bounds.right),
      vertical: placement === "top"
        ? { bottom: window.innerHeight - bounds.top + 8 }
        : { top: bounds.bottom + 8 },
    });
  };

  useEffect(() => {
    if (!open) {
      return undefined;
    }
    updatePosition();
    window.addEventListener("resize", updatePosition);
    window.addEventListener("scroll", updatePosition, true);
    return () => {
      window.removeEventListener("resize", updatePosition);
      window.removeEventListener("scroll", updatePosition, true);
    };
  }, [open, placement]);

  useOutsidePointerUp(open, [triggerRef, menuRef], () => onOpenChange(false));

  return (
    <>
      <button
        ref={triggerRef}
        type="button"
        disabled={disabled}
        onClick={() => onOpenChange(!open)}
        className="inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-xl text-stone-500 transition-colors hover:bg-stone-100 hover:text-stone-700 disabled:cursor-not-allowed disabled:opacity-50 dark:text-stone-400 dark:hover:bg-stone-800 dark:hover:text-stone-200"
        title={label}
        aria-label={label}
        aria-expanded={open}
      >
        <MoreHorizontal size={18} />
      </button>
      {open && position ? createPortal(
        <div
          ref={menuRef}
          className={`fixed z-[70] ${menuClassName} rounded-2xl border border-stone-200 bg-white p-1 shadow-xl motion-fade-scale dark:border-stone-700 dark:bg-neutral-900`}
          style={{ right: position.right, ...position.vertical }}
        >
          {children}
        </div>,
        document.body,
      ) : null}
    </>
  );
}
