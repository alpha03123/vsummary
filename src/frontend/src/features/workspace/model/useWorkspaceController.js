import { useEffect, useReducer } from "react";

import { generateVideoSummary, loadVideoSummary, loadWorkspaceLibrary } from "./workspaceApi";
import {
  createInitialWorkspaceState,
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
        summaryLoading: false,
        generatingVideoKey: null,
        error: action.message,
      };
    case "series_selected": {
      const series = findSeriesById(state.library, action.seriesId);
      return {
        ...state,
        selectedSeriesId: action.seriesId,
        selectedVideoId: series?.videos?.[0]?.id ?? null,
        summary: null,
        selectedChapterId: null,
      };
    }
    case "video_selected":
      return {
        ...state,
        selectedSeriesId: action.seriesId,
        selectedVideoId: action.videoId,
        summary: null,
        selectedChapterId: null,
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
    case "chapter_selected":
      return {
        ...state,
        selectedChapterId: action.chapterId,
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
        generatingVideoKey: null,
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
      dispatch({ type: "summary_cleared" });
      return;
    }
    if (!selectedVideo.processed) {
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
  }, [state.library, state.selectedSeriesId, state.selectedVideoId]);

  const summary = state.summary;
  const activeSeries = findSeriesById(state.library, state.selectedSeriesId);
  const selectedVideo = findVideoById(state.library, state.selectedSeriesId, state.selectedVideoId);
  const isGeneratingSelectedVideo =
    state.generatingVideoKey != null &&
    state.generatingVideoKey === buildVideoKey(state.selectedSeriesId, state.selectedVideoId);

  function onSelectSeries(seriesId) {
    dispatch({ type: "series_selected", seriesId });
  }

  function onSelectVideo(seriesId, videoId) {
    dispatch({ type: "video_selected", seriesId, videoId });
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

  return {
    state,
    ui: state.ui,
    summary,
    activeSeries,
    selectedVideo,
    isGeneratingSelectedVideo,
    onSelectSeries,
    onSelectVideo,
    onGenerateVideo,
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
