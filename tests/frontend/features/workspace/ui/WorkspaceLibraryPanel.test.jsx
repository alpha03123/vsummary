import { fireEvent, render, screen } from "@testing-library/react";
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

describe("WorkspaceLibraryPanel", () => {
  function renderPanelWithVideo(video) {
    return render(
      <WorkspaceLibraryPanel
        activeSeries={{
          id: "s1",
          title: "S1",
          videos: [video],
        }}
        selectedContextType="video"
        selectedVideo={video}
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

  it("matches videos by core_problem in search filter", () => {
    renderPanelWithVideo({
      ...linkedDownloadedVideo,
      coreProblem: "拆解复杂问题",
    });

    const searchInput = screen.getByPlaceholderText("搜索视频");
    fireEvent.change(searchInput, { target: { value: "拆解" } });

    // 卡片应仍然可见
    expect(screen.getByText("拆解复杂问题")).toBeInTheDocument();
  });

  it("combines generated status filter with text search", () => {
    render(
      <WorkspaceLibraryPanel
        activeSeries={{
          id: "s1",
          title: "S1",
          videos: [
            { ...linkedDownloadedVideo, id: "done", title: "已生成视频", processed: true },
            { ...linkedDownloadedVideo, id: "pending", title: "未处理视频", processed: false },
          ],
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
        onAddSeriesVideo={vi.fn()}
        onRequestDeleteCurrentVideo={vi.fn()}
        onRequestDeleteSeries={vi.fn()}
        onRequestBulkDelete={vi.fn()}
        downloadProgress={null}
        onOpenSettings={vi.fn()}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "已生成1" }));
    expect(screen.getByText("已生成视频")).toBeInTheDocument();
    expect(screen.queryByText("未处理视频")).not.toBeInTheDocument();
  });

});
