import { useState, useRef, useEffect } from "react";
import { ChevronDown, Check } from "lucide-react";

export function WorkspaceProviderSelect({ value, onChange, options, className = "" }) {
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

  useEffect(() => {
    function onOutside(e) {
      if (ref.current && !ref.current.contains(e.target)) setOpen(false);
    }
    document.addEventListener("mousedown", onOutside);
    return () => document.removeEventListener("mousedown", onOutside);
  }, []);

  return (
    <div ref={ref} className={`relative ${className}`}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center justify-between gap-2 rounded-xl border border-stone-200 bg-white px-4 py-2.5 text-left text-sm text-stone-900 outline-none transition-colors hover:border-accent/50 focus:border-accent dark:border-stone-700 dark:bg-stone-900 dark:text-stone-100"
      >
        <span className="truncate font-medium">{selected?.label ?? value}</span>
        <ChevronDown size={15} className={`shrink-0 text-stone-400 transition-transform ${open ? "rotate-180" : ""}`} />
      </button>

      {open && (
        <div className="absolute left-0 right-0 top-full z-50 mt-1.5 max-h-80 overflow-y-auto rounded-xl border border-stone-200 bg-white shadow-xl dark:border-stone-700 dark:bg-stone-900">
          {groups.map((group, gi) => (
            <div key={group}>
              {gi > 0 && <div className="mx-3 border-t border-stone-100 dark:border-stone-800" />}
              <div className="px-4 pb-1 pt-3 text-[10px] font-bold uppercase tracking-widest text-stone-400 dark:text-stone-500">
                {group}
              </div>
              {groupMap[group].map((option) => {
                const active = option.id === value;
                return (
                  <button
                    key={option.id}
                    type="button"
                    onClick={() => { onChange(option.id); setOpen(false); }}
                    className={`flex w-full items-start gap-3 px-4 py-2.5 text-left transition-colors hover:bg-stone-50 dark:hover:bg-stone-800/60 ${active ? "bg-accent/5 dark:bg-accent/10" : ""}`}
                  >
                    <div className="min-w-0 flex-1">
                      <div className={`text-sm font-semibold ${active ? "text-accent" : "text-stone-900 dark:text-stone-100"}`}>
                        {option.label}
                      </div>
                      {option.description && (
                        <div className="mt-0.5 text-xs leading-snug text-stone-400 dark:text-stone-500">
                          {option.description}
                        </div>
                      )}
                    </div>
                    {active && <Check size={14} className="mt-0.5 shrink-0 text-accent" />}
                  </button>
                );
              })}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export function WorkspaceSettingRow({ title, description, children, contentClassName = "" }) {
  const contentLayoutClassName = contentClassName || "2xl:w-auto 2xl:shrink-0";

  return (
    <div className="flex flex-col justify-between gap-6 rounded-[1.5rem] border border-stone-100 bg-stone-50/50 p-6 transition-colors dark:border-stone-800/60 dark:bg-stone-800/30 2xl:flex-row 2xl:items-center">
      <div className="min-w-0 max-w-none 2xl:w-[260px] 2xl:shrink-0">
        <strong className="mb-1.5 block text-base font-bold text-stone-900 dark:text-stone-100">{title}</strong>
        <span className="block text-[13px] leading-relaxed text-stone-500 dark:text-stone-400">{description}</span>
      </div>
      <div className={`flex min-w-0 w-full items-center justify-end ${contentLayoutClassName}`}>{children}</div>
    </div>
  );
}

export function WorkspaceToggleSwitch({ checked, disabled = false, onChange }) {
  return (
    <button
      type="button"
      disabled={disabled}
      className={`relative inline-flex h-7 w-12 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none focus-visible:ring-2 focus-visible:ring-accent/50 focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50 ${
        checked ? "bg-accent" : "bg-stone-300 dark:bg-stone-600"
      }`}
      onClick={onChange}
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

export function WorkspaceSegmentedControl({ value, options, onChange }) {
  return (
    <div className="flex flex-wrap rounded-xl bg-stone-100 p-1 dark:bg-stone-800/60" role="group">
      {options.map((option) => {
        const active = option.id === value;
        return (
          <button
            key={option.id}
            type="button"
            className={`rounded-lg px-4 py-2 text-sm font-medium transition-colors ${
              active
                ? "bg-white text-stone-900 shadow-sm dark:bg-stone-700 dark:text-stone-100"
                : "text-stone-500 hover:text-stone-700 dark:text-stone-400 dark:hover:text-stone-200"
            }`}
            onClick={() => onChange(option.id)}
          >
            {option.label}
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
}) {
  return (
    <select
      value={value}
      onChange={(event) => onChange(event.target.value)}
      className={`max-w-full rounded-xl border border-stone-200 bg-white px-4 py-2.5 text-sm text-stone-900 outline-none focus:border-accent dark:border-stone-700 dark:bg-stone-900 dark:text-stone-100 ${className}`}
    >
      {options.map((option) => (
        <option key={option.id} value={option.id}>
          {option.label}
        </option>
      ))}
    </select>
  );
}
