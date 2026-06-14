import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { WorkspaceOverviewView } from "@src/features/workspace/ui/views/WorkspaceOverviewView";

const summary = {
  title: "视频标题",
  core_problem: "核心问题",
  key_takeaways: ["要点 1", "要点 2"],
  chapters: [
    {
      id: "ch-1",
      title: "第一章 入门",
      start_seconds: 5,
      end_seconds: 60,
      summary: "本章讲了一些东西",
      key_points: ["点 A", "点 B"],
      transcript_segments: [
        { start_seconds: 5, end_seconds: 10, text: "段落一" },
        { start_seconds: 12, end_seconds: 18, text: "段落二" },
      ],
    },
  ],
};

const selectedVideo = { id: "v1", title: "视频标题" };
const tools = { overview: { generated: true } };

function renderView(overrides = {}) {
  const onSeek = vi.fn();
  render(
    <WorkspaceOverviewView
      ui={{ showTakeaways: true }}
      tools={tools}
      summary={summary}
      selectedVideo={selectedVideo}
      selectedChapterId={null}
      summaryLoading={false}
      isGeneratingSelectedVideo={false}
      onSeek={onSeek}
      {...overrides}
    />,
  );
  return { onSeek };
}

describe("WorkspaceOverviewView chapter + transcript clicks", () => {
  it("does not crash when onSeek is omitted", () => {
    render(
      <WorkspaceOverviewView
        ui={{ showTakeaways: true }}
        tools={tools}
        summary={summary}
        selectedVideo={selectedVideo}
        selectedChapterId={null}
        summaryLoading={false}
        isGeneratingSelectedVideo={false}
      />,
    );
    expect(screen.getByText("第一章 入门")).toBeInTheDocument();
  });

  it("chapter header click calls onSeek with chapter timestamps", () => {
    const { onSeek } = renderView();
    const chapter = screen.getByText("第一章 入门").closest("button");
    expect(chapter).toBeTruthy();
    fireEvent.click(chapter);
    expect(onSeek).toHaveBeenCalledWith({
      seconds: 5,
      endSeconds: 60,
      chapterTitle: "第一章 入门",
    });
  });

  it("transcript segment click calls onSeek with segment timestamps", () => {
    const { onSeek } = renderView();
    const details = document.querySelector("details");
    fireEvent.click(within(details).getByText("查看本章原文"));
    const seg1 = within(details).getByText("段落一").closest("button");
    expect(seg1).toBeTruthy();
    fireEvent.click(seg1);
    expect(onSeek).toHaveBeenCalledWith({
      seconds: 5,
      endSeconds: 10,
      chapterTitle: "第一章 入门",
    });
  });

  it("clicking on summary or key_points does NOT call onSeek", () => {
    const { onSeek } = renderView();
    fireEvent.click(screen.getByText("本章讲了一些东西"));
    fireEvent.click(screen.getByText("点 A"));
    fireEvent.click(screen.getByText("点 B"));
    expect(onSeek).not.toHaveBeenCalled();
  });

  it("clicking on Key Takeaways bullets does NOT call onSeek", () => {
    const { onSeek } = renderView();
    fireEvent.click(screen.getByText("要点 1"));
    fireEvent.click(screen.getByText("要点 2"));
    expect(onSeek).not.toHaveBeenCalled();
  });
});