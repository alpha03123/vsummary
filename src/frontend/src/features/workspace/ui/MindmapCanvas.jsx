import { useRef, useState } from "react";
import { RotateCcw } from "lucide-react";

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

  if (!root) {
    return <div className="empty-note">当前没有导图数据。</div>;
  }

  function renderNode(node, depth) {
    const hasChildren = node.children && node.children.length > 0;
    const isRoot = depth === 0;

    return (
      <li key={node.id}>
        <div className="css-tree-node-wrapper">
          <button
            type="button"
            className={`mindmap-node depth-${depth}${node.id === selectedNodeId ? " is-active" : ""}`}
            onClick={() => onSelectNode(node)}
          >
            <span className="mindmap-label">{node.title}</span>
            {!isRoot && hasChildren ? <span className="mindmap-badge">{node.children.length}</span> : null}
          </button>
        </div>
        {hasChildren ? (
          <ul>
            {node.children.map((child) => renderNode(child, depth + 1))}
          </ul>
        ) : null}
      </li>
    );
  }

  function resetView() {
    setView(INITIAL_VIEW);
  }

  function handleWheel(event) {
    event.preventDefault();
    const viewport = viewportRef.current;
    if (!viewport) {
      return;
    }

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
    if (event.button !== 0 || event.target.closest(".mindmap-node")) {
      return;
    }

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
    if (!dragStateRef.current.active) {
      return;
    }

    const deltaX = event.clientX - dragStateRef.current.startX;
    const deltaY = event.clientY - dragStateRef.current.startY;
    setView((currentView) => ({
      ...currentView,
      x: dragStateRef.current.originX + deltaX,
      y: dragStateRef.current.originY + deltaY,
    }));
  }

  function handlePointerUp(event) {
    if (!dragStateRef.current.active) {
      return;
    }

    if (event.currentTarget.hasPointerCapture?.(dragStateRef.current.pointerId)) {
      event.currentTarget.releasePointerCapture(dragStateRef.current.pointerId);
    }
    dragStateRef.current.active = false;
    setIsPanning(false);
  }

  return (
    <div
      ref={viewportRef}
      className={`mindmap-scroll${isPanning ? " is-panning" : ""}`}
      onDoubleClick={resetView}
      onWheel={handleWheel}
      onPointerDown={handlePointerDown}
      onPointerMove={handlePointerMove}
      onPointerUp={handlePointerUp}
      onPointerCancel={handlePointerUp}
    >
      <div className="mindmap-hud">
        <button type="button" className="mindmap-reset" onClick={resetView}>
          <RotateCcw size={14} strokeWidth={2.1} />
          复位
        </button>
      </div>
      <div
        className="mindmap-canvas"
        style={{
          transform: `translate3d(${view.x}px, ${view.y}px, 0) scale(${view.scale})`,
        }}
      >
        <div className="css-tree">
        <ul>{renderNode(root, 0)}</ul>
        </div>
      </div>
    </div>
  );
}

function clamp(value, min, max) {
  return Math.min(max, Math.max(min, value));
}
