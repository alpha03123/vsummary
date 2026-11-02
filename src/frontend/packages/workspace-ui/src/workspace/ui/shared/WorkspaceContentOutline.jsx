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
      <div className="flex flex-col @[650px]:ml-auto @[650px]:grid @[650px]:max-w-[calc(48rem+10rem+10rem)] @[650px]:grid-cols-[minmax(0,48rem)_10rem] @[650px]:items-start @[650px]:gap-x-[clamp(2.5rem,8vw,10rem)] @[760px]:max-w-[calc(48rem+11rem+10rem)] @[760px]:grid-cols-[minmax(0,48rem)_11rem]">
        {/* The bar must match the button it wraps: stone-950 behind a stone-900 button showed the
            wrapper's padding as a black frame around the outline on phones. */}
        <div className="sticky top-0 z-20 mb-4 bg-surface/95 py-2 backdrop-blur @[650px]:hidden">
          <button
            type="button"
            onClick={() => setOpen((current) => !current)}
            aria-label="打开正文目录"
            aria-expanded={open}
            className="flex h-9 w-full items-center gap-2 rounded-xl border border-line bg-surface px-3 text-left text-sm font-medium text-body shadow-sm transition-colors hover:border-accent/40"
          >
            <List size={15} className="shrink-0 text-faint" aria-hidden="true" />
            <span className="truncate">{activeItem?.label ?? label}</span>
            <ChevronDown size={15} className={`ml-auto shrink-0 text-faint transition-transform ${open ? "rotate-180" : ""}`} aria-hidden="true" />
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

        <aside className="hidden @[650px]:sticky @[650px]:top-0 @[650px]:col-start-2 @[650px]:row-start-1 @[650px]:block @[650px]:max-h-[calc(100dvh-10rem)] @[650px]:overflow-y-auto @[650px]:pr-1">
          <OutlineList label={label} items={items} activeItemId={activeItemId} onSelect={selectItem} />
        </aside>

        <div className="min-w-0 max-w-3xl @[650px]:col-start-1 @[650px]:row-start-1">{children}</div>
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
    <nav aria-label={label ?? "正文目录"} className="rounded-2xl border border-line/80 bg-surface/70 p-2">
      {label ? <p className="px-2 py-1 text-xs font-bold uppercase tracking-widest text-faint">{label}</p> : null}
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
                  : "text-subtle hover:bg-soft hover:text-strong"
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
