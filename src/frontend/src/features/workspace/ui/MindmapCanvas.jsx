import { useEffect, useRef } from "react";
import { Markmap } from "markmap-view";
import { Toolbar } from "markmap-toolbar";
import * as d3 from "d3";

export function MindmapCanvas({ root, selectedNodeId, onSelectNode, markmapRef, theme }) {
  const svgRef = useRef(null);
  const mmRef = useRef(null);
  const toolbarRef = useRef(null);

  useEffect(() => {
    if (!root || !svgRef.current) {
      mmRef.current?.destroy();
      mmRef.current = null;
      toolbarRef.current?.remove();
      toolbarRef.current = null;
      return;
    }

    mmRef.current?.destroy();
    toolbarRef.current?.remove();

    const data = convertToMarkmapNode(root);
    const mm = Markmap.create(svgRef.current, null, data);
    mmRef.current = mm;
    if (markmapRef) markmapRef.current = mm;

    const toolbar = Toolbar.create(mm);
    toolbar.setBrand?.(false);
    const toolbarItems = Toolbar.defaultItems?.filter((item) => item !== "dark");
    toolbar.setItems?.(toolbarItems);
    configureToolbar(toolbar.el, resolveDarkTheme(theme));
    svgRef.current.parentElement?.appendChild(toolbar.el);
    toolbarRef.current = toolbar.el;

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
      const target = event.target.closest(".markmap-node");
      if (!target) return;
      event.preventDefault();
      selectNode(target);
    });

    return () => {
      toolbarRef.current?.remove();
      toolbarRef.current = null;
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
    if (toolbarRef.current) {
      applyToolbarTheme(toolbarRef.current, isDark);
    }
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

function configureToolbar(toolbarEl, isDark) {
  Object.assign(toolbarEl.style, {
    position: "absolute",
    bottom: "20px",
    right: "20px",
    display: "flex",
    flexDirection: "row",
    alignItems: "center",
    gap: "8px",
    width: "auto",
    padding: "6px",
    borderRadius: "16px",
    backdropFilter: "blur(12px)",
  });
  applyToolbarTheme(toolbarEl, isDark);
  toolbarEl.querySelectorAll(".mm-toolbar-item").forEach((item) => {
    Object.assign(item.style, {
      display: "inline-flex",
      alignItems: "center",
      justifyContent: "center",
      width: "32px",
      height: "32px",
      margin: "0",
      borderRadius: "12px",
      transition: "background-color 160ms ease, color 160ms ease, box-shadow 160ms ease, transform 160ms ease",
    });
    item.style.setProperty("--toolbar-item-color", isDark ? "rgb(212, 212, 216)" : "rgb(87, 83, 78)");
    item.style.color = "var(--toolbar-item-color)";
    item.addEventListener("mouseenter", handleToolbarItemEnter);
    item.addEventListener("mouseleave", handleToolbarItemLeave);
  });
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

function applyToolbarTheme(toolbarEl, isDark) {
  if (!toolbarEl?.style) return;
  Object.assign(toolbarEl.style, {
    border: isDark ? "1px solid rgba(63, 63, 70, 0.9)" : "1px solid rgba(214, 211, 209, 0.72)",
    background: isDark ? "rgba(24, 24, 27, 0.95)" : "rgba(255, 255, 255, 0.86)",
    boxShadow: isDark ? "0 18px 44px rgba(0, 0, 0, 0.36)" : "0 18px 44px rgba(15, 23, 42, 0.12)",
  });
  toolbarEl.querySelectorAll(".mm-toolbar-item").forEach((item) => {
    item.style.setProperty("--toolbar-item-color", isDark ? "rgb(212, 212, 216)" : "rgb(87, 83, 78)");
    item.style.color = "var(--toolbar-item-color)";
  });
}

function handleToolbarItemEnter(event) {
  Object.assign(event.currentTarget.style, {
    background: "rgba(245, 158, 11, 0.12)",
    color: "rgb(180, 83, 9)",
    boxShadow: "0 10px 24px rgba(180, 83, 9, 0.12)",
    transform: "translateY(-1px)",
  });
}

function handleToolbarItemLeave(event) {
  Object.assign(event.currentTarget.style, {
    background: "",
    color: "var(--toolbar-item-color)",
    boxShadow: "",
    transform: "",
  });
}
