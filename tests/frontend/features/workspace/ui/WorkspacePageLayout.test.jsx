import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

vi.mock("@src/features/workspace/ui/WorkspaceToolbar", () => ({
  WorkspaceToolbar: ({ onToggleChatDrawer }) => (
    <button onClick={onToggleChatDrawer} aria-label="打开分析助手">toolbar</button>
  ),
}));
vi.mock("@src/features/workspace/ui/WorkspaceLibraryPanel", () => ({
  WorkspaceLibraryPanel: ({ onRequestBulkDelete }) => (
    <button onClick={() => onRequestBulkDelete?.(["v1", "v2"])}>delete-selected</button>
  ),
}));
vi.mock("@src/features/workspace/ui/WorkspaceSeriesGrid", () => ({
  WorkspaceSeriesGrid: () => <div>series-grid</div>,
}));
vi.mock("@src/features/workspace/ui/WorkspaceReadingPane", () => ({
  WorkspaceReadingPane: ({
    onGenerateSeriesMindmap,
    onUploadSrt,
    onRestoreAutomaticTranscript,
    onSeek,
    seriesMindmap,
    seriesMindmapAvailable,
    seriesMindmapLoading,
    generatingSeriesMindmap,
    mindmapGenerationProgress,
  }) => (
    <div
      data-testid="reading-pane"
      data-on-seek={Boolean(onSeek)}
      data-on-upload-srt={Boolean(onUploadSrt)}
      data-on-restore-automatic-transcript={Boolean(onRestoreAutomaticTranscript)}
      data-series-mindmap={seriesMindmap?.id ?? ""}
      data-series-mindmap-available={String(seriesMindmapAvailable)}
      data-series-mindmap-loading={String(seriesMindmapLoading)}
      data-generating-series-mindmap={String(generatingSeriesMindmap)}
      data-series-mindmap-progress={mindmapGenerationProgress?.status ?? ""}
      data-on-generate-series-mindmap={Boolean(onGenerateSeriesMindmap)}
    >
      reading
    </div>
  ),
}));
vi.mock("@src/features/workspace/ui/WorkspaceVideoPlayer", () => ({
  WorkspaceVideoPlayer: ({ videoSource, onOpenOverviewAtTime }) => (
    <button
      data-testid="video-player"
      data-source={videoSource}
      data-on-open-overview-at-time={Boolean(onOpenOverviewAtTime)}
      onClick={() => onOpenOverviewAtTime?.(42.5)}
    >
      player
    </button>
  ),
}));
vi.mock("@src/features/workspace/ui/ChatDrawer", () => ({
  ChatDrawer: ({ isOpen }) => <div data-testid="chat-drawer" data-open={String(isOpen)}>drawer</div>,
}));
vi.mock("@src/features/workspace/ui/WorkspaceImportModal", () => ({
  WorkspaceImportModal: () => null,
}));
vi.mock("@src/features/workspace/ui/shared/WorkspaceConfirmDialog", () => ({
  WorkspaceConfirmDialog: ({ open, title, onConfirm }) => (
    open ? <button onClick={onConfirm}>{title}</button> : null
  ),
}));
vi.mock("@src/features/workspace/ui/WorkspaceLibraryHomePane", () => ({
  WorkspaceLibraryHomePane: () => null,
}));
vi.mock("@src/features/workspace/ui/WorkspaceSettingsPanel", () => ({
  WorkspaceSettingsPanel: () => null,
}));
vi.mock("@src/features/workspace/ui/WorkspaceGenerationOverlay", () => ({
  WorkspaceGenerationOverlay: () => null,
}));

import { WorkspacePage } from "@src/features/workspace/ui/WorkspacePage";

