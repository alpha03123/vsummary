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

describe("WorkspaceLibraryPanel", () => {
  it("keeps source link visible after a linked video is downloaded", () => {
    renderPanel();

    const sourceLink = screen.getByTitle("在 Bilibili 中查看");

    expect(sourceLink).toHaveAttribute("href", linkedDownloadedVideo.sourceUrl);
  });

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

  it("renders core_problem under title when present", () => {
    renderPanelWithVideo({
      ...linkedDownloadedVideo,
      coreProblem: "如何用三步拆解复杂问题",
    });

    expect(screen.getByText("如何用三步拆解复杂问题")).toBeInTheDocument();
  });

  it("omits core_problem display when coreProblem is empty", () => {
    renderPanelWithVideo({
      ...linkedDownloadedVideo,
      coreProblem: "",
    });

    // 找到 title 所在的 strong 元素的父容器,确认其下没有非空 line-clamp-2 span
    const titleNodes = screen.getAllByText(linkedDownloadedVideo.title);
    const titleStrong = titleNodes.find((node) => node.tagName.toLowerCase() === "strong");
    expect(titleStrong).toBeTruthy();
    const card = titleStrong.closest('[role="button"]');
    const coreProblemSpan = card?.querySelector("span.line-clamp-2");
    expect(coreProblemSpan === null || coreProblemSpan.textContent === "").toBe(true);
  });

  it("matches videos by core_problem in search filter", () => {
    renderPanelWithVideo({
      ...linkedDownloadedVideo,
      coreProblem: "拆解复杂问题",
    });

    const searchInput = screen.getByPlaceholderText(/筛选当前系列内容/);
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

    fireEvent.click(screen.getByRole("button", { name: "已生成" }));
    expect(screen.getByText("已生成视频")).toBeInTheDocument();
    expect(screen.queryByText("未处理视频")).not.toBeInTheDocument();
  });

  it("disables bulk deletion while any series work is active", () => {
    const onRequestBulkDelete = vi.fn();
    render(
      <WorkspaceLibraryPanel
        activeSeries={{ id: "s1", title: "S1", videos: [linkedDownloadedVideo] }}
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
        onRequestBulkDelete={onRequestBulkDelete}
        seriesHasActiveWork
        activeWorkSummary="系列中有 1 个任务正在处理，暂不能批量删除。"
        downloadProgress={null}
        onOpenSettings={vi.fn()}
      />,
    );

    expect(screen.getByLabelText("批量删除所选视频")).toBeDisabled();
    expect(screen.getByText("系列中有 1 个任务正在处理，暂不能批量删除。")).toBeInTheDocument();
  });

  it("renders embedded newlines in core_problem with whitespace-pre-line", () => {
    renderPanelWithVideo({
      ...linkedDownloadedVideo,
      coreProblem: "第一行\n第二行",
    });

    // 使用 querySelectorAll 找到含换行符的 span (title= attribute 也是证据)
    const card = screen.getAllByText(linkedDownloadedVideo.title)
      .find((node) => node.tagName.toLowerCase() === "strong")
      ?.closest('[role="button"]');
    expect(card).toBeTruthy();
    const spans = Array.from(card.querySelectorAll("span"));
    const span = spans.find((node) => node.textContent?.includes("第一行"));
    expect(span).toBeTruthy();
    expect(span?.textContent).toContain("第一行");
    expect(span?.textContent).toContain("第二行");
    expect(span?.className).toContain("whitespace-pre-line");
    expect(span?.className).toContain("line-clamp-2");
  });
});
