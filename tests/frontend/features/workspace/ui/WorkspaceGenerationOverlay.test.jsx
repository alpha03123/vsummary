import { act, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { WorkspaceGenerationOverlay } from "@src/features/workspace/ui/WorkspaceGenerationOverlay";

afterEach(() => {
  vi.useRealTimers();
});

describe("WorkspaceGenerationOverlay", () => {
  it("does not treat a missing start timestamp as the Unix epoch", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-09-27T20:30:00Z"));
    render(
      <WorkspaceGenerationOverlay
        generationProgress={5}
        generationSnapshot={{
          status: "running",
          stage: "prepare",
          detail: "正在读取视频信息",
          startedAt: null,
          elapsedSeconds: null,
        }}
      />,
    );

    expect(screen.getByText("已耗时").parentElement).toHaveTextContent("0秒");
  });

  it("advances elapsed time while generation is running", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-09-27T20:30:00Z"));
    render(
      <WorkspaceGenerationOverlay
        generationProgress={50}
        generationSnapshot={{ status: "running", stage: "transcribe", detail: "正在转写音频" }}
      />,
    );

    act(() => {
      vi.advanceTimersByTime(10_000);
    });

    expect(screen.getByText("已耗时").parentElement).toHaveTextContent("10秒");
  });
});
