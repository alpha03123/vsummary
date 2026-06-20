import { useEffect, useRef } from "react";
import { Markmap } from "markmap-view";
import { Toolbar } from "markmap-toolbar";
import * as d3 from "d3";

export function MindmapCanvas({ root, selectedNodeId, onSelectNode, markmapRef }) {
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
    toolbar.el.setAttribute("style", "position:absolute;bottom:20px;right:20px");
    svgRef.current.parentElement?.appendChild(toolbar.el);
    toolbarRef.current = toolbar.el;

    d3.select(svgRef.current).on("click", (event) => {
      const target = event.target.closest(".markmap-node");
      if (!target || !onSelectNode) return;
      const nodeData = d3.select(target).datum();
      if (!nodeData) return;
      onSelectNode({
        id: nodeData.payload?.id,
        title: nodeData.content,
        summary: nodeData.payload?.summary,
        start_seconds: nodeData.payload?.startSeconds ?? 0,
        end_seconds: nodeData.payload?.endSeconds ?? 0,
        children: nodeData.children || [],
      });
    });

    return () => {
      toolbarRef.current?.remove();
      toolbarRef.current = null;
      mm.destroy();
      mmRef.current = null;
      if (markmapRef) markmapRef.current = null;
    };
  }, [root, markmapRef]);

  useEffect(() => {
    const svg = mmRef.current?.svg?.node();
    if (!svg || !root) return;
    if (document.documentElement.classList.contains("dark")) {
      svg.classList.add("markmap-dark");
    } else {
      svg.classList.remove("markmap-dark");
    }
  }, [root]);

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
      <div className="p-8 text-stone-500 text-sm text-center">
        当前没有导图数据。
      </div>
    );
  }

  return (
    <svg
      ref={svgRef}
      className="mindmap-svg absolute inset-0 w-full h-full"
      style={{ background: "transparent" }}
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
