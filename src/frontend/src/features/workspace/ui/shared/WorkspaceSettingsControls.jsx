export function WorkspaceSettingRow({ title, description, children }) {
  return (
    <div className="flex flex-col justify-between gap-6 rounded-[1.5rem] border border-stone-100 bg-stone-50/50 p-6 transition-colors dark:border-stone-800/60 dark:bg-stone-800/30 sm:flex-row sm:items-center">
      <div className="max-w-[400px]">
        <strong className="mb-1.5 block text-base font-bold text-stone-900 dark:text-stone-100">{title}</strong>
        <span className="block text-[13px] leading-relaxed text-stone-500 dark:text-stone-400">{description}</span>
      </div>
      <div className="flex shrink-0 items-center justify-end">{children}</div>
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
    <div className="flex rounded-xl bg-stone-100 p-1 dark:bg-stone-800/60" role="group">
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
  placeholder,
  className = "",
  type = "text",
}) {
  return (
    <input
      type={type}
      value={value}
      onChange={(event) => onChange(event.target.value)}
      placeholder={placeholder}
      className={`rounded-xl border border-stone-200 bg-white px-4 py-2.5 text-sm text-stone-900 outline-none focus:border-accent dark:border-stone-700 dark:bg-stone-900 dark:text-stone-100 ${className}`}
    />
  );
}