function makePage(overrides = {}) {
  return {
    shell: {
      state: {
        loading: false,
        backendReady: true,
        settingsPanelOpen: false,
        knowledgeMemorySnapshot: null,
        selectedToolId: "studio",
        selectedChapterId: null,
        toolsLoading: false,
        summaryLoading: false,
        mindmapLoading: false,
      },
      ui: {},
      library: { workspace: { title: "我的工作台" } },
      activeSeries: { id: "s1", title: "我的系列" },
      selectedVideo: { id: "v1", title: "第一讲", sourceType: "video" },
      selectedContextType: "video",
      selectedNode: null,
      previewUrl: "/api/videos/s1/v1/preview",
      playerSeekRequest: { seconds: 10, requestId: "1" },
      player: { seekToTime: vi.fn() },
      summary: null,
      mindmap: null,
      seriesMindmap: null,
      seriesMindmapAvailable: false,
      knowledgeCards: null,
      knowledgeCardsGenerating: false,
      knowledgeCardsFeedback: null,
      notes: null,
      tools: {},
      ...overrides.shell,
    },
    chat: {
      messages: [], sessions: [], activeSessionId: null, pending: false,
      contextUsage: null, contextUsageLoading: false,
      drawerOpen: false, toggleDrawer: vi.fn(), openDrawer: vi.fn(), closeDrawer: vi.fn(),
      startNewChat: vi.fn(), selectChatSession: vi.fn(), openSeekReference: vi.fn(), clearChat: vi.fn(), submit: vi.fn(),
      ...overrides.chat,
    },
    generation: {
      isGeneratingSummary: false, isGeneratingSeries: false, seriesGenerationQueue: null,
      isGeneratingMindmap: false, knowledgeCardsLoading: false, notesLoading: false, savingNote: false,
      seriesMindmapLoading: false, generatingSeriesMindmap: false, mindmapGenerationProgress: null,
      fasterWhisperModels: [], fasterWhisperModelsLoading: false, ragModels: [], ragModelsLoading: false,
      downloadingRagModelKey: null, downloadingModelId: null, modelDownloadsById: {},
      modelDownloadStatus: null, modelDownloadProgress: null, modelDownloadErrorModelId: null, modelDownloadError: null,
      progress: null, snapshot: null, showOverlay: false, videoDownloadProgress: null, downloadingVideoKey: null,
      ...overrides.generation,
    },
    actions: new Proxy({}, { get: (target, property) => target[property] ?? vi.fn() }),
  };
}

describe("WorkspacePage new layout", () => {
  it("renders the video player in the middle when a video is selected", () => {
    render(<WorkspacePage page={makePage()} />);
    const player = screen.getByTestId("video-player");
    expect(player).toBeInTheDocument();
    expect(player.getAttribute("data-source")).toBe("/api/videos/s1/v1/preview");
  });

  it("forwards onSeek to WorkspaceReadingPane", () => {
    render(<WorkspacePage page={makePage()} />);
    const pane = screen.getByTestId("reading-pane");
    expect(pane.getAttribute("data-on-seek")).toBe("true");
  });

  it("opens the current transcript from the video player when the overview is available", () => {
    const openOverviewAtTime = vi.fn();
    const page = makePage({
      shell: { tools: { overview: { generated: true } } },
    });
    page.actions.openOverviewAtTime = openOverviewAtTime;

    render(<WorkspacePage page={page} />);
    const player = screen.getByTestId("video-player");
    expect(player.getAttribute("data-on-open-overview-at-time")).toBe("true");

    fireEvent.click(player);
    expect(openOverviewAtTime).toHaveBeenCalledWith(42.5);
  });

  it("forwards transcript generation actions to WorkspaceReadingPane", () => {
    render(<WorkspacePage page={makePage()} />);
    const pane = screen.getByTestId("reading-pane");
    expect(pane.getAttribute("data-on-upload-srt")).toBe("true");
    expect(pane.getAttribute("data-on-restore-automatic-transcript")).toBe("true");
  });

  it("forwards series mindmap state to WorkspaceReadingPane", () => {
    render(
      <WorkspacePage
        page={makePage({
          shell: {
            seriesMindmap: { id: "series-root" },
            seriesMindmapAvailable: true,
          },
          generation: {
            seriesMindmapLoading: true,
            generatingSeriesMindmap: true,
            mindmapGenerationProgress: { status: "running" },
          },
        })}
      />,
    );

    const pane = screen.getByTestId("reading-pane");
    expect(pane.getAttribute("data-series-mindmap")).toBe("series-root");
    expect(pane.getAttribute("data-series-mindmap-available")).toBe("true");
    expect(pane.getAttribute("data-series-mindmap-loading")).toBe("true");
    expect(pane.getAttribute("data-generating-series-mindmap")).toBe("true");
    expect(pane.getAttribute("data-series-mindmap-progress")).toBe("running");
    expect(pane.getAttribute("data-on-generate-series-mindmap")).toBe("true");
  });

  it("mounts ChatDrawer with isOpen reflecting chat.drawerOpen", () => {
    const page = makePage();
    page.chat.drawerOpen = true;
    render(<WorkspacePage page={page} />);
    const drawer = screen.getByTestId("chat-drawer");
    expect(drawer.getAttribute("data-open")).toBe("true");
  });

  it("confirms and forwards selected video IDs for bulk deletion", async () => {
    const deleteVideos = vi.fn().mockResolvedValue({ deleted: ["v1", "v2"], failed: [] });
    const page = makePage();
    page.actions.deleteVideos = deleteVideos;
    render(<WorkspacePage page={page} />);

    fireEvent.click(screen.getByRole("button", { name: "delete-selected" }));
    fireEvent.click(screen.getByRole("button", { name: "删除 2 个视频？" }));

    await waitFor(() => expect(deleteVideos).toHaveBeenCalledWith(["v1", "v2"]));
  });
});
