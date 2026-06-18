import { describe, it, expect, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";

import { WorkspaceSeriesMindmapView } from "@src/features/workspace/ui/views/WorkspaceSeriesMindmapView";

const fakeMindmap = {
  id: "root", title: "测试系列导图", summary: "", start_seconds: 0, end_seconds: 0, children: [],
};

describe("WorkspaceSeriesMindmapView", () => {
  const baseProps = {
    seriesId: "s1",
    seriesMindmap: null,
    seriesMindmapAvailable: true,
    seriesMindmapLoading: false,
    generatingSeriesMindmap: false,
    selectedNode: null,
    onFocusNode: vi.fn(),
    onGenerateSeriesMindmap: vi.fn(),
  };

  it("shows generate button when no mindmap data", () => {
    render(<WorkspaceSeriesMindmapView {...baseProps} />);
    expect(screen.getByText("生成系列导图")).toBeInTheDocument();
  });

  it("shows blocked state when seriesMindmapAvailable is false", () => {
    render(<WorkspaceSeriesMindmapView {...baseProps} seriesMindmapAvailable={false} />);
    expect(screen.getByText("需要先生成 AI 概况")).toBeInTheDocument();
  });

  it("shows regenerate and export buttons when mindmap exists", () => {
    render(
      <WorkspaceSeriesMindmapView
        {...baseProps}
        seriesMindmap={fakeMindmap}
      />
    );
    expect(screen.getByText("重新生成")).toBeInTheDocument();
    expect(screen.getByText("导出")).toBeInTheDocument();
  });

  it("generate button calls onGenerateSeriesMindmap", () => {
    const onGenerate = vi.fn();
    render(<WorkspaceSeriesMindmapView {...baseProps} onGenerateSeriesMindmap={onGenerate} />);
    fireEvent.click(screen.getByText("生成系列导图"));
    expect(onGenerate).toHaveBeenCalledOnce();
  });
});

describe("WorkspaceSeriesMindmapView — elapsed time progress", () => {
  const baseProps = {
    seriesId: "s1",
    seriesMindmap: null,
    seriesMindmapAvailable: true,
    seriesMindmapLoading: false,
    generatingSeriesMindmap: false,
    selectedNode: null,
    onFocusNode: vi.fn(),
    onGenerateSeriesMindmap: vi.fn(),
    mindmapGenerationProgress: null,
  };

  it("shows elapsed time during generation", () => {
    render(
      <WorkspaceSeriesMindmapView
        {...baseProps}
        generatingSeriesMindmap={true}
        mindmapGenerationProgress={{
          status: "running", stage: "generate", progress: 30,
          detail: "正在生成系列思维导图", elapsed_seconds: 12,
        }}
      />
    );
    expect(screen.getByText("正在生成系列思维导图")).toBeTruthy();
    expect(screen.getByText("已用 12 秒")).toBeTruthy();
  });

  it("shows updated elapsed time on rerender", () => {
    const { rerender } = render(
      <WorkspaceSeriesMindmapView
        {...baseProps}
        generatingSeriesMindmap={true}
        mindmapGenerationProgress={{
          status: "running", stage: "generate", progress: 30,
          detail: "正在生成系列思维导图", elapsed_seconds: 12,
        }}
      />
    );
    expect(screen.getByText("已用 12 秒")).toBeTruthy();

    rerender(
      <WorkspaceSeriesMindmapView
        {...baseProps}
        generatingSeriesMindmap={true}
        mindmapGenerationProgress={{
          status: "running", stage: "generate", progress: 30,
          detail: "正在生成系列思维导图", elapsed_seconds: 18,
        }}
      />
    );
    expect(screen.getByText("已用 18 秒")).toBeTruthy();
  });

  it("does not show percentage during generation", () => {
    render(
      <WorkspaceSeriesMindmapView
        {...baseProps}
        generatingSeriesMindmap={true}
        mindmapGenerationProgress={{
          status: "running", stage: "generate", progress: 30,
          detail: "正在生成系列思维导图", elapsed_seconds: 12,
        }}
      />
    );
    expect(screen.queryByText("30%")).toBeNull();
  });

  it("hides progress on completion", () => {
    render(
      <WorkspaceSeriesMindmapView
        {...baseProps}
        generatingSeriesMindmap={false}
        seriesMindmap={{ id: "root", title: "Test", children: [] }}
        mindmapGenerationProgress={null}
      />
    );
    expect(screen.queryByText(/已用.*秒/)).toBeNull();
  });
});
