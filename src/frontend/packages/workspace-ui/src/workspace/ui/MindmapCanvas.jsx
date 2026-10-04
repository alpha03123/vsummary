import { useEffect, useRef } from "react";
import { Markmap } from "markmap-view";
import * as d3 from "d3";

/**
 * markmap 默认值不适合这里的窄面板场景，统一在这里覆盖：
 *
 * - autoFit: 库默认为 false，导图创建后不会缩放到容器，内容会挤在左上角、
 *   右下留出大片空白。开启后每次渲染自动 fit。
 * - fitRatio: 默认 0.95，配合外层卡片内边距会形成两层留白，收紧到 0.98。
 * - colorFreezeLevel: 默认按完整层级路径取色（如 0.2.1，每层都换色），
 *   导致橙/粉/紫/青混排、颜色无任何含义。截断路径再取色后，
 *   同一分支的子孙节点共色，颜色即"一级分类"。
 *
 *   注意取值是 2 而不是 1：根节点自身占第 0 段（path="0"），
 *   一级分支是 "0.1"、"0.2"…。freeze=1 会把所有一级分支截成同一个 "0"，
 *   结果是整张图只剩一种颜色；freeze=2 才能让每个一级分支各得一个颜色，
 *   且该分支下所有层级保持同色。
 */
export const MARKMAP_OPTIONS = {
  autoFit: true,
  fitRatio: 0.98,
  colorFreezeLevel: 2,
};

export function MindmapCanvas({ root, selectedNodeId, onSelectNode, markmapRef, theme }) {
  const svgRef = useRef(null);
  const mmRef = useRef(null);

  useEffect(() => {
    if (!root || !svgRef.current) {
      mmRef.current?.destroy();
      mmRef.current = null;
      return;
    }

    mmRef.current?.destroy();

    const data = convertToMarkmapNode(root);
    const mm = Markmap.create(svgRef.current, MARKMAP_OPTIONS, data);
    mmRef.current = mm;
    if (markmapRef) markmapRef.current = mm;

    const preventTextSelection = (event) => {
      if (event.target.closest(".markmap-node")) {
        event.preventDefault();
      }
    };
    const selectNode = (nodeElement) => {
      if (!nodeElement || !onSelectNode) return;
      const nodeData = d3.select(nodeElement).datum();
      if (!nodeData) return;
      onSelectNode({
        id: nodeData.payload?.id,
        title: nodeData.content,
        summary: nodeData.payload?.summary,
        start_seconds: nodeData.payload?.startSeconds ?? 0,
        end_seconds: nodeData.payload?.endSeconds ?? 0,
        children: nodeData.children || [],
      });
    };
    svgRef.current.addEventListener("mousedown", preventTextSelection, true);

    const svg = d3.select(svgRef.current);
    svg.on("mouseover.mindmap-hover", (event) => {
      event.target.closest(".markmap-node")?.classList.add("mindmap-hovered");
    });
    svg.on("mouseout.mindmap-hover", (event) => {
      const node = event.target.closest(".markmap-node");
      if (node && !node.contains(event.relatedTarget)) {
        node.classList.remove("mindmap-hovered");
      }
    });
    svg.on("click", (event) => {
      if (event.target instanceof SVGCircleElement) {
        return;
      }
      const target = event.target.closest(".markmap-node");
      if (!target) return;
      event.preventDefault();
      selectNode(target);
    });

    return () => {
      svg.on(".mindmap-hover", null);
      svgRef.current?.removeEventListener("mousedown", preventTextSelection, true);
      mm.destroy();
      mmRef.current = null;
      if (markmapRef) markmapRef.current = null;
    };
  }, [root, markmapRef]);

  useEffect(() => {
    const svg = mmRef.current?.svg?.node();
    if (!svg || !root) return;
    const isDark = resolveDarkTheme(theme);
    if (isDark) {
      svg.classList.add("markmap-dark");
    } else {
      svg.classList.remove("markmap-dark");
    }
    applyMindmapTheme(svg, isDark);
  }, [root, theme]);

  useEffect(() => {
    if (!svgRef.current || !selectedNodeId) return;
    const svg = svgRef.current;
    svg.querySelectorAll(".mindmap-selected").forEach((el) =>
      el.classList.remove("mindmap-selected")
    );
    svg.querySelectorAll("g.markmap-node").forEach((g) => {
      const data = g.__data__;
      if (data?.payload?.id === selectedNodeId) {
        g.classList.add("mindmap-selected");
      }
    });
  }, [selectedNodeId, root]);

  if (!root) {
    return (
      <div className="p-8 text-stone-600 text-sm text-center">
        当前没有导图数据。
      </div>
    );
  }

  return (
    <svg
      ref={svgRef}
      className="mindmap-svg absolute inset-0 w-full h-full"
      style={{ background: "transparent", userSelect: "none", WebkitUserSelect: "none" }}
    />
  );
}

function convertToMarkmapNode(node) {
  return {
    content: node.title,
    payload: {
      id: node.id,
      summary: node.summary,
      startSeconds: node.start_seconds,
      endSeconds: node.end_seconds,
    },
    children: (node.children || []).map(convertToMarkmapNode),
  };
}

function resolveDarkTheme(theme) {
  return theme === "dark" || (theme == null && document.documentElement.classList.contains("dark"));
}

function applyMindmapTheme(svg, isDark) {
  if (!svg.style?.setProperty) return;
  svg.style.setProperty("--markmap-text-color", isDark ? "#f4f4f5" : "#18181b");
  svg.style.setProperty("--markmap-code-color", isDark ? "#e4e4e7" : "#3f3f46");
  svg.style.setProperty("--markmap-code-bg", isDark ? "#27272a" : "#f4f4f5");
  svg.style.setProperty("--markmap-circle-open-bg", isDark ? "#52525b" : "#fff");
}
