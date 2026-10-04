import { WorkspaceOverviewView } from "@workspace/workspace/ui/views/WorkspaceOverviewView";
import { render } from "@src/testing/renderWorkspace";
import { fireEvent, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

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
      image_url: "/api/videos/s/v/screenshots/chapter-01.jpg",
      image_timestamp_seconds: 8,
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
  it("chapter header click calls onSeek with chapter timestamps", () => {
    const { onSeek } = renderView();
    const chapterCard = document.getElementById("overview-chapter-ch-1");
    fireEvent.click(chapterCard.querySelector("button"));
    expect(onSeek).toHaveBeenCalledWith({
      seconds: 5,
      endSeconds: 60,
      chapterTitle: "第一章 入门",
    });
  });

  it("transcript segment click calls onSeek with segment timestamps", () => {
    const { onSeek } = renderView();
    fireEvent.click(screen.getByText("查看本章原文"));
    fireEvent.click(screen.getByRole("button", { name: /段落一/ }));
    expect(onSeek).toHaveBeenCalledWith({
      seconds: 5,
      endSeconds: 10,
      chapterTitle: "第一章 入门",
    });
  });

  it("chapter screenshot click calls onSeek with its capture timestamp", () => {
    const { onSeek } = renderView();

    fireEvent.click(screen.getByRole("button", { name: /第一章 入门 视频截图/ }));

    expect(onSeek).toHaveBeenCalledWith({
      seconds: 8,
      endSeconds: 8,
      chapterTitle: "第一章 入门",
    });
  });

  it.each(["citation", "playback"])("manual transcript toggles neither seek nor re-scroll during %s focus", (source) => {
    const scrollIntoView = vi.fn();
    const previousScrollIntoView = Object.getOwnPropertyDescriptor(HTMLElement.prototype, "scrollIntoView");
    Object.defineProperty(HTMLElement.prototype, "scrollIntoView", { configurable: true, value: scrollIntoView });
    const previousRequestAnimationFrame = window.requestAnimationFrame;
    const previousCancelAnimationFrame = window.cancelAnimationFrame;
    window.requestAnimationFrame = (callback) => { callback(); return 1; };
    window.cancelAnimationFrame = vi.fn();
    try {
      const onFollowOverviewPlaybackChange = vi.fn();
      const { onSeek } = renderView({
        ...(source === "citation"
          ? { citationFocus: { seconds: 12, endSeconds: 18, requestId: "citation-1" } }
          : { playbackTime: 12, followOverviewPlayback: true }),
        onFollowOverviewPlaybackChange,
      });
      const initialCalls = scrollIntoView.mock.calls.length;
      expect(initialCalls).toBeGreaterThan(0);
      const details = document.getElementById("overview-transcript-ch-1");
      const initiallyOpen = details.open;

      fireEvent.click(screen.getByText("查看本章原文"));
      expect(details.open).toBe(!initiallyOpen);
      fireEvent.click(screen.getByText("查看本章原文"));

      expect(details.open).toBe(initiallyOpen);
      expect(onSeek).not.toHaveBeenCalled();
      expect(onFollowOverviewPlaybackChange).toHaveBeenLastCalledWith(false);
      expect(scrollIntoView).toHaveBeenCalledTimes(initialCalls);
    } finally {
      window.requestAnimationFrame = previousRequestAnimationFrame;
      window.cancelAnimationFrame = previousCancelAnimationFrame;
      if (previousScrollIntoView) {
        Object.defineProperty(HTMLElement.prototype, "scrollIntoView", previousScrollIntoView);
      } else {
        delete HTMLElement.prototype.scrollIntoView;
      }
    }
  });

  it("renders only the visible transcript rows for a large chapter", () => {
    const largeSummary = {
      ...summary,
      chapters: [{
        ...summary.chapters[0],
        transcript_segments: Array.from({ length: 1800 }, (_, index) => ({
          start_seconds: index * 10,
          end_seconds: index * 10 + 10,
          text: `模拟段落 ${index + 1}`,
        })),
      }],
    };

    renderView({ summary: largeSummary });
    fireEvent.click(screen.getByText("查看本章原文"));

    expect(screen.getAllByRole("button", { name: /模拟段落/ })).toHaveLength(10);
  });
});
