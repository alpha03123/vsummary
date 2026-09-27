import { useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { ChevronDown, List } from "lucide-react";

export function WorkspaceContentOutline({ label = "正文目录", items = [], activeItemId = null, onSelect, children }) {
  const [open, setOpen] = useState(false);
  const activeItem = items.find((item) => item.id === activeItemId) ?? items[0] ?? null;

  if (!items.length) {
    return children;
  }

  function selectItem(item) {
    onSelect?.(item.id);
    setOpen(false);
  }

  return (
    <div className="@container w-full">
      <div className="flex flex-col @[550px]:ml-auto @[550px]:grid @[550px]:max-w-[calc(48rem+10rem+10rem)] @[550px]:grid-cols-[minmax(0,48rem)_10rem] @[550px]:items-start @[550px]:gap-x-[clamp(2.5rem,8vw,10rem)] @[760px]:max-w-[calc(48rem+11rem+10rem)] @[760px]:grid-cols-[minmax(0,48rem)_11rem]">
        <div className="sticky top-0 z-20 mb-4 bg-white/95 py-2 backdrop-blur @[550px]:hidden dark:bg-stone-950/95">
          <button
            type="button"
            onClick={() => setOpen((current) => !current)}
            aria-label="打开正文目录"
            aria-expanded={open}
            className="flex h-9 w-full items-center gap-2 rounded-xl border border-stone-200 bg-white px-3 text-left text-sm font-medium text-stone-700 shadow-sm transition-colors hover:border-accent/40 dark:border-stone-700 dark:bg-stone-900 dark:text-stone-200"
          >
            <List size={15} className="shrink-0 text-stone-400" aria-hidden="true" />
            <span className="truncate">{activeItem?.label ?? label}</span>
            <ChevronDown size={15} className={`ml-auto shrink-0 text-stone-400 transition-transform ${open ? "rotate-180" : ""}`} aria-hidden="true" />
          </button>
          <AnimatePresence initial={false}>
            {open ? (
              <motion.div
                initial={{ opacity: 0, y: -6, scale: 0.98 }}
                animate={{ opacity: 1, y: 0, scale: 1 }}
                exit={{ opacity: 0, y: -6, scale: 0.98 }}
                transition={{ duration: 0.16, ease: "easeOut" }}
                className="workspace-elevated-panel absolute inset-x-0 top-full z-30 mt-2 max-h-72 overflow-y-auto rounded-2xl border p-2 shadow-xl"
              >
                <OutlineList items={items} activeItemId={activeItemId} onSelect={selectItem} />
              </motion.div>
            ) : null}
          </AnimatePresence>
        </div>

        <aside className="hidden @[550px]:sticky @[550px]:top-0 @[550px]:col-start-2 @[550px]:row-start-1 @[550px]:block @[550px]:max-h-[calc(100vh-10rem)] @[550px]:overflow-y-auto @[550px]:pr-1">
          <OutlineList label={label} items={items} activeItemId={activeItemId} onSelect={selectItem} />
        </aside>

        <div className="min-w-0 max-w-3xl @[550px]:col-start-1 @[550px]:row-start-1">{children}</div>
      </div>
    </div>
  );
}

export function findContentScrollContainer(element) {
  if (typeof window === "undefined") {
    return null;
  }
  let current = element?.parentElement ?? null;
  while (current) {
    const overflowY = window.getComputedStyle(current).overflowY;
    if (overflowY === "auto" || overflowY === "scroll" || overflowY === "overlay") {
      return current;
    }
    current = current.parentElement;
  }
  return null;
}

function OutlineList({ label, items, activeItemId, onSelect }) {
  return (
    <nav aria-label={label ?? "正文目录"} className="rounded-2xl border border-stone-200/80 bg-white/70 p-2 dark:border-stone-800 dark:bg-stone-950/50">
      {label ? <p className="px-2 py-1 text-[10px] font-bold uppercase tracking-widest text-stone-400 dark:text-stone-500">{label}</p> : null}
      <div className="mt-1 flex flex-col gap-1">
        {items.map((item) => {
          const active = item.id === activeItemId;
          return (
            <button
              key={item.id}
              type="button"
              onClick={() => onSelect(item)}
              title={item.label}
              className={`flex w-full items-center rounded-xl px-2 py-2 text-left text-xs transition-colors ${
                active
                  ? "bg-accent/10 font-semibold text-accent dark:bg-accent/15"
                  : "text-stone-600 hover:bg-stone-100 hover:text-stone-900 dark:text-stone-400 dark:hover:bg-stone-800 dark:hover:text-stone-100"
              } ${item.depth === 3 ? "pl-5" : ""}`}
            >
              <span className="truncate">{item.label}</span>
            </button>
          );
        })}
      </div>
    </nav>
  );
}
