import { describe, expect, it, vi } from "vitest";

import { buildWorkspacePageModel } from "@src/features/workspace/ui/workspacePageModel";

function createController(status) {
  return {
    state: {
      library: null,
      generationProgress: null,
      generationSnapshot: null,
      videoDownloadProgress: null,
    },
    currentGenerationTask: status == null
      ? null
      : {
          snapshot: {
            status,
            progress: status === "running" ? 42 : 100,
          },
        },
    ui: {},
    activeSeries: null,
    selectedVideo: null,
    selectedContextType: null,
    selectedNode: null,
    previewUrl: null,
    playerSeekRequest: null,
    summary: null,
    mindmap: null,
    knowledgeCards: null,
    knowledgeCardsGenerating: false,
    knowledgeCardsFeedback: null,
    notes: null,
    tools: null,
    chatMessages: [],
    chatSessions: [],
    activeChatSessionId: null,
    chatPending: false,
    contextUsage: null,
    contextUsageLoading: false,
    onStartNewChat: () => {},
    onSelectChatSession: () => {},
    onOpenSeekReference: () => {},
    chatDrawerOpen: false,
    onSeekToTime: () => {},
    onToggleChatDrawer: () => {},
    onOpenChatDrawer: () => {},
    onCloseChatDrawer: () => {},
    onClearChat: () => {},
    onSubmitChat: () => {},
    isGeneratingSelectedVideo: status === "running" || status === "queued",
    isGeneratingSelectedSeries: false,
    isGeneratingMindmapSelectedVideo: false,
    knowledgeCardsLoading: false,
    notesLoading: false,
    savingNote: false,
    fasterWhisperModels: [],
    fasterWhisperModelsLoading: false,
    downloadingModelId: null,
    modelDownloadProgress: null,
    onSelectSeries: () => {},
    onEnterLibraryHome: () => {},
    onSelectVideo: () => {},
    onSelectSeriesContext: () => {},
    onSelectTool: () => {},
    onFocusNode: () => {},
    onGenerateVideo: () => {},
    onGenerateSeries: () => {},
    onCancelGeneration: () => {},
    onGenerateMindmap: () => {},
    onGenerateKnowledgeCards: () => {},
    onCreateNote: () => {},
    onUpdateNote: () => {},
    onDeleteNote: () => {},
    onToggleSettingsPanel: () => {},
    onCloseSettingsPanel: () => {},
    onChangeSetting: () => {},
    onSaveApiKey: () => {},
    onDownloadFasterWhisperModel: () => {},
    onCancelFasterWhisperModelDownload: () => {},
    onResetSettings: () => {},
    onClearError: () => {},
    onImportLocalSeries: () => {},
    onImportLocalPlaygroundVideos: () => {},
    onImportSeriesVideos: () => {},
    onDeleteSeries: () => {},
    onDeleteCurrentVideo: () => {},
  };
}

describe("buildWorkspacePageModel generation overlay", () => {
  it("shows overlay for active generation states", () => {
    expect(buildWorkspacePageModel(createController("running")).generation.showOverlay).toBe(true);
    expect(buildWorkspacePageModel(createController("queued")).generation.showOverlay).toBe(true);
    expect(buildWorkspacePageModel(createController("cancelling")).generation.showOverlay).toBe(true);
    expect(buildWorkspacePageModel(createController("completed")).generation.showOverlay).toBe(false);
    expect(buildWorkspacePageModel(createController("failed")).generation.showOverlay).toBe(false);
    expect(buildWorkspacePageModel(createController("cancelled")).generation.showOverlay).toBe(false);
  });
});

describe("buildWorkspacePageModel shell.player", () => {
  it("exposes playerSeekRequest and player.seekToTime", () => {
    const seekToTime = vi.fn();
    const controller = { ...createController(null), playerSeekRequest: { seconds: 7 }, onSeekToTime: seekToTime };
    const model = buildWorkspacePageModel(controller);
    expect(model.shell.playerSeekRequest).toEqual({ seconds: 7 });
    expect(model.shell.player.seekToTime).toBe(seekToTime);
  });
});

describe("buildWorkspacePageModel chat.drawer", () => {
  it("exposes drawer state and controls from the controller", () => {
    const toggle = vi.fn();
    const open = vi.fn();
    const close = vi.fn();
    const controller = {
      ...createController(null),
      chatDrawerOpen: true,
      onToggleChatDrawer: toggle,
      onOpenChatDrawer: open,
      onCloseChatDrawer: close,
    };
    const model = buildWorkspacePageModel(controller);
    expect(model.chat.drawerOpen).toBe(true);
    expect(model.chat.toggleDrawer).toBe(toggle);
    expect(model.chat.openDrawer).toBe(open);
    expect(model.chat.closeDrawer).toBe(close);
  });
});
