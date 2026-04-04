import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { WorkspaceReadingPane } from "./WorkspaceReadingPane";

describe("WorkspaceReadingPane", () => {
  it("renders seek details and seeks the preview video", async () => {
    const { container } = render(
      <WorkspaceReadingPane
        ui={{ showTakeaways: true }}
        tools={{
          preview: {
            previewUrl: "/api/videos/series-a/video-1/preview",
          },
        }}
        library={null}
        summary={null}
        mindmap={null}
        knowledgeCards={null}
        notes={null}
        activeSeries={{
          id: "series-a",
          title: "Series A",
          videos: [],
        }}
        selectedVideo={{
          id: "video-1",
          title: "Video 1",
        }}
        selectedContextType="video"
        selectedNode={null}
        previewUrl="/api/videos/series-a/video-1/preview"
        previewSeekRequest={{
          seconds: 128,
          endSeconds: 146,
          query: "百度地图 API Key",
          matchedText: "后续项目会用到百度地图 API，需要提前申请 API Key。",
          chapterTitle: "准备工作",
          requestId: "req-1",
        }}
        selectedToolId="preview"
        selectedChapterId={null}
        toolsLoading={false}
        summaryLoading={false}
        mindmapLoading={false}
        knowledgeCardsLoading={false}
        notesLoading={false}
        savingNote={false}
        isGeneratingMindmapSelectedVideo={false}
        isGeneratingSelectedVideo={false}
        onSelectTool={() => {}}
        onFocusNode={() => {}}
        onOpenCard={() => {}}
        onGenerateMindmap={() => {}}
        onGenerateKnowledgeCards={() => {}}
        onCreateNote={() => {}}
        onUpdateNote={() => {}}
        onDeleteNote={() => {}}
      />,
    );

    expect(screen.getByText("已定位到 02:08 - 02:26 · 准备工作")).toBeInTheDocument();
    expect(screen.getByText("检索问题：百度地图 API Key")).toBeInTheDocument();
    expect(screen.getByText("后续项目会用到百度地图 API，需要提前申请 API Key。")).toBeInTheDocument();

    const video = container.querySelector("video");
    expect(video).not.toBeNull();
    Object.defineProperty(video, "duration", { value: 300, configurable: true });

    fireEvent(video, new Event("loadedmetadata"));

    expect(video.currentTime).toBe(128);
  });

  it("renders notes panel and submits a manual note", () => {
    const onCreateNote = vi.fn();

    render(
      <WorkspaceReadingPane
        ui={{ showTakeaways: true }}
        tools={{
          notes: {
            id: "notes",
            title: "笔记",
            available: true,
            generated: true,
            status: "ready",
          },
          preview: {
            previewUrl: "/api/videos/series-a/video-1/preview",
          },
        }}
        library={null}
        summary={null}
        mindmap={null}
        knowledgeCards={null}
        notes={{ seriesId: "series-a", videoId: "video-1", title: "Video 1", notes: [] }}
        activeSeries={{
          id: "series-a",
          title: "Series A",
          videos: [],
        }}
        selectedVideo={{
          id: "video-1",
          title: "Video 1",
        }}
        selectedContextType="video"
        selectedNode={null}
        previewUrl="/api/videos/series-a/video-1/preview"
        previewSeekRequest={null}
        selectedToolId="notes"
        selectedChapterId={null}
        toolsLoading={false}
        summaryLoading={false}
        mindmapLoading={false}
        knowledgeCardsLoading={false}
        notesLoading={false}
        savingNote={false}
        isGeneratingMindmapSelectedVideo={false}
        isGeneratingSelectedVideo={false}
        onSelectTool={() => {}}
        onFocusNode={() => {}}
        onOpenCard={() => {}}
        onGenerateMindmap={() => {}}
        onGenerateKnowledgeCards={() => {}}
        onCreateNote={onCreateNote}
        onUpdateNote={() => {}}
        onDeleteNote={() => {}}
      />,
    );

    fireEvent.change(screen.getByPlaceholderText("笔记标题"), { target: { value: "新的笔记" } });
    fireEvent.change(screen.getByPlaceholderText("记录要点、结论或待办..."), {
      target: { value: "这里记录一条手动笔记。" },
    });
    fireEvent.click(screen.getByRole("button", { name: "保存笔记" }));

    expect(onCreateNote).toHaveBeenCalledWith({
      title: "新的笔记",
      content: "这里记录一条手动笔记。",
      source: "manual",
    });
  });
});
