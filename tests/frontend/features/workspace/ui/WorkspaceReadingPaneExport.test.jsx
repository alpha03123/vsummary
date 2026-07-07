import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { WorkspaceReadingPane } from "@src/features/workspace/ui/WorkspaceReadingPane";

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
      tools={{
        overview: { generated: true },
        knowledgeCards: { available: true, generated: false },
        preview: {},
        ...overrides.tools,
      }}
      chat={null}
      summary={null}
      mindmap={null}
      knowledgeCards={null}
      knowledgeCardsGenerating={false}
      knowledgeCardsFeedback={null}
      notes={overrides.notes ?? null}
      activeSeries={activeSeries}
      selectedVideo={selectedVideo}
      selectedContextType="video"
      selectedNode={null}
      selectedToolId={overrides.selectedToolId ?? "overview"}
      selectedChapterId={null}
      toolsLoading={false}
      summaryLoading={false}
      mindmapLoading={false}
      knowledgeCardsLoading={false}
      notesLoading={false}
      savingNote={false}
      isGeneratingMindmapSelectedVideo={false}
      isGeneratingSelectedVideo={false}
      onSelectTool={vi.fn()}
      onFocusNode={vi.fn()}
      onSeek={vi.fn()}
      onGenerateMindmap={vi.fn()}
      onGenerateKnowledgeCards={vi.fn()}
      onClearKnowledgeCardsFeedback={vi.fn()}
      onCreateNote={vi.fn()}
      onUpdateNote={vi.fn()}
      onDeleteNote={vi.fn()}
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

  it("disables knowledge card export before cards are generated", async () => {
    renderPane({ selectedToolId: "knowledge-cards" });

    expect(await screen.findByRole("button", { name: "导出" })).toBeDisabled();
    expect(screen.queryByRole("link", { name: "知识卡片导出" })).toBeNull();
  });

  it("enables notes export when the current video has notes", async () => {
    renderPane({
      selectedToolId: "notes",
      notes: {
        notes: [
          {
            id: "note-1",
            title: "重点",
            content: "内容",
            source: "manual",
            createdAt: "2026-06-06T10:00:00Z",
            updatedAt: "2026-06-06T10:00:00Z",
          },
        ],
      },
    });

    fireEvent.click(await screen.findByRole("button", { name: "导出" }));
    expect(screen.getByRole("link", { name: "笔记导出" })).toHaveAttribute(
      "href",
      "/api/videos/series-1/video-1/exports/notes.md",
    );
  });

  it("disables notes export when there are no notes", async () => {
    renderPane({
      selectedToolId: "notes",
      notes: { notes: [] },
    });

    expect(await screen.findByRole("button", { name: "导出" })).toBeDisabled();
  });
});
