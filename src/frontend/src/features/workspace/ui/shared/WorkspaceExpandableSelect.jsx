import { useState, useRef, useEffect } from "react";
import { ChevronRight, ChevronLeft } from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import { useOutsidePointerUp } from "../../../../shared/lib/useOutsidePointerUp";

/**
 * 横向展开式选择器
 * 默认显示当前选项和右箭头，点击展开显示所有选项
 */
export function WorkspaceExpandableSelect({
  value,
  onChange,
  options,
  className = "",
  disabled = false,
  ariaLabel,
}) {
  const [isExpanded, setIsExpanded] = useState(false);
  const containerRef = useRef(null);

  const selectedOption = options.find((o) => o.id === value);
  const availableOptions = options.filter((o) => !o.disabled);

  useOutsidePointerUp(isExpanded, [containerRef], () => setIsExpanded(false));

  function handleOptionClick(optionId) {
    onChange(optionId);
    setIsExpanded(false);
  }

  function handleToggle() {
    if (!disabled) {
      setIsExpanded((prev) => !prev);
    }
  }

  return (
    <div ref={containerRef} className={`relative ${className}`}>
      <button
        type="button"
        onClick={handleToggle}
        disabled={disabled}
        aria-label={ariaLabel}
        aria-expanded={isExpanded}
        className="inline-flex items-center gap-4 rounded-2xl border border-stone-200 bg-white px-4 py-3 transition-colors hover:border-accent/50 disabled:cursor-not-allowed disabled:opacity-50 dark:border-stone-700 dark:bg-neutral-900 dark:hover:border-accent/50"
      >
        <span className="text-sm font-semibold text-stone-900 dark:text-stone-100">
          {selectedOption?.label ?? value}
        </span>
        <span className="text-stone-400 dark:text-zinc-500">
          {isExpanded ? <ChevronLeft size={16} /> : <ChevronRight size={16} />}
        </span>
      </button>

        <AnimatePresence initial={false}>
          {isExpanded && (
            <motion.div
              key="options"
              initial={{ opacity: 0, x: -4, clipPath: "inset(0 100% 0 0)" }}
              animate={{ opacity: 1, x: 0, clipPath: "inset(0 0% 0 0)" }}
              exit={{ opacity: 0, x: -4, clipPath: "inset(0 100% 0 0)" }}
              transition={{ duration: 0.18, ease: [0.22, 1, 0.36, 1] }}
              className="absolute left-0 top-0 z-10 inline-flex h-full w-max items-center gap-3 overflow-hidden whitespace-nowrap rounded-2xl border border-accent/50 bg-white px-4 py-3 dark:bg-neutral-900"
            >
              <button
                type="button"
                onClick={handleToggle}
                aria-label={ariaLabel}
                className="inline-flex items-center gap-4 text-sm font-semibold text-stone-900 dark:text-stone-100"
              >
                <span>{selectedOption?.label ?? value}</span>
                <span className="text-stone-400 dark:text-zinc-500"><ChevronLeft size={16} /></span>
              </button>
              <span className="text-stone-300 dark:text-stone-700">|</span>
              {availableOptions.map((option, index) => {
                const isSelected = option.id === value;
                return (
                  <span key={option.id} className="inline-flex items-center gap-3">
                    <button
                      type="button"
                      onClick={() => handleOptionClick(option.id)}
                      disabled={option.disabled}
                      title={option.disabled ? option.disabledReason : option.label}
                      className={`text-sm font-medium transition-colors disabled:cursor-not-allowed ${
                        option.disabled
                          ? "opacity-40"
                          : isSelected
                            ? "text-accent"
                            : "text-stone-600 hover:text-stone-900 dark:text-zinc-400 dark:hover:text-stone-100"
                      }`}
                    >
                      {option.label}
                    </button>
                    {index < availableOptions.length - 1 && <span className="text-stone-300 dark:text-stone-700">|</span>}
                  </span>
                );
              })}
            </motion.div>
          )}
        </AnimatePresence>

      {/* 禁用提示 - 当选中的选项被禁用时显示 */}
      {selectedOption?.disabled && selectedOption?.disabledReason && (
        <motion.p
          initial={{ opacity: 0, y: -4 }}
          animate={{ opacity: 1, y: 0 }}
          className="mt-2 text-xs font-medium text-danger"
        >
          {selectedOption.disabledReason}
        </motion.p>
      )}
    </div>
  );
}
