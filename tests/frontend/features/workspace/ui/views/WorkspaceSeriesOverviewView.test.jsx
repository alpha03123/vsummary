import { WorkspaceSeriesOverviewView } from "@workspace/workspace/ui/views/WorkspaceSeriesOverviewView";
import { render } from "@src/testing/renderWorkspace";
import { screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

const activeSeries = {
  id: "series-1",
  title: "测试系列",
  videos: [
    { id: "video-1", title: "第一讲", processed: true },
    { id: "video-2", title: "第二讲", processed: true },
    { id: "video-3", title: "第三讲", processed: false },
  ],
};

function createSummary(title) {
  return {
    title,
    core_problem: "核心问题",
    key_takeaways: ["关键结论"],
    chapters: [
      {
        id: `${title}-chapter-1`,
        title: "章节一",
        start_seconds: 0,
        end_seconds: 10,
        summary: "章节说明",
        key_points: ["章节要点"],
        transcript_segments: [],
      },
    ],
  };
}

function renderView(overrides = {}) {
  const onOpenVideoOverview = vi.fn();
  render(
    <WorkspaceSeriesOverviewView
      activeSeries={activeSeries}
      ui={{ showTakeaways: true }}
      summariesByVideoId={{
        "video-1": createSummary("第一讲概况"),
        "video-2": createSummary("第二讲概况"),
      }}
      loading={false}
      onOpenVideoOverview={onOpenVideoOverview}
      {...overrides}
    />,
  );
  return { onOpenVideoOverview };
}

describe("WorkspaceSeriesOverviewView", () => {
  it("expands and highlights the cited transcript segment in the matching video overview", async () => {
    const citedSummary = createSummary("第二讲概况");
    citedSummary.chapters[0].transcript_segments = [{
      start_seconds: 2,
      end_seconds: 4,
      text: "被引用的转写片段",
    }];

    renderView({
      summariesByVideoId: {
        "video-1": createSummary("第一讲概况"),
        "video-2": citedSummary,
      },
      citationFocus: {
        videoId: "video-2",
        seconds: 3,
        endSeconds: 3,
        requestId: "citation-1",
      },
    });

    await screen.findByRole("button", { name: /被引用的转写片段/ });

    expect(screen.queryByText("第一讲概况")).not.toBeInTheDocument();
    expect(screen.getByText("第二讲概况")).toBeInTheDocument();
    expect(document.getElementById("overview-transcript-video-2-第二讲概况-chapter-1")).toHaveProperty("open", true);
  });

  it("uses video-scoped transcript ids when multiple overviews share a chapter id", () => {
    const firstSummary = createSummary("第一讲概况");
    const secondSummary = createSummary("第二讲概况");
    firstSummary.chapters[0].id = "chapter-1";
    secondSummary.chapters[0].id = "chapter-1";
    firstSummary.chapters[0].transcript_segments = [{ start_seconds: 0, end_seconds: 1, text: "第一讲转写" }];
    secondSummary.chapters[0].transcript_segments = [{ start_seconds: 0, end_seconds: 1, text: "第二讲转写" }];

    renderView({
      summariesByVideoId: {
        "video-1": firstSummary,
        "video-2": secondSummary,
      },
    });

    expect(document.getElementById("overview-transcript-video-1-chapter-1")).toBeInTheDocument();
    expect(document.getElementById("overview-transcript-video-2-chapter-1")).toBeInTheDocument();
  });
});
