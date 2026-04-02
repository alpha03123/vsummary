export const initialWorkspaceState = {
  summary: null,
  library: null,
  selectedChapterId: null,
  selectedNodeId: null,
  mindmapVisible: true,
  error: "",
  loading: true,
};

export function createLoadedState(summary, library) {
  return {
    summary,
    library,
    selectedChapterId: summary.chapters?.[0]?.id ?? null,
    selectedNodeId: summary.mindmap?.children?.[0]?.id ?? summary.mindmap?.id ?? null,
    mindmapVisible: true,
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
