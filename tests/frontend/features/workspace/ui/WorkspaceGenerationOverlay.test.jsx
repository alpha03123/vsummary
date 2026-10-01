import { act, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { WorkspaceGenerationOverlay } from "@src/features/workspace/ui/WorkspaceGenerationOverlay";

afterEach(() => {
  vi.useRealTimers();
});

describe("WorkspaceGenerationOverlay", () => {
  it("shows picture recognition alongside text work and keeps initialization indeterminate", () => {
    const { rerender } = render(<WorkspaceGenerationOverlay generationProgress={1} generationSnapshot={{ status: "running", stage: "initialize", detail: "正在准备识别和生成所需的模型" }} />);
    expect(screen.getByRole("progressbar")).not.toHaveAttribute("aria-valuenow");
    expect(screen.queryByText(/1%/)).not.toBeInTheDocument();
    rerender(<WorkspaceGenerationOverlay generationProgress={92} generationSnapshot={{ status: "running", stage: "understand_frames", steps: [
      { id: "chapter_images", label: "为章节添加截图", status: "running" },
      { id: "ai_summary", label: "识别画面并生成概况", status: "running", detail: "正在阅读图片中的文字和内容" },
    ] }} />);
    expect(screen.getByText("有 2 项同时进行")).toBeInTheDocument();
    expect(screen.getAllByText("进行中")).toHaveLength(2);
    expect(screen.getByText("正在阅读图片中的文字和内容")).toBeInTheDocument();
    expect(screen.queryByText("语音转写")).not.toBeInTheDocument();
  });

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

    expect(screen.getByText("准备任务 · 准备中")).toBeInTheDocument();
    expect(screen.getByText("已耗时").parentElement).toHaveTextContent("3秒");
    expect(screen.queryByText("预计总时长")).not.toBeInTheDocument();
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

  it("keeps live elapsed time without extrapolating milestone percentages into an ETA", () => {
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
    expect(screen.queryByText("预计总时长")).not.toBeInTheDocument();
    expect(screen.queryByText("预计剩余")).not.toBeInTheDocument();
  });
});
