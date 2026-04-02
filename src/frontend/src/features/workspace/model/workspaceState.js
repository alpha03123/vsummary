const UI_SETTINGS_STORAGE_KEY = "video-include-ui-settings";

export const defaultUiSettings = {
  mindmapVisible: true,
  contentWidth: "regular",
  readingDensity: "comfortable",
  showTakeaways: true,
};

export function createInitialWorkspaceState() {
  return {
    summary: null,
    library: null,
    selectedChapterId: null,
    selectedNodeId: null,
    ui: loadUiSettings(),
    settingsPanelOpen: false,
    error: "",
    loading: true,
  };
}

export function createLoadedState(summary, library, currentState) {
  return {
    ...currentState,
    summary,
    library,
    selectedChapterId: summary.chapters?.[0]?.id ?? null,
    selectedNodeId: summary.mindmap?.children?.[0]?.id ?? summary.mindmap?.id ?? null,
    error: "",
    loading: false,
  };
}

export function currentLibrary(existingLibrary, summary) {
  if (existingLibrary) {
    return existingLibrary;
  }

  return {
    workspace: { id: "local", title: "Local Workspace" },
    series: [
      {
        id: "imported",
        title: "Imported Series",
        videos: [{ id: summary.title, title: summary.title }],
      },
    ],
  };
}

export function normalizeSummaryPayload(payload) {
  if (payload && typeof payload === "object" && payload.summary && typeof payload.summary === "object") {
    return payload.summary;
  }
  return payload;
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
