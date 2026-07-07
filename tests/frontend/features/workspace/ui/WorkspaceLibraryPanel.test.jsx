import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { WorkspaceLibraryPanel } from "@src/features/workspace/ui/WorkspaceLibraryPanel";

const linkedDownloadedVideo = {
  id: "BV1xx411c7mD",
  title: "第一讲",
  sourceName: "BV1xx411c7mD.mp4",
  processed: false,
  status: "pending",
  isLinked: false,
  sourceUrl: "https://www.bilibili.com/video/BV1xx411c7mD",
};

function renderPanel() {
  render(
    <WorkspaceLibraryPanel
      activeSeries={{
        id: "__playground__",
        title: "Playground",
        videos: [linkedDownloadedVideo],
      }}
      selectedContextType="video"
      selectedVideo={linkedDownloadedVideo}
      isGeneratingSelectedVideo={false}
      isGeneratingSeries={false}
      seriesGenerationQueue={null}
      currentAsrModel={{ id: "large-v3-turbo", label: "large-v3-turbo", downloaded: true }}
      ragModels={[]}
      onEnterLibraryHome={vi.fn()}
      onSelectSeriesContext={vi.fn()}
      onSelectVideo={vi.fn()}
      onGenerateVideo={vi.fn()}
      onGenerateSeries={vi.fn()}
      onCancelGeneration={vi.fn()}
      onDownloadVideo={vi.fn()}
      onAddPlaygroundVideo={vi.fn()}
      onAddSeriesVideo={vi.fn()}
      onDeleteSeries={vi.fn()}
      onRequestDeleteCurrentVideo={vi.fn()}
      onRequestDeleteSeries={vi.fn()}
      downloadProgress={null}
      onOpenSettings={vi.fn()}
    />,
  );
}

function renderSeriesPanelWithQueue(seriesGenerationQueue, overrides = {}) {
  render(
    <WorkspaceLibraryPanel
      activeSeries={{
        id: "series-a",
        title: "Bilibili Series",
        videos: [linkedDownloadedVideo],
      }}
      selectedContextType="series"
      selectedVideo={null}
      isGeneratingSelectedVideo={false}
      isGeneratingSeries={false}
      seriesGenerationQueue={seriesGenerationQueue}
      currentAsrModel={{ id: "large-v3-turbo", label: "large-v3-turbo", downloaded: true }}
      ragModels={[]}
      onEnterLibraryHome={vi.fn()}
      onSelectSeriesContext={vi.fn()}
      onSelectVideo={vi.fn()}
      onGenerateVideo={vi.fn()}
      onGenerateSeries={vi.fn()}
      onCancelGeneration={vi.fn()}
      onDownloadVideo={vi.fn()}
      onAddPlaygroundVideo={vi.fn()}
      onAddSeriesVideo={vi.fn()}
      onDeleteSeries={vi.fn()}
      onRequestDeleteCurrentVideo={vi.fn()}
      onRequestDeleteSeries={vi.fn()}
      downloadProgress={null}
      onOpenSettings={vi.fn()}
      onExportSeriesMarkdown={overrides.onExportSeriesMarkdown ?? vi.fn()}
    />,
  );
}

describe("WorkspaceLibraryPanel", () => {
  it("keeps source link visible after a linked video is downloaded", () => {
    renderPanel();

    const sourceLink = screen.getByTitle("在 Bilibili 中查看");

    expect(sourceLink).toHaveAttribute("href", linkedDownloadedVideo.sourceUrl);
  });

  it("keeps failed series generation details visible in the series footer", () => {
    renderSeriesPanelWithQueue({
      seriesId: "series-a",
      status: "failed",
      completed: 0,
      total: 3,
      downloadVideoId: "BV1xx411c7mD",
      error: "视频下载进度连接已中断",
      detail: "下载 Bilibili 视频失败",
    });

    expect(screen.getByText("处理全部系列视频失败")).toBeInTheDocument();
    expect(screen.getByText("下载 Bilibili 视频失败")).toBeInTheDocument();
    expect(screen.getByText("视频下载进度连接已中断")).toBeInTheDocument();
    expect(screen.getByText("失败视频：BV1xx411c7mD")).toBeInTheDocument();
  });

  it("exports series markdown from the series footer and shows the output folder", async () => {
    const onExportSeriesMarkdown = vi.fn().mockResolvedValue({ outputDir: "D:/exports/Bilibili Series", exportedCount: 1 });

    renderSeriesPanelWithQueue(null, { onExportSeriesMarkdown });

    fireEvent.click(screen.getByRole("button", { name: "导出系列文案 Markdown" }));

    await waitFor(() => expect(onExportSeriesMarkdown).toHaveBeenCalledTimes(1));
    expect(await screen.findByText("已导出 1 个 Markdown 文件"));
    expect(screen.getByText("D:/exports/Bilibili Series")).toBeInTheDocument();
  });
});
