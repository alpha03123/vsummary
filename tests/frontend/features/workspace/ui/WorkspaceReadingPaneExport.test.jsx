import { WorkspaceReadingPane } from "@workspace/workspace/ui/WorkspaceReadingPane";
import { render } from "@src/testing/renderWorkspace";
import { fireEvent, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

const selectedVideo = {
  id: "video-1",
  title: "第一讲",
};

const activeSeries = {
  id: "series-1",
  title: "课程",
};

function renderPane(overrides = {}) {
  render(
    <WorkspaceReadingPane
      ui={{ showTakeaways: true }}
      tools={overrides.tools === undefined ? {
        overview: { generated: true },
        knowledgeCards: { available: true, generated: false },
        preview: {},
      } : overrides.tools}
      chat={null}
      summary={null}
      aiSummary={overrides.aiSummary ?? null}
      mindmap={null}
      knowledgeCards={null}
      knowledgeCardsGenerating={false}
      knowledgeCardsFeedback={null}
      notes={overrides.notes ?? null}
      activeSeries={activeSeries}
      selectedVideo={overrides.selectedVideo === undefined ? selectedVideo : overrides.selectedVideo}
      selectedContextType={overrides.selectedContextType ?? "video"}
      selectedNode={null}
      toolId={overrides.toolId ?? "overview"}
      selectedChapterId={null}
      toolsLoading={overrides.toolsLoading ?? false}
      summaryLoading={false}
      mindmapLoading={false}
      knowledgeCardsLoading={false}
      notesLoading={false}
      savingNote={false}
      isGeneratingMindmapSelectedVideo={false}
      isGeneratingSelectedVideo={false}
      onSelectTool={overrides.onSelectTool ?? vi.fn()}
      onFocusNode={vi.fn()}
      onSeek={vi.fn()}
      onGenerateMindmap={vi.fn()}
      onGenerateKnowledgeCards={vi.fn()}
      onClearKnowledgeCardsFeedback={vi.fn()}
      onCreateNote={vi.fn()}
      onUpdateNote={vi.fn()}
      onDeleteNote={vi.fn()}
      onOpenCitationReference={overrides.onOpenCitationReference ?? vi.fn()}
    />,
  );
}

describe("WorkspaceReadingPane markdown exports", () => {
  it("uses the active series and selected video in overview export links", async () => {
    renderPane();

    fireEvent.click(await screen.findByRole("button", { name: "导出" }));
    expect(screen.getByRole("link", { name: "概况导出" })).toHaveAttribute(
      "href",
      "/api/videos/series-1/video-1/exports/summary.md",
    );
    expect(screen.getByRole("link", { name: "转写导出" })).toHaveAttribute(
      "href",
      "/api/videos/series-1/video-1/exports/transcript.md",
    );
    expect(screen.getByRole("link", { name: "混合导出" })).toHaveAttribute(
      "href",
      "/api/videos/series-1/video-1/exports/mixed.md",
    );
  });

  it("exports the original media from the video preview", async () => {
    renderPane({ toolId: "preview" });

    fireEvent.click(await screen.findByRole("button", { name: "导出" }));
    expect(screen.getByRole("link", { name: "视频导出" })).toHaveAttribute(
      "href",
      "/api/videos/series-1/video-1/exports/video",
    );
  });
});

describe("WorkspaceReadingPane AI summary references", () => {
  it("keeps the current panel when an AI summary citation is opened", async () => {
    const onSelectTool = vi.fn();
    const onOpenCitationReference = vi.fn();
    renderPane({
      toolId: "ai-summary",
      onSelectTool,
      onOpenCitationReference,
      aiSummary: {
        title: "AI 概括",
        content: "原文依据[1]",
        citations: [{
          id: "1",
          label: "逐字稿",
          source_type: "transcript",
          slots: [{ target_type: "video", video_id: "video-1", start_seconds: 12, end_seconds: 14, text: "原文" }],
        }],
      },
    });

    fireEvent.click(await screen.findByRole("link", { name: "1" }));

    expect(onOpenCitationReference).toHaveBeenCalledWith(expect.objectContaining({ seconds: 12 }));
    expect(onSelectTool).not.toHaveBeenCalled();
  });
});
