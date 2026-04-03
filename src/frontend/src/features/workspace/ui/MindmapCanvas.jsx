import { useRef, useState, useEffect } from "react";

const MIN_SCALE = 0.55;
const MAX_SCALE = 2.4;
const INITIAL_VIEW = {
  x: 28,
  y: 20,
  scale: 1,
};

export function MindmapCanvas({ root, selectedNodeId, onSelectNode }) {
  const viewportRef = useRef(null);
  const dragStateRef = useRef({
    active: false,
    pointerId: null,
    originX: 0,
    originY: 0,
    startX: 0,
    startY: 0,
  });
  const [view, setView] = useState(INITIAL_VIEW);
  const [isPanning, setIsPanning] = useState(false);

  // Reset view when a new video is loaded (root changes)
  useEffect(() => {
    setView(INITIAL_VIEW);
  }, [root]);

  if (!root) {
    return <div className="p-8 text-stone-500 text-sm text-center">当前没有导图数据。</div>;
  }

  function renderNode(node, depth) {
    const hasChildren = node.children && node.children.length > 0;
    const isRoot = depth === 0;

    return (
      <li key={node.id}>
        <div className="css-tree-node-wrapper">
          <button
            type="button"
            className={`mindmap-node depth-${depth} group`}
            onClick={() => onSelectNode(node)}
          >
            <span className={`mindmap-label inline-flex items-center min-h-[36px] px-4 py-1.5 rounded-full text-sm border transition-all duration-200 outline-none
              ${node.id === selectedNodeId
                ? "bg-white dark:bg-[#101214] border-[#0070f3] text-stone-900 dark:text-white shadow-md ring-2 ring-[#0070f3]/20 z-10 font-bold"
                : isRoot
                  ? "bg-stone-900 dark:bg-[#111111] border-stone-800 dark:border-white/10 text-white shadow-sm font-bold"
                  : "bg-white/80 dark:bg-[#161616] border-stone-200 dark:border-white/10 text-stone-700 dark:text-zinc-200 hover:bg-white dark:hover:bg-[#1c1c1c] hover:border-stone-300 dark:hover:border-white/16 hover:shadow-sm"
              }`}
            >
              {node.title}
            </span>
            {!isRoot && hasChildren && (
              <span className="mindmap-badge ml-2 flex items-center justify-center w-6 h-6 rounded-full bg-stone-100 dark:bg-[#111111] text-stone-700 dark:text-white font-bold text-xs shadow-sm border border-stone-200 dark:border-white/10">
                {node.children.length}
              </span>
            )}
          </button>
        </div>
        {hasChildren ? <ul>{node.children.map((child) => renderNode(child, depth + 1))}</ul> : null}
      </li>
    );
  }

  function resetView() {
    setView(INITIAL_VIEW);
  }

  function handleWheel(event) {
    event.preventDefault();
    const viewport = viewportRef.current;
    if (!viewport) return;

    const rect = viewport.getBoundingClientRect();
    const cursorX = event.clientX - rect.left;
    const cursorY = event.clientY - rect.top;
    const nextScale = clamp(view.scale * Math.exp(-event.deltaY * 0.0015), MIN_SCALE, MAX_SCALE);
    const worldX = (cursorX - view.x) / view.scale;
    const worldY = (cursorY - view.y) / view.scale;

    setView({
      scale: nextScale,
      x: cursorX - worldX * nextScale,
      y: cursorY - worldY * nextScale,
    });
  }

  function handlePointerDown(event) {
    if (event.button !== 0 || event.target.closest(".mindmap-node")) return;
    event.preventDefault();

    dragStateRef.current = {
      active: true,
      pointerId: event.pointerId,
      originX: view.x,
      originY: view.y,
      startX: event.clientX,
      startY: event.clientY,
    };

    event.currentTarget.setPointerCapture(event.pointerId);
    setIsPanning(true);
  }

  function handlePointerMove(event) {
    if (!dragStateRef.current.active) return;
    const deltaX = event.clientX - dragStateRef.current.startX;
    const deltaY = event.clientY - dragStateRef.current.startY;
    setView((currentView) => ({
      ...currentView,
      x: dragStateRef.current.originX + deltaX,
      y: dragStateRef.current.originY + deltaY,
    }));
  }

  function handlePointerUp(event) {
    if (!dragStateRef.current.active) return;
    if (event.currentTarget.hasPointerCapture?.(dragStateRef.current.pointerId)) {
      event.currentTarget.releasePointerCapture(dragStateRef.current.pointerId);
    }
    dragStateRef.current.active = false;
    setIsPanning(false);
  }

  return (
    <div
      ref={viewportRef}
      className={`absolute inset-0 overflow-hidden w-full h-full select-none bg-stone-50/50 dark:bg-[#0f0f10] rounded-b-3xl ${isPanning ? "cursor-grabbing" : "cursor-grab"}`}
      onDoubleClick={resetView}
      onWheel={handleWheel}
      onPointerDown={handlePointerDown}
      onPointerMove={handlePointerMove}
      onPointerUp={handlePointerUp}
      onPointerCancel={handlePointerUp}
      onDragStart={(event) => event.preventDefault()}
      style={{ touchAction: "none" }}
    >
      <div
        className="absolute top-0 left-0 origin-top-left will-change-transform isolate"
        style={{
          transform: `translate3d(${view.x}px, ${view.y}px, 0) scale(${view.scale})`,
        }}
      >
        <div className="css-tree p-10 pt-16">
          <ul>{renderNode(root, 0)}</ul>
        </div>
      </div>
    </div>
  );
}

function clamp(value, min, max) {
  return Math.min(max, Math.max(min, value));
}
