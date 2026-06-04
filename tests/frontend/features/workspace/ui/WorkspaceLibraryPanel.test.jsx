import { render, screen } from "@testing-library/react";
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
});
