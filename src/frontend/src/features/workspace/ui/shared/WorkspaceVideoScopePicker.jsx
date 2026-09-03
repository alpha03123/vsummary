import { useEffect, useId, useMemo, useRef, useState } from "react";
import { Check, ChevronDown, ListFilter, Search } from "lucide-react";
import { useOutsidePointerUp } from "../../../../shared/lib/useOutsidePointerUp";

const SEARCHABLE_THRESHOLD = 8;
const ALL_OPTION_LABEL = "全部视频 AI 概况";

/**
 * Scope picker for series-level overview filtering.
 * Always renders a styled custom listbox; adds a search input for large lists.
 */
export function WorkspaceVideoScopePicker({ videos, value, onChange, label = "查看范围" }) {
  const searchable = videos.length > SEARCHABLE_THRESHOLD;

  return (
    <div className="flex min-w-0 items-center gap-2.5">
      <span className="flex shrink-0 items-center gap-1.5 text-xs font-medium text-stone-500 dark:text-stone-400">
        <ListFilter size={14} aria-hidden="true" />
        {label}
      </span>
      <ScopePicker videos={videos} value={value} onChange={onChange} searchable={searchable} />
    </div>
  );
}

function ScopePicker({ videos, value, onChange, searchable }) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [activeIndex, setActiveIndex] = useState(0);
  const containerRef = useRef(null);
  const inputRef = useRef(null);
  const listboxId = useId();

  const options = useMemo(
    () => [{ id: "all", title: ALL_OPTION_LABEL }, ...videos],
    [videos],
  );

  const filtered = useMemo(() => {
    if (!searchable) return options;
    const needle = query.trim().toLowerCase();
    if (!needle) return options;
    return options.filter((option) => option.title.toLowerCase().includes(needle));
  }, [options, query, searchable]);

  const selectedLabel = options.find((o) => o.id === value)?.title ?? ALL_OPTION_LABEL;

  useEffect(() => {
    setActiveIndex(0);
  }, [query]);

  useEffect(() => {
    if (open && searchable) {
      inputRef.current?.focus();
    }
    if (!open) {
      setQuery("");
    }
  }, [open, searchable]);

  useOutsidePointerUp(open, [containerRef], () => setOpen(false));

  function commit(option) {
    onChange(option.id);
    setOpen(false);
  }

  function handleKeyDown(event) {
    if (event.key === "Escape") {
      setOpen(false);
      return;
    }
    if (event.key === "ArrowDown") {
      event.preventDefault();
      if (!open) {
        setOpen(true);
        return;
      }
      setActiveIndex((index) => Math.min(index + 1, filtered.length - 1));
      return;
    }
    if (event.key === "ArrowUp") {
      event.preventDefault();
      setActiveIndex((index) => Math.max(index - 1, 0));
      return;
    }
    if (event.key === "Enter") {
      event.preventDefault();
      const option = filtered[activeIndex];
      if (option) commit(option);
    }
  }

  return (
    <div ref={containerRef} className="relative">
      <button
        type="button"
        aria-label="选择视频概况"
        aria-haspopup="listbox"
        aria-expanded={open}
        onKeyDown={handleKeyDown}
        onClick={() => setOpen((current) => !current)}
        className="flex h-9 items-center gap-2 rounded-xl border border-stone-200/80 bg-white/90 px-3 text-sm font-medium text-stone-700 shadow-sm transition-colors hover:border-stone-300 hover:bg-white dark:border-stone-700/80 dark:bg-stone-900/80 dark:text-stone-200 dark:hover:border-stone-600 dark:hover:bg-stone-900"
      >
        <span className="max-w-[220px] truncate">{selectedLabel}</span>
        <ChevronDown
          size={14}
          className={`shrink-0 text-stone-400 transition-transform dark:text-stone-500 ${open ? "rotate-180" : ""}`}
          aria-hidden="true"
        />
      </button>

      {open ? (
        <div className="workspace-elevated-panel absolute left-0 z-30 mt-1.5 w-max min-w-full max-w-[min(20rem,calc(100vw-3rem))] overflow-hidden rounded-xl border shadow-lg">
          {searchable ? (
            <div className="flex items-center gap-2 border-b border-stone-200/80 px-3 py-2 dark:border-white/5">
              <Search size={13} className="shrink-0 text-stone-400 dark:text-stone-500" aria-hidden="true" />
              <input
                ref={inputRef}
                type="text"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="搜索视频标题"
                aria-label="搜索视频标题"
                aria-controls={listboxId}
                className="w-full bg-transparent text-sm text-stone-800 placeholder:text-stone-400 focus:outline-none dark:text-stone-100 dark:placeholder:text-stone-500"
              />
            </div>
          ) : null}
          <ul id={listboxId} role="listbox" className="max-h-60 overflow-y-auto p-1">
            {filtered.length === 0 ? (
              <li className="px-3 py-6 text-center text-sm text-stone-500 dark:text-stone-400">
                没有匹配的视频
              </li>
            ) : (
              filtered.map((option, index) => {
                const selected = option.id === value;
                return (
                  <li key={option.id}>
                    <button
                      type="button"
                      role="option"
                      aria-selected={selected}
                      onClick={() => commit(option)}
                      onMouseEnter={() => setActiveIndex(index)}
                      className={`flex w-full items-center gap-2 rounded-lg px-3 py-2 text-left text-sm transition-colors ${
                        index === activeIndex ? "bg-stone-100 dark:bg-stone-800" : ""
                      } ${selected ? "font-semibold text-stone-900 dark:text-stone-100" : "text-stone-700 dark:text-stone-300"}`}
                    >
                      <Check
                        size={13}
                        className={`shrink-0 text-accent ${selected ? "" : "invisible"}`}
                        aria-hidden="true"
                      />
                      <span className="truncate">{option.title}</span>
                    </button>
                  </li>
                );
              })
            )}
          </ul>
        </div>
      ) : null}
    </div>
  );
}
