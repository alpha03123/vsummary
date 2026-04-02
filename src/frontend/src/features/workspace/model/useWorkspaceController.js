import { useEffect, useMemo, useReducer } from "react";

import {
  generateVideoMindmap,
  generateVideoSummary,
  getVideoPreviewUrl,
  loadVideoMindmap,
  loadVideoSummary,
  loadVideoTools,
  loadWorkspaceLibrary,
} from "./workspaceApi";
import { findChapterForNode, findNodeById } from "./workspaceTree";
import {
  createInitialWorkspaceState,
  createMindmapLoadedState,
  createSummaryLoadedState,
  createWorkspaceLoadedState,
  findSeriesById,
  findVideoById,
  markVideoAsReady,
  persistUiSettings,
  resetUiSettings,
} from "./workspaceState";

function workspaceReducer(state, action) {
  switch (action.type) {
    case "workspace_loaded":
      return createWorkspaceLoadedState(action.library, state);
    case "load_failed":
      return {
        ...state,
        loading: false,
        toolsLoading: false,
        summaryLoading: false,
        mindmapLoading: false,
        generatingVideoKey: null,
        generatingMindmapKey: null,
        error: action.message,
      };
    case "series_selected": {
      const series = findSeriesById(state.library, action.seriesId);
      return {
        ...state,
        tools: null,
        selectedSeriesId: action.seriesId,
        selectedVideoId: series?.videos?.[0]?.id ?? null,
        selectedToolId: "overview",
        summary: null,
        mindmap: null,
        selectedChapterId: null,
        selectedNodeId: null,
      };
    }
    case "library_home_entered":
      return {
        ...state,
        tools: null,
        selectedSeriesId: null,
        selectedVideoId: null,
        selectedToolId: "overview",
        summary: null,
        mindmap: null,
        selectedChapterId: null,
        selectedNodeId: null,
        toolsLoading: false,
        summaryLoading: false,
        mindmapLoading: false,
      };
    case "video_selected":
      return {
        ...state,
        selectedSeriesId: action.seriesId,
        selectedVideoId: action.videoId,
        selectedToolId: "overview",
        tools: null,
        summary: null,
        mindmap: null,
        selectedChapterId: null,
        selectedNodeId: null,
      };
    case "tool_selected":
      return {
        ...state,
        selectedToolId: action.toolId,
        error: "",
      };
    case "tools_loading_started":
      return {
        ...state,
        toolsLoading: true,
        error: "",
      };
    case "tools_loaded":
      return {
        ...state,
        tools: action.tools,
        toolsLoading: false,
      };
    case "summary_loading_started":
      return {
        ...state,
        summaryLoading: true,
        error: "",
      };
    case "summary_loaded":
      return createSummaryLoadedState(action.summary, state);
    case "summary_cleared":
      return {
        ...state,
        summary: null,
        summaryLoading: false,
        selectedChapterId: null,
      };
    case "mindmap_loading_started":
      return {
        ...state,
        mindmapLoading: true,
        error: "",
      };
    case "mindmap_loaded":
      return createMindmapLoadedState(action.mindmap, state);
    case "mindmap_cleared":
      return {
        ...state,
        mindmap: null,
        mindmapLoading: false,
        selectedNodeId: null,
      };
    case "chapter_selected":
      return {
        ...state,
        selectedChapterId: action.chapterId,
      };
    case "node_selected":
      return {
        ...state,
        selectedNodeId: action.nodeId,
        selectedChapterId: action.chapterId ?? state.selectedChapterId,
      };
    case "settings_panel_toggled":
      return {
        ...state,
        settingsPanelOpen: !state.settingsPanelOpen,
      };
    case "settings_panel_closed":
      return {
        ...state,
        settingsPanelOpen: false,
      };
    case "ui_setting_changed":
      return {
        ...state,
        ui: {
          ...state.ui,
          [action.key]: action.value,
        },
      };
    case "ui_settings_reset":
      return {
        ...state,
        ui: resetUiSettings(),
      };
    case "generation_started":
      return {
        ...state,
        generatingVideoKey: action.videoKey,
        error: "",
      };
    case "generation_succeeded":
      return createSummaryLoadedState(action.summary, {
        ...state,
        library: markVideoAsReady(state.library, action.seriesId, action.videoId),
        tools: state.tools == null
          ? state.tools
          : {
              ...state.tools,
              overview: {
                ...state.tools.overview,
                generated: true,
                status: "ready",
              },
              mindmap: {
                ...state.tools.mindmap,
                available: true,
                generated: false,
                status: "available",
              },
            },
        generatingVideoKey: null,
      });
    case "mindmap_generation_started":
      return {
        ...state,
        generatingMindmapKey: action.videoKey,
        error: "",
      };
    case "mindmap_generation_succeeded":
      return createMindmapLoadedState(action.mindmap, {
        ...state,
        tools: state.tools == null
          ? state.tools
          : {
              ...state.tools,
              mindmap: {
                ...state.tools.mindmap,
                available: true,
                generated: true,
                status: "ready",
              },
            },
        generatingMindmapKey: null,
      });
    default:
      return state;
  }
}

