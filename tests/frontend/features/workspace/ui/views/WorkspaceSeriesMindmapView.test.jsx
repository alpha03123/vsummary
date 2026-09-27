import { act, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { WorkspaceSeriesMindmapView } from "@src/features/workspace/ui/views/WorkspaceSeriesMindmapView";

afterEach(() => {
  vi.useRealTimers();
});

describe("WorkspaceSeriesMindmapView", () => {
  it("keeps elapsed time moving before durable timing arrives", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-09-27T20:40:00Z"));
    render(
      <WorkspaceSeriesMindmapView
        seriesId="series-1"
        seriesMindmap={null}
        seriesMindmapAvailable
        seriesMindmapLoading={false}
        generatingSeriesMindmap
        selectedNode={null}
        onFocusNode={vi.fn()}
        onGenerateSeriesMindmap={vi.fn()}
        mindmapGenerationProgress={{ status: "running", stage: "generate", progress: 10, detail: "正在生成系列思维导图" }}
      />,
    );

    act(() => {
      vi.advanceTimersByTime(5_000);
    });

    expect(screen.getByText(/已用 5 秒/)).toBeInTheDocument();
  });
});
