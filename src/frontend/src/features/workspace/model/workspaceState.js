const UI_SETTINGS_STORAGE_KEY = "video-include-ui-settings";

export const defaultUiSettings = {
  mindmapVisible: true,
  contentWidth: "regular",
  readingDensity: "comfortable",
  showTakeaways: true,
};

export function createInitialWorkspaceState() {
  return {
    library: null,
    summary: null,
    selectedSeriesId: null,
    selectedVideoId: null,
    selectedChapterId: null,
    selectedNodeId: null,
    generatingVideoKey: null,
    summaryLoading: false,
    ui: loadUiSettings(),
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
    selectedNodeId: summary?.mindmap?.children?.[0]?.id ?? summary?.mindmap?.id ?? null,
  };
}

export function getDefaultSelection(library, preferredSeriesId = null, preferredVideoId = null) {
  const series = library?.series ?? [];
  if (!series.length) {
    return { seriesId: null, videoId: null };
  }

  const preferredSeries = series.find((item) => item.id === preferredSeriesId) ?? series[0];
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

export function persistUiSettings(ui) {
  if (typeof window === "undefined") {
    return;
  }
  window.localStorage.setItem(UI_SETTINGS_STORAGE_KEY, JSON.stringify(normalizeUiSettings(ui)));
}

export function resetUiSettings() {
  return { ...defaultUiSettings };
}

function loadUiSettings() {
  if (typeof window === "undefined") {
    return resetUiSettings();
  }

  try {
    const rawValue = window.localStorage.getItem(UI_SETTINGS_STORAGE_KEY);
    if (!rawValue) {
      return resetUiSettings();
    }
    return normalizeUiSettings(JSON.parse(rawValue));
  } catch {
    return resetUiSettings();
  }
}

function normalizeUiSettings(value) {
  const record = value && typeof value === "object" ? value : {};
  return {
    mindmapVisible: typeof record.mindmapVisible === "boolean" ? record.mindmapVisible : true,
    contentWidth: record.contentWidth === "wide" ? "wide" : "regular",
    readingDensity: record.readingDensity === "compact" ? "compact" : "comfortable",
    showTakeaways: typeof record.showTakeaways === "boolean" ? record.showTakeaways : true,
  };
}
