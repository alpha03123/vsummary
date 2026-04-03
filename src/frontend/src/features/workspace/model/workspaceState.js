export const defaultUiSettings = {
  showTakeaways: true,
  theme: "light",
  aiTranscriptEnhancement: true,
  asrModelQuality: "large-v3-turbo",
};

export function createInitialWorkspaceState() {
  return {
    library: null,
    tools: null,
    summary: null,
    mindmap: null,
    selectedSeriesId: null,
    selectedVideoId: null,
    selectedContextType: "library",
    selectedToolId: "studio",
    selectedChapterId: null,
    selectedNodeId: null,
    generatingVideoKey: null,
    generatingMindmapKey: null,
    generationProgress: null,
    toolsLoading: false,
    summaryLoading: false,
    mindmapLoading: false,
    fasterWhisperModels: [],
    fasterWhisperModelsLoading: false,
    ui: resetUiSettings(),
    settingsPanelOpen: false,
    error: "",
    loading: true,
  };
}

export function createWorkspaceLoadedState(library, currentState) {
  const selection = getDefaultSelection(library, currentState.selectedSeriesId, currentState.selectedVideoId);
  return {
    ...currentState,
    library,
    selectedSeriesId: selection.seriesId,
    selectedVideoId: selection.videoId,
    selectedContextType: selection.seriesId ? currentState.selectedContextType : "library",
    error: "",
    loading: false,
  };
}

export function createSummaryLoadedState(summary, currentState) {
  return {
    ...currentState,
    summary,
    summaryLoading: false,
    selectedChapterId: summary?.chapters?.[0]?.id ?? null,
  };
}

export function createMindmapLoadedState(mindmap, currentState) {
  return {
    ...currentState,
    mindmap,
    mindmapLoading: false,
    selectedNodeId: mindmap?.children?.[0]?.id ?? mindmap?.id ?? null,
  };
}

export function getDefaultSelection(library, preferredSeriesId = null, preferredVideoId = null) {
  const series = library?.series ?? [];
  if (!series.length) {
    return { seriesId: null, videoId: null };
  }

  if (!preferredSeriesId) {
    return { seriesId: null, videoId: null };
  }

  const preferredSeries = series.find((item) => item.id === preferredSeriesId);
  if (!preferredSeries) {
    return { seriesId: null, videoId: null };
  }

  const preferredVideo =
    preferredSeries.videos.find((item) => item.id === preferredVideoId) ?? preferredSeries.videos[0] ?? null;

  return {
    seriesId: preferredSeries.id,
    videoId: preferredVideo?.id ?? null,
  };
}

export function findSeriesById(library, seriesId) {
  return library?.series?.find((series) => series.id === seriesId) ?? null;
}

export function findVideoById(library, seriesId, videoId) {
  return findSeriesById(library, seriesId)?.videos.find((video) => video.id === videoId) ?? null;
}

export function markVideoAsReady(library, seriesId, videoId) {
  if (!library) {
    return library;
  }

  return {
    ...library,
    series: library.series.map((series) =>
      series.id !== seriesId
        ? series
        : {
            ...series,
            videos: series.videos.map((video) =>
              video.id !== videoId
                ? video
                : {
                    ...video,
                    processed: true,
                    status: "ready",
                  },
            ),
          },
    ),
  };
}

export function resetUiSettings() {
  return { ...defaultUiSettings };
}

export function normalizeUiSettings(value) {
  const record = value && typeof value === "object" ? value : {};
  return {
    showTakeaways: typeof record.showTakeaways === "boolean" ? record.showTakeaways : true,
    theme: record.theme === "dark" ? "dark" : "light",
    aiTranscriptEnhancement:
      typeof record.aiTranscriptEnhancement === "boolean" ? record.aiTranscriptEnhancement : true,
    asrModelQuality:
      typeof record.asrModelQuality === "string" && record.asrModelQuality.trim()
        ? record.asrModelQuality.trim()
        : "large-v3-turbo",
  };
}
