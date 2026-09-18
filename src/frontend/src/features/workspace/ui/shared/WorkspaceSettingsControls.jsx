import { useState, useRef, useEffect } from "react";
import { ChevronDown, Check } from "lucide-react";
import { useOutsidePointerUp } from "../../../../shared/lib/useOutsidePointerUp";

export function WorkspaceProviderSelect({
  value,
  onChange,
  options,
  className = "",
  disabled = false,
  hideGroupLabels = false,
  ariaLabel,
  optionLayout = "vertical",
  menuClassName = "",
  align = "start",
  triggerVariant = "default",
  leading = null,
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef(null);
  const selected = options.find((o) => o.id === value);

  // Build ordered group list, preserving first-seen order
  const groups = [];
  const groupMap = {};
  for (const opt of options) {
    const g = opt.group ?? "其他";
    if (!groupMap[g]) { groupMap[g] = []; groups.push(g); }
    groupMap[g].push(opt);
  }

  useOutsidePointerUp(open, [ref], () => setOpen(false));

  function renderOption(option, horizontal = false) {
    const active = option.id === value;
    return (
      <button
        key={option.id}
        type="button"
        role="option"
        aria-selected={active}
        disabled={option.disabled}
        title={option.disabled ? option.disabledReason || option.label : undefined}
        onClick={() => { onChange(option.id); setOpen(false); }}
        className={horizontal
          ? `flex min-w-0 flex-col items-center justify-center rounded-xl px-3 py-2.5 text-center transition-colors hover:bg-stone-100/80 disabled:cursor-not-allowed disabled:opacity-45 dark:hover:bg-stone-800/70 ${active ? "bg-accent/10 text-accent dark:bg-accent/15" : "text-stone-900 dark:text-stone-100"}`
          : `group flex w-full items-center gap-2.5 rounded-xl px-2.5 py-2 text-left transition-colors hover:bg-stone-100/80 disabled:cursor-not-allowed disabled:opacity-45 dark:hover:bg-stone-800/70 ${active ? "bg-accent/10 dark:bg-accent/15" : ""}`}
      >
        <span className="min-w-0 flex-1">
          <span className={`block truncate text-sm ${active ? "font-semibold text-accent" : "font-medium text-stone-700 dark:text-stone-200"}`}>
            {option.label}
          </span>
          {option.description && (
            <span className={`mt-0.5 block text-xs leading-snug text-stone-500 dark:text-stone-500 ${horizontal ? "text-center" : ""}`}>
              {option.description}
            </span>
          )}
        </span>
        <Check
          size={15}
          strokeWidth={2.5}
          aria-hidden="true"
          className={`shrink-0 text-accent transition-opacity ${active ? "opacity-100" : "opacity-0"}`}
        />
      </button>
    );
  }

  return (
    <div ref={ref} className={`relative ${className}`}>
      <button
        type="button"
        aria-label={ariaLabel}
        aria-haspopup="listbox"
        aria-expanded={open}
        disabled={disabled}
        onClick={() => setOpen((v) => !v)}
        className={
          triggerVariant === "bare"
            ? `flex h-full w-full items-center justify-between gap-2 bg-transparent px-3 py-2 text-left text-sm text-stone-900 outline-none transition-colors disabled:cursor-not-allowed disabled:opacity-50 dark:text-stone-100 ${open ? "text-accent" : "hover:bg-stone-100/80 dark:hover:bg-stone-800/70"}`
            : `flex w-full items-center justify-between gap-2 rounded-xl border bg-white px-3.5 py-2 text-left text-sm text-stone-900 outline-none transition-colors disabled:cursor-not-allowed disabled:opacity-50 dark:bg-stone-900 dark:text-stone-100 ${
                open
                  ? "border-accent/40 ring-2 ring-accent/20 dark:border-accent/40"
                  : "border-stone-200 hover:border-stone-300 dark:border-stone-700 dark:hover:border-stone-600"
              }`
        }
      >
        <span className="flex min-w-0 flex-1 items-center gap-2">
          {leading ? <span className="shrink-0 text-stone-400 dark:text-stone-500">{leading}</span> : null}
          <span className="truncate font-medium">{selected?.label ?? value}</span>
        </span>
        <ChevronDown
          size={15}
          className={`shrink-0 text-stone-400 transition-transform duration-200 ${open ? "rotate-180 text-accent" : ""}`}
        />
      </button>

      {open && (
        <div
          role="listbox"
          className={`absolute top-full z-50 mt-2 min-w-full max-w-[min(20rem,calc(100vw-2rem))] overflow-y-auto rounded-2xl border border-stone-200/90 bg-white p-1.5 shadow-[0_8px_28px_-6px_rgba(15,23,42,0.18),0_2px_6px_-2px_rgba(15,23,42,0.08)] motion-fade-scale dark:border-stone-700 dark:bg-neutral-900 dark:shadow-[0_8px_28px_-6px_rgba(0,0,0,0.6)] ${
            align === "end" ? "right-0" : "left-0"
          } max-h-80 ${menuClassName}`}
        >
          {optionLayout === "horizontal" ? (
            <div className="grid grid-cols-3 gap-1">
              {options.map((option) => renderOption(option, true))}
            </div>
          ) : groups.map((group, gi) => (
            <div key={group}>
              {gi > 0 && <div className="mx-1.5 my-1 border-t border-stone-100 dark:border-stone-800" />}
              {!hideGroupLabels ? (
                <div className="px-2.5 pb-1 pt-2 text-[10px] font-bold uppercase tracking-widest text-stone-400 dark:text-stone-500">
                  {group}
                </div>
              ) : null}
              {groupMap[group].map((option) => renderOption(option))}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export function WorkspaceSettingRow({ title, description, children, contentClassName = "" }) {
  const contentLayoutClassName = contentClassName || "2xl:w-auto 2xl:min-w-0";

  return (
    <div className="flex flex-col justify-between gap-6 rounded-[1.5rem] border border-stone-100 bg-stone-50/50 p-6 transition-colors dark:border-stone-800/60 dark:bg-stone-800/30 2xl:flex-row 2xl:items-center min-w-0">
      <div className="min-w-0 max-w-none 2xl:w-[260px] 2xl:shrink-0">
        <strong className="mb-1.5 block text-base font-bold text-stone-900 dark:text-stone-100">{title}</strong>
        <span className="block text-[13px] leading-relaxed text-stone-600 dark:text-stone-400">{description}</span>
      </div>
      <div className={`flex min-w-0 w-full items-center justify-end ${contentLayoutClassName}`}>{children}</div>
    </div>
  );
}

export function WorkspaceAdvancedSettings({ children, defaultOpen = false }) {
  const [open, setOpen] = useState(defaultOpen);

  return (
    <section className="rounded-[1.5rem] border border-stone-200/80 bg-white/60 p-2 dark:border-stone-700/70 dark:bg-stone-900/40">
      <button
        type="button"
        aria-expanded={open}
        onClick={() => setOpen((current) => !current)}
        className="flex w-full items-center justify-between gap-4 rounded-[1.15rem] px-4 py-3 text-left transition-colors hover:bg-stone-100/80 dark:hover:bg-stone-800/70"
      >
        <span>
          <strong className="block text-sm font-bold text-stone-900 dark:text-stone-100">高级设置</strong>
          <span className="mt-0.5 block text-xs leading-relaxed text-stone-600 dark:text-stone-400">进一步控制性能与成本，不确定时保持默认即可。</span>
        </span>
        <ChevronDown size={18} className={`shrink-0 text-stone-500 transition-transform duration-200 ${open ? "rotate-180" : ""}`} />
      </button>
      {open ? <div className="space-y-3 px-1 pb-1 pt-2">{children}</div> : null}
    </section>
  );
}

export function WorkspaceToggleSwitch({ checked, disabled = false, onChange, ariaLabel }) {
  return (
    <button
      type="button"
      disabled={disabled}
      className={`relative inline-flex h-7 w-12 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none focus-visible:ring-2 focus-visible:ring-accent/50 focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50 ${
        checked ? "bg-accent" : "bg-stone-300 dark:bg-stone-600"
      }`}
      onClick={onChange}
      aria-label={ariaLabel}
      aria-pressed={checked}
    >
      <span
        className={`pointer-events-none inline-block h-6 w-6 transform rounded-full bg-white shadow-sm ring-0 transition duration-200 ease-in-out ${
          checked ? "translate-x-5" : "translate-x-0"
        }`}
      />
    </button>
  );
}

export function WorkspaceSegmentedControl({ value, options, onChange, className = "" }) {
  const columnsClass =
    options.length === 2
      ? "grid-cols-2"
      : options.length === 3
      ? "grid-cols-3"
      : "grid-cols-4";
  return (
    <div className={`grid w-full min-w-0 ${columnsClass} rounded-xl bg-stone-100 p-1 dark:bg-stone-800/60 ${className}`} role="group">
      {options.map((option) => {
        const active = option.id === value;
        return (
          <button
            key={option.id}
            type="button"
            disabled={option.disabled}
            title={option.disabled ? option.disabledReason || option.label : option.label}
            className={`min-w-0 rounded-lg px-2 py-1.5 text-xs sm:text-xs md:text-sm font-medium leading-5 transition-colors disabled:cursor-not-allowed disabled:opacity-45 text-center ${
              active
                ? "bg-white text-stone-900 shadow-sm dark:bg-stone-700 dark:text-stone-100"
                : "text-stone-600 hover:text-stone-700 dark:text-stone-400 dark:hover:text-stone-200"
            }`}
            onClick={() => onChange(option.id)}
          >
            <span className="block truncate">{option.label}</span>
          </button>
        );
      })}
    </div>
  );
}

/**
 * Multi-toggle pill group for settings.
 *
 * Rendered as a segmented rail (same surface, padding and radius as
 * `WorkspaceSegmentedControl`) so it reads as the multi-select sibling of the
 * single-choice control instead of a row of loose checkboxes. Selection is
 * carried by the raised white chip + accent text, and the check icon is the
 * only thing that changes between states — no layout shift on toggle.
 */
export function WorkspaceMultiSelect({ values, options, onChange, className = "" }) {
  const selectedValues = Array.isArray(values) ? values : [];

  function toggle(optionId) {
    onChange(selectedValues.includes(optionId)
      ? selectedValues.filter((value) => value !== optionId)
      : [...selectedValues, optionId]);
  }

  return (
    <div
      className={`flex w-full min-w-0 flex-wrap items-center gap-1 rounded-xl bg-stone-100 p-1 dark:bg-stone-800/60 ${className}`}
      role="group"
      aria-label="多选项"
    >
      {options.map((option) => {
        const selected = selectedValues.includes(option.id);
        return (
          <button
            key={option.id}
            type="button"
            aria-pressed={selected}
            title={option.label}
            onClick={() => toggle(option.id)}
            className={`inline-flex min-w-0 flex-1 items-center justify-center gap-1.5 whitespace-nowrap rounded-lg px-2.5 py-1.5 text-xs font-medium leading-5 transition-colors sm:text-sm ${
              selected
                ? "bg-white text-stone-900 shadow-sm dark:bg-stone-700 dark:text-stone-100"
                : "text-stone-600 hover:text-stone-700 dark:text-stone-400 dark:hover:text-stone-200"
            }`}
          >
            <Check
              size={13}
              strokeWidth={3}
              aria-hidden="true"
              className={`shrink-0 transition-opacity ${selected ? "opacity-100 text-accent" : "opacity-0"}`}
            />
            <span className="truncate">{option.label}</span>
          </button>
        );
      })}
    </div>
  );
}

export function WorkspaceTextInput({
  value,
  onChange,
  onBlur,
  onKeyDown,
  placeholder,
  className = "",
  type = "text",
}) {
  return (
    <input
      type={type}
      value={value}
      onChange={(event) => onChange(event.target.value)}
      onBlur={onBlur}
      onKeyDown={onKeyDown}
      placeholder={placeholder}
      className={`max-w-full rounded-xl border border-stone-200 bg-white px-4 py-2.5 text-sm text-stone-900 outline-none focus:border-accent dark:border-stone-700 dark:bg-stone-900 dark:text-stone-100 ${className}`}
    />
  );
}

export function WorkspaceSelect({
  value,
  onChange,
  options,
  className = "",
  disabled = false,
}) {
  return (
    <select
      value={value}
      onChange={(event) => onChange(event.target.value)}
      disabled={disabled}
      className={`max-w-full rounded-xl border border-stone-200 bg-white px-4 py-2.5 text-sm text-stone-900 outline-none focus:border-accent disabled:cursor-not-allowed disabled:opacity-50 dark:border-stone-700 dark:bg-stone-900 dark:text-stone-100 ${className}`}
    >
      {options.map((option) => (
        <option key={option.id} value={option.id} disabled={option.disabled}>
          {option.label}
        </option>
      ))}
    </select>
  );
}
