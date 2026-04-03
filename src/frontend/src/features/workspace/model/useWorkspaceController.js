import { useEffect, useMemo, useReducer } from "react";

import {
  cancelFasterWhisperModelDownload,
  downloadFasterWhisperModel,
  generateVideoMindmap,
  generateVideoSummary,
  getVideoPreviewUrl,
  loadFasterWhisperModels,
  loadVideoMindmap,
  loadVideoSummary,
  loadWorkspaceSettings,
  loadVideoTools,
  loadWorkspaceLibrary,
  subscribeFasterWhisperModelDownloadProgress,
  subscribeVideoGenerationProgress,
  updateWorkspaceSettings,
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
  normalizeUiSettings,
  resetUiSettings,
} from "./workspaceState";

function workspaceReducer(state, action) {
  switch (action.type) {
    case "workspace_loaded":
      return createWorkspaceLoadedState(action.library, state);
    case "workspace_settings_loaded":
      return {
        ...state,
        ui: normalizeUiSettings(action.settings),
      };
    case "faster_whisper_models_loading_started":
      return {
        ...state,
        fasterWhisperModelsLoading: true,
      };
    case "faster_whisper_model_download_started":
      return {
        ...state,
        downloadingModelId: action.modelId,
        modelDownloadProgress: 0,
        fasterWhisperModelsLoading: true,
        error: "",
      };
    case "faster_whisper_model_download_progress_updated":
      return {
        ...state,
        downloadingModelId: action.modelId,
        modelDownloadProgress: action.progress == null ? null : Math.max(0, Math.min(100, action.progress)),
      };
    case "faster_whisper_model_download_cancelled":
      return {
        ...state,
        downloadingModelId: null,
        modelDownloadProgress: null,
        fasterWhisperModelsLoading: false,
      };
    case "faster_whisper_models_loaded":
      return {
        ...state,
        fasterWhisperModels: action.models,
        fasterWhisperModelsLoading: false,
        downloadingModelId: null,
        modelDownloadProgress: null,
      };
    case "load_failed":
      return {
        ...state,
        loading: false,
        toolsLoading: false,
        summaryLoading: false,
        mindmapLoading: false,
        generatingVideoKey: null,
        generatingMindmapKey: null,
        generationProgress: null,
        downloadingModelId: null,
        modelDownloadProgress: null,
        error: action.message,
        fasterWhisperModelsLoading: false,
      };
    case "series_selected": {
      return {
        ...state,
        tools: null,
        selectedSeriesId: action.seriesId,
        selectedVideoId: null,
        selectedContextType: "series",
        selectedToolId: "series-home",
        summary: null,
        mindmap: null,
        selectedChapterId: null,
        selectedNodeId: null,
        generationProgress: null,
      };
    }
    case "library_home_entered":
      return {
        ...state,
        tools: null,
        selectedSeriesId: null,
        selectedVideoId: null,
        selectedContextType: "library",
        selectedToolId: "studio",
        summary: null,
        mindmap: null,
        selectedChapterId: null,
        selectedNodeId: null,
        toolsLoading: false,
        summaryLoading: false,
        mindmapLoading: false,
        generationProgress: null,
      };
    case "video_selected":
      return {
        ...state,
        selectedSeriesId: action.seriesId,
        selectedVideoId: action.videoId,
        selectedContextType: "video",
        selectedToolId: "studio",
        tools: null,
        summary: null,
        mindmap: null,
        selectedChapterId: null,
        selectedNodeId: null,
        generationProgress: null,
      };
    case "tool_selected":
      return {
        ...state,
        selectedToolId: action.toolId,
        error: "",
      };
    case "series_context_selected":
      return {
        ...state,
        selectedContextType: "series",
        selectedVideoId: null,
        selectedToolId: "series-home",
        tools: null,
        summary: null,
        mindmap: null,
        selectedChapterId: null,
        selectedNodeId: null,
        generationProgress: null,
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
    case "generation_started":
      return {
        ...state,
        generatingVideoKey: action.videoKey,
        generationProgress: null,
        error: "",
      };
    case "generation_progress_updated":
      return {
        ...state,
        generationProgress: action.progress == null ? null : Math.max(0, Math.min(100, action.progress)),
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
        generationProgress: null,
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
    let cancelled = false;
    dispatch({ type: "faster_whisper_models_loading_started" });
    loadFasterWhisperModels()
      .then((models) => {
        if (!cancelled) {
          dispatch({ type: "faster_whisper_models_loaded", models });
        }
      })
      .catch((error) => {
        if (!cancelled) {
          dispatch({
            type: "load_failed",
            message: error instanceof Error ? error.message : "语音模型列表加载失败",
          });
        }
      });

    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;

    loadWorkspaceSettings()
      .then((settings) => {
        if (!cancelled) {
          dispatch({ type: "workspace_settings_loaded", settings });
        }
      })
      .catch((error) => {
        if (!cancelled) {
          dispatch({
            type: "load_failed",
            message: error instanceof Error ? error.message : "设置加载失败",
          });
        }
      });

    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (typeof document === "undefined") {
      return;
    }
    document.documentElement.classList.toggle("dark", state.ui.theme === "dark");
  }, [state.ui.theme]);

  useEffect(() => {
    const selectedVideo = findVideoById(state.library, state.selectedSeriesId, state.selectedVideoId);
    if (!selectedVideo || state.selectedContextType !== "video") {
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
  }, [state.library, state.selectedSeriesId, state.selectedVideoId, state.selectedContextType]);

  useEffect(() => {
    const selectedVideo = findVideoById(state.library, state.selectedSeriesId, state.selectedVideoId);
    if (!selectedVideo || state.selectedContextType !== "video") {
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
  }, [state.library, state.selectedSeriesId, state.selectedVideoId, state.selectedContextType, state.tools?.overview.generated]);

  useEffect(() => {
    const selectedVideo = findVideoById(state.library, state.selectedSeriesId, state.selectedVideoId);
    if (
      !selectedVideo ||
      state.selectedContextType !== "video" ||
      state.selectedToolId !== "mindmap" ||
      !state.tools?.mindmap.generated
    ) {
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
  }, [state.library, state.selectedSeriesId, state.selectedVideoId, state.selectedContextType, state.selectedToolId, state.tools?.mindmap.generated]);

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

  function onSelectSeriesContext() {
    dispatch({ type: "series_context_selected" });
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

  async function onChangeSetting(key, value) {
    const nextUi = normalizeUiSettings({
      ...state.ui,
      [key]: value,
    });
    dispatch({ type: "workspace_settings_loaded", settings: nextUi });

    try {
      const savedSettings = await updateWorkspaceSettings(nextUi);
      dispatch({ type: "workspace_settings_loaded", settings: savedSettings });
      const models = await loadFasterWhisperModels();
      dispatch({ type: "faster_whisper_models_loaded", models });
    } catch (error) {
      dispatch({
        type: "load_failed",
        message: error instanceof Error ? error.message : "设置保存失败",
      });
    }
  }

  async function onResetSettings() {
    const nextUi = resetUiSettings();
    dispatch({ type: "workspace_settings_loaded", settings: nextUi });

    try {
      const savedSettings = await updateWorkspaceSettings(nextUi);
      dispatch({ type: "workspace_settings_loaded", settings: savedSettings });
      const models = await loadFasterWhisperModels();
      dispatch({ type: "faster_whisper_models_loaded", models });
    } catch (error) {
      dispatch({
        type: "load_failed",
        message: error instanceof Error ? error.message : "设置保存失败",
      });
    }
  }

  async function onDownloadFasterWhisperModel(modelId) {
    dispatch({ type: "faster_whisper_model_download_started", modelId });
    const unsubscribe = subscribeFasterWhisperModelDownloadProgress(modelId, (snapshot) => {
      if (snapshot.status === "running" || snapshot.status === "completed") {
        dispatch({
          type: "faster_whisper_model_download_progress_updated",
          modelId,
          progress: snapshot.progress,
        });
      }

      if (snapshot.status === "failed") {
        dispatch({
          type: "load_failed",
          message: snapshot.error ?? "语音模型下载失败",
        });
      }
      if (snapshot.status === "cancelled") {
        dispatch({ type: "faster_whisper_model_download_cancelled" });
      }
    });
    try {
      await downloadFasterWhisperModel(modelId);
      const savedSettings = await updateWorkspaceSettings({
        ...state.ui,
        asrModelQuality: modelId,
      });
      dispatch({ type: "workspace_settings_loaded", settings: savedSettings });
      const models = await loadFasterWhisperModels();
      dispatch({ type: "faster_whisper_models_loaded", models });
    } catch (error) {
      if (error instanceof Error && error.message.includes("409")) {
        dispatch({ type: "faster_whisper_model_download_cancelled" });
        return;
      }
      dispatch({
        type: "load_failed",
        message: error instanceof Error ? error.message : "语音模型下载失败",
      });
    } finally {
      unsubscribe();
    }
  }

  async function onCancelFasterWhisperModelDownload(modelId) {
    try {
      await cancelFasterWhisperModelDownload(modelId);
      dispatch({ type: "faster_whisper_model_download_cancelled" });
      const models = await loadFasterWhisperModels();
      dispatch({ type: "faster_whisper_models_loaded", models });
    } catch (error) {
      dispatch({
        type: "load_failed",
        message: error instanceof Error ? error.message : "取消语音模型下载失败",
      });
    }
  }

  async function onGenerateVideo() {
    if (!state.selectedSeriesId || !state.selectedVideoId) {
      return;
    }

    const seriesId = state.selectedSeriesId;
    const videoId = state.selectedVideoId;
    const videoKey = buildVideoKey(seriesId, videoId);
    dispatch({ type: "generation_started", videoKey });

    const unsubscribe = subscribeVideoGenerationProgress(seriesId, videoId, (snapshot) => {
      if (snapshot.status === "running" || snapshot.status === "completed") {
        dispatch({
          type: "generation_progress_updated",
          progress: snapshot.progress,
        });
      }

      if (snapshot.status === "failed") {
        dispatch({
          type: "load_failed",
          message: snapshot.error ?? "生成失败",
        });
      }
    });

    try {
      const summaryResult = await generateVideoSummary(seriesId, videoId, {
        transcriptEnhancementEnabled: state.ui.aiTranscriptEnhancement,
      });
      dispatch({
        type: "generation_succeeded",
        seriesId,
        videoId,
        summary: summaryResult,
      });
    } catch (error) {
      dispatch({
        type: "load_failed",
        message: error instanceof Error ? error.message : "生成失败",
      });
    } finally {
      unsubscribe();
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
    fasterWhisperModels: state.fasterWhisperModels,
    fasterWhisperModelsLoading: state.fasterWhisperModelsLoading,
    downloadingModelId: state.downloadingModelId,
    modelDownloadProgress: state.modelDownloadProgress,
    tools,
    summary,
    mindmap,
    activeSeries,
    selectedVideo,
    selectedNode,
    previewUrl,
    isGeneratingMindmapSelectedVideo,
    isGeneratingSelectedVideo,
    selectedContextType: state.selectedContextType,
    onSelectSeries,
    onEnterLibraryHome,
    onSelectVideo,
    onSelectSeriesContext,
    onSelectTool,
    onFocusNode,
    onGenerateVideo,
    onGenerateMindmap,
    onToggleSettingsPanel,
    onCloseSettingsPanel,
    onChangeSetting,
    onDownloadFasterWhisperModel,
    onCancelFasterWhisperModelDownload,
    onResetSettings,
  };
}

function buildVideoKey(seriesId, videoId) {
  if (!seriesId || !videoId) {
    return null;
  }
  return `${seriesId}/${videoId}`;
}
