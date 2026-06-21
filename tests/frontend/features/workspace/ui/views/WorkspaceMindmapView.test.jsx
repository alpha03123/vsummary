import { describe, it, expect, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";

vi.mock("markmap-view", () => ({
  Markmap: {
    create: vi.fn(() => ({
      destroy: vi.fn(),
      fit: vi.fn(() => Promise.resolve()),
      state: { rect: { x1: 0, x2: 100, y1: 0, y2: 100 } },
      svg: { node: vi.fn(() => ({ classList: { add: vi.fn(), remove: vi.fn() } })) },
      zoom: { transform: vi.fn() },
    })),
  },
}));
vi.mock("markmap-toolbar", () => ({
  Toolbar: {
    create: vi.fn(() => ({ el: document.createElement("div") })),
  },
}));
vi.mock("d3", () => ({
  select: vi.fn(() => ({
    on: vi.fn(),
    datum: vi.fn(),
    node: vi.fn(() => ({ classList: { add: vi.fn(), remove: vi.fn() } })),
  })),
}));

vi.mock("@src/features/workspace/ui/mindmapSVGExport", () => ({
  exportMindmapAsSVG: vi.fn(() => Promise.resolve()),
}));

import { exportMindmapAsSVG } from "@src/features/workspace/ui/mindmapSVGExport";
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

describe("WorkspaceMindmapView — export dropdown", () => {
  const baseProps = {
    tools: makeTools({ generated: true }),
    mindmap: fakeMindmap, selectedNode: null, mindmapLoading: false,
    isGeneratingMindmapSelectedVideo: false,
    onFocusNode: vi.fn(), onGenerateMindmap: vi.fn(),
    seriesId: "s1", videoId: "v1", mindmapGenerationProgress: null,
  };

  it("shows export button when mindmap is generated", () => {
    render(<WorkspaceMindmapView {...baseProps} />);
    expect(screen.getByText("导出")).toBeTruthy();
  });

  it("hides export button when mindmap not generated", () => {
    render(<WorkspaceMindmapView {...baseProps} tools={makeTools({ generated: false })} mindmap={null} />);
    expect(screen.queryByText("导出")).toBeNull();
  });

  it("shows three options when dropdown is opened", () => {
    render(<WorkspaceMindmapView {...baseProps} />);
    fireEvent.click(screen.getByText("导出"));
    expect(screen.getByText("Markdown (.md)")).toBeTruthy();
    expect(screen.getByText("HTML (.html)")).toBeTruthy();
    expect(screen.getByText("SVG (.svg)")).toBeTruthy();
  });

  it("closes dropdown on option click", () => {
    render(<WorkspaceMindmapView {...baseProps} />);
    fireEvent.click(screen.getByText("导出"));
    expect(screen.getByText("Markdown (.md)")).toBeTruthy();
    fireEvent.click(screen.getByText("Markdown (.md)"));
    expect(screen.queryByText("Markdown (.md)")).toBeNull();
  });

  it("T10: SVG option calls exportMindmapAsSVG with the markmap instance from the ref", async () => {
    exportMindmapAsSVG.mockClear();
    const { Markmap } = await import("markmap-view");

    render(<WorkspaceMindmapView {...baseProps} />);
    const fakeMm = Markmap.create.mock.results[Markmap.create.mock.results.length - 1].value;

    fireEvent.click(screen.getByText("导出"));
    fireEvent.click(screen.getByText("SVG (.svg)"));

    expect(exportMindmapAsSVG).toHaveBeenCalledTimes(1);
    expect(exportMindmapAsSVG).toHaveBeenCalledWith(fakeMm, "mindmap-v1.svg");
  });
});

describe("WorkspaceMindmapView — elapsed time progress", () => {
  const baseProps = {
    tools: makeTools({ generated: false }),
    mindmap: null,
    selectedNode: null,
    mindmapLoading: false,
    isGeneratingMindmapSelectedVideo: false,
    onFocusNode: vi.fn(),
    onGenerateMindmap: vi.fn(),
    seriesId: "s1",
    videoId: "v1",
    mindmapGenerationProgress: null,
  };

  it("shows elapsed time during generation", () => {
    render(
      <WorkspaceMindmapView
        {...baseProps}
        isGeneratingMindmapSelectedVideo={true}
        mindmapGenerationProgress={{
          status: "running",
          stage: "generate",
          progress: 45,
          detail: "正在生成思维导图",
          elapsed_seconds: 5,
        }}
      />
    );
    expect(screen.getByText("正在生成思维导图")).toBeTruthy();
    expect(screen.getByText("已用 5 秒")).toBeTruthy();
  });

  it("shows updated elapsed time on rerender", () => {
    const { rerender } = render(
      <WorkspaceMindmapView
        {...baseProps}
        isGeneratingMindmapSelectedVideo={true}
        mindmapGenerationProgress={{
          status: "running", stage: "generate", progress: 45,
          detail: "正在生成思维导图", elapsed_seconds: 5,
        }}
      />
    );
    expect(screen.getByText("已用 5 秒")).toBeTruthy();

    rerender(
      <WorkspaceMindmapView
        {...baseProps}
        isGeneratingMindmapSelectedVideo={true}
        mindmapGenerationProgress={{
          status: "running", stage: "generate", progress: 45,
          detail: "正在生成思维导图", elapsed_seconds: 8,
        }}
      />
    );
    expect(screen.getByText("已用 8 秒")).toBeTruthy();
  });

  it("does not show percentage during generation", () => {
    render(
      <WorkspaceMindmapView
        {...baseProps}
        isGeneratingMindmapSelectedVideo={true}
        mindmapGenerationProgress={{
          status: "running", stage: "generate", progress: 45,
          detail: "正在生成思维导图", elapsed_seconds: 5,
        }}
      />
    );
    expect(screen.queryByText("45%")).toBeNull();
  });

  it("hides progress on completion", () => {
    render(
      <WorkspaceMindmapView
        {...baseProps}
        isGeneratingMindmapSelectedVideo={false}
        mindmap={{ id: "root", title: "Test", children: [] }}
        mindmapGenerationProgress={null}
      />
    );
    expect(screen.queryByText(/已用.*秒/)).toBeNull();
  });
});
