import { describe, it, expect, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";

import { WorkspaceMindmapView } from "@src/features/workspace/ui/views/WorkspaceMindmapView";

function makeTools(overrides = {}) {
  return {
    mindmap: {
      id: "mindmap", title: "思维导图", available: true, generated: false, status: "available",
      ...overrides,
    },
  };
}

const fakeMindmap = {
  id: "root", title: "测试导图", summary: "", start_seconds: 0, end_seconds: 0, children: [],
};

describe("WorkspaceMindmapView — regenerate button", () => {
  const baseProps = { tools: makeTools({ generated: true }), mindmap: fakeMindmap, selectedNode: null, mindmapLoading: false, isGeneratingMindmapSelectedVideo: false, onFocusNode: vi.fn(), onGenerateMindmap: vi.fn(), seriesId: "s1", videoId: "v1" };

  it("shows regenerate button when mindmap is generated", () => {
    render(<WorkspaceMindmapView {...baseProps} />);
    expect(screen.getByText("重新生成")).toBeInTheDocument();
  });

  it("hides regenerate button when mindmap not generated", () => {
    render(<WorkspaceMindmapView {...baseProps} tools={makeTools({ generated: false })} mindmap={null} />);
    expect(screen.queryByText("重新生成")).toBeNull();
  });

  it("regenerate button triggers onGenerateMindmap", () => {
    const onGenerate = vi.fn();
    render(<WorkspaceMindmapView {...baseProps} onGenerateMindmap={onGenerate} />);
    fireEvent.click(screen.getByText("重新生成"));
    expect(onGenerate).toHaveBeenCalledOnce();
  });

  it("regenerate button disabled while generating", () => {
    render(<WorkspaceMindmapView {...baseProps} isGeneratingMindmapSelectedVideo={true} />);
    expect(screen.getByText("重新生成").closest("button").disabled).toBe(true);
  });
});

describe("WorkspaceMindmapView — export button", () => {
  const baseProps = { tools: makeTools({ generated: true }), mindmap: fakeMindmap, selectedNode: null, mindmapLoading: false, isGeneratingMindmapSelectedVideo: false, onFocusNode: vi.fn(), onGenerateMindmap: vi.fn(), seriesId: "s1", videoId: "v1" };

  it("shows export button when mindmap is generated", () => {
    render(<WorkspaceMindmapView {...baseProps} />);
    expect(screen.getByText("导出")).toBeInTheDocument();
  });

  it("hides export button when mindmap not generated", () => {
    render(<WorkspaceMindmapView {...baseProps} tools={makeTools({ generated: false })} mindmap={null} />);
    expect(screen.queryByText("导出")).toBeNull();
  });
});
