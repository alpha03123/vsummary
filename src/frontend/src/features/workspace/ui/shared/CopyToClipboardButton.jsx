import { useEffect, useRef, useState } from "react";
import { Check, Copy } from "lucide-react";

import { copyText } from "./clipboard";

const REVERT_DELAY_MS = 1600;

export function CopyToClipboardButton({
  text,
  label = "复制",
  copiedLabel = "已复制",
  iconSize = 14,
  className = "",
}) {
  const [copied, setCopied] = useState(false);
  const timeoutRef = useRef(null);

  useEffect(
    () => () => {
      if (timeoutRef.current) window.clearTimeout(timeoutRef.current);
    },
    [],
  );

  async function handleClick() {
    try {
      await copyText(text);
      setCopied(true);
      if (timeoutRef.current) window.clearTimeout(timeoutRef.current);
      timeoutRef.current = window.setTimeout(() => setCopied(false), REVERT_DELAY_MS);
    } catch {
      // copyText rejected: leave button in initial state, no toast/log
    }
  }

  const Icon = copied ? Check : Copy;
  const displayLabel = copied ? copiedLabel : label;

  return (
    <button
      type="button"
      onClick={handleClick}
      aria-label={displayLabel}
      title={displayLabel}
      className={`inline-flex items-center gap-1.5 rounded-xl px-2.5 py-1.5 text-xs font-semibold transition ${
        copied
          ? "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300"
          : "bg-stone-100 text-stone-600 hover:bg-stone-200 dark:bg-stone-800 dark:text-stone-300 dark:hover:bg-stone-700"
      } ${className}`}
    >
      <Icon size={iconSize} strokeWidth={2.2} aria-hidden="true" />
      <span aria-live="polite">{displayLabel}</span>
    </button>
  );
}