export function useWorkspaceController() {
  const [state, dispatch] = useReducer(workspaceReducer, undefined, createInitialWorkspaceState);

  useEffect(() => {
    let cancelled = false;

    loadWorkspaceLibrary()
      .then((library) => {
        if (!cancelled) {
          dispatch({ type: "workspace_loaded", library });
        }
      })
      .catch((error) => {
        if (!cancelled) {
          dispatch({
            type: "load_failed",
            message: error instanceof Error ? error.message : "加载失败",
          });
        }
      });

    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    persistUiSettings(state.ui);
  }, [state.ui]);

  useEffect(() => {
    const selectedVideo = findVideoById(state.library, state.selectedSeriesId, state.selectedVideoId);
    if (!selectedVideo) {
      dispatch({ type: "tools_loaded", tools: null });
      return;
    }

    let cancelled = false;
    dispatch({ type: "tools_loading_started" });
    loadVideoTools(state.selectedSeriesId, state.selectedVideoId)
      .then((tools) => {
        if (!cancelled) {
          dispatch({ type: "tools_loaded", tools });
        }
      })
      .catch((error) => {
        if (!cancelled) {
          dispatch({
            type: "load_failed",
            message: error instanceof Error ? error.message : "加载失败",
          });
        }
      });

    return () => {
      cancelled = true;
    };
  }, [state.library, state.selectedSeriesId, state.selectedVideoId]);

  useEffect(() => {
    const selectedVideo = findVideoById(state.library, state.selectedSeriesId, state.selectedVideoId);
    if (!selectedVideo) {
      dispatch({ type: "summary_cleared" });
      return;
    }
    if (!state.tools?.overview.generated) {
      dispatch({ type: "summary_cleared" });
      return;
    }

    let cancelled = false;
    dispatch({ type: "summary_loading_started" });
    loadVideoSummary(state.selectedSeriesId, state.selectedVideoId)
      .then((summary) => {
        if (!cancelled) {
          dispatch({ type: "summary_loaded", summary });
        }
      })
      .catch((error) => {
        if (!cancelled) {
          dispatch({
            type: "load_failed",
            message: error instanceof Error ? error.message : "加载失败",
          });
        }
      });

    return () => {
      cancelled = true;
    };
  }, [state.library, state.selectedSeriesId, state.selectedVideoId, state.tools?.overview.generated]);

  useEffect(() => {
    const selectedVideo = findVideoById(state.library, state.selectedSeriesId, state.selectedVideoId);
    if (!selectedVideo || state.selectedToolId !== "mindmap" || !state.tools?.mindmap.generated) {
      dispatch({ type: "mindmap_cleared" });
      return;
    }

    let cancelled = false;
    dispatch({ type: "mindmap_loading_started" });
    loadVideoMindmap(state.selectedSeriesId, state.selectedVideoId)
      .then((mindmap) => {
        if (!cancelled) {
          dispatch({ type: "mindmap_loaded", mindmap });
        }
      })
      .catch((error) => {
        if (!cancelled) {
          dispatch({
            type: "load_failed",
            message: error instanceof Error ? error.message : "加载失败",
          });
        }
      });

    return () => {
      cancelled = true;
    };
  }, [state.library, state.selectedSeriesId, state.selectedVideoId, state.selectedToolId, state.tools?.mindmap.generated]);

  const summary = state.summary;
  const mindmap = state.mindmap;
  const tools = state.tools;
  const activeSeries = findSeriesById(state.library, state.selectedSeriesId);
  const selectedVideo = findVideoById(state.library, state.selectedSeriesId, state.selectedVideoId);
  const selectedNode = useMemo(
    () => findNodeById(mindmap, state.selectedNodeId),
    [mindmap, state.selectedNodeId],
  );
  const isGeneratingSelectedVideo =
    state.generatingVideoKey != null &&
    state.generatingVideoKey === buildVideoKey(state.selectedSeriesId, state.selectedVideoId);
  const isGeneratingMindmapSelectedVideo =
    state.generatingMindmapKey != null &&
    state.generatingMindmapKey === buildVideoKey(state.selectedSeriesId, state.selectedVideoId);
  const previewUrl = state.selectedSeriesId && state.selectedVideoId
    ? getVideoPreviewUrl(state.selectedSeriesId, state.selectedVideoId)
    : null;

  function onSelectSeries(seriesId) {
    dispatch({ type: "series_selected", seriesId });
  }

  function onEnterLibraryHome() {
    dispatch({ type: "library_home_entered" });
  }

  function onSelectVideo(seriesId, videoId) {
    dispatch({ type: "video_selected", seriesId, videoId });
  }

  function onSelectTool(toolId) {
    dispatch({ type: "tool_selected", toolId });
  }

  function onFocusNode(node) {
    const chapterId = findChapterForNode(state.summary?.chapters ?? [], node)?.id ?? null;
    dispatch({
      type: "node_selected",
      nodeId: node.id,
      chapterId,
    });

    requestAnimationFrame(() => {
      if (chapterId) {
        document.getElementById(chapterId)?.scrollIntoView({ behavior: "smooth", block: "start" });
      }
    });
  }

  function onToggleSettingsPanel() {
    dispatch({ type: "settings_panel_toggled" });
  }

  function onCloseSettingsPanel() {
    dispatch({ type: "settings_panel_closed" });
  }

  function onChangeSetting(key, value) {
    dispatch({ type: "ui_setting_changed", key, value });
  }

  function onResetSettings() {
    dispatch({ type: "ui_settings_reset" });
  }

  async function onGenerateVideo() {
    if (!state.selectedSeriesId || !state.selectedVideoId) {
      return;
    }

    const videoKey = buildVideoKey(state.selectedSeriesId, state.selectedVideoId);
    dispatch({ type: "generation_started", videoKey });
    try {
      const summaryResult = await generateVideoSummary(state.selectedSeriesId, state.selectedVideoId);
      dispatch({
        type: "generation_succeeded",
        seriesId: state.selectedSeriesId,
        videoId: state.selectedVideoId,
        summary: summaryResult,
      });
    } catch (error) {
      dispatch({
        type: "load_failed",
        message: error instanceof Error ? error.message : "生成失败",
      });
    }
  }

  async function onGenerateMindmap() {
    if (!state.selectedSeriesId || !state.selectedVideoId) {
      return;
    }

    const videoKey = buildVideoKey(state.selectedSeriesId, state.selectedVideoId);
    dispatch({ type: "mindmap_generation_started", videoKey });
    try {
      const mindmapResult = await generateVideoMindmap(state.selectedSeriesId, state.selectedVideoId);
      dispatch({
        type: "mindmap_generation_succeeded",
        mindmap: mindmapResult,
      });
    } catch (error) {
      dispatch({
        type: "load_failed",
        message: error instanceof Error ? error.message : "生成失败",
      });
    }
  }

  return {
    state,
    ui: state.ui,
    tools,
    summary,
    mindmap,
    activeSeries,
    selectedVideo,
    selectedNode,
    previewUrl,
    isGeneratingMindmapSelectedVideo,
    isGeneratingSelectedVideo,
    onSelectSeries,
    onEnterLibraryHome,
    onSelectVideo,
    onSelectTool,
    onFocusNode,
    onGenerateVideo,
    onGenerateMindmap,
    onToggleSettingsPanel,
    onCloseSettingsPanel,
    onChangeSetting,
    onResetSettings,
  };
}

function buildVideoKey(seriesId, videoId) {
  if (!seriesId || !videoId) {
    return null;
  }
  return `${seriesId}/${videoId}`;
}
