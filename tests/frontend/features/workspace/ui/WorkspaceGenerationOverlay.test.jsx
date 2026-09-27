import { act, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { WorkspaceGenerationOverlay } from "@src/features/workspace/ui/WorkspaceGenerationOverlay";

afterEach(() => {
  vi.useRealTimers();
});

describe("WorkspaceGenerationOverlay", () => {
  it("uses the preparation stage and live timing before a measurable percentage is available", () => {
    render(
      <WorkspaceGenerationOverlay
        generationProgress={0}
        generationSnapshot={{
          status: "running",
          stage: "claimed",
          detail: "正在准备任务",
          startedAt: Date.now() / 1000 - 3,
          elapsedSeconds: 3,
          estimatedTotalSeconds: null,
          remainingSeconds: null,
        }}
      />,
    );

    expect(screen.getByText("准备素材 · 准备中")).toBeInTheDocument();
    expect(screen.getByText("已耗时").parentElement).toHaveTextContent("3秒");
    expect(screen.getByText("预计总时长").parentElement).toHaveTextContent("计算中");
    expect(screen.queryByText("Worker 已领取任务")).not.toBeInTheDocument();
  });

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
    expect(screen.queryByText(/小时/)).not.toBeInTheDocument();
  });

  it("estimates duration from local elapsed time when durable timing has not arrived yet", () => {
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
    expect(screen.getByText("预计总时长").parentElement).toHaveTextContent("20秒");
    expect(screen.getByText("预计剩余").parentElement).toHaveTextContent("10秒");
  });
});
