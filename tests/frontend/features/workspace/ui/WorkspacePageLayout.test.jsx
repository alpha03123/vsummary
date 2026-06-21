import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

vi.mock("@src/features/workspace/ui/WorkspaceToolbar", () => ({
  WorkspaceToolbar: ({ onToggleChatDrawer }) => (
    <button onClick={onToggleChatDrawer} aria-label="打开分析助手">toolbar</button>
  ),
}));
vi.mock("@src/features/workspace/ui/WorkspaceLibraryPanel", () => ({
  WorkspaceLibraryPanel: () => <div>library</div>,
}));
vi.mock("@src/features/workspace/ui/WorkspaceSeriesGrid", () => ({
  WorkspaceSeriesGrid: () => <div>series-grid</div>,
}));
vi.mock("@src/features/workspace/ui/WorkspaceReadingPane", () => ({
  WorkspaceReadingPane: ({
    onGenerateSeriesMindmap,
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
  WorkspaceVideoPlayer: ({ videoSource }) => <div data-testid="video-player" data-source={videoSource}>player</div>,
}));
vi.mock("@src/features/workspace/ui/ChatDrawer", () => ({
  ChatDrawer: ({ isOpen }) => <div data-testid="chat-drawer" data-open={String(isOpen)}>drawer</div>,
}));
vi.mock("@src/features/workspace/ui/WorkspaceImportModal", () => ({
  WorkspaceImportModal: () => null,
}));
vi.mock("@src/features/workspace/ui/shared/WorkspaceConfirmDialog", () => ({
  WorkspaceConfirmDialog: () => null,
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
    actions: new Proxy({}, { get: () => vi.fn() }),
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
});
