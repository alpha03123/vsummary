import { useEffect, useMemo, useReducer } from "react";

import { loadWorkspaceFromLocation } from "./workspaceApi";
import { findChapterForNode, findNodeById } from "./workspaceTree";
import {
  createInitialWorkspaceState,
  createLoadedState,
  persistUiSettings,
  resetUiSettings,
} from "./workspaceState";

function workspaceReducer(state, action) {
  switch (action.type) {
    case "loaded":
      return createLoadedState(action.summary, action.library, state);
    case "load_failed":
      return {
        ...state,
        loading: false,
        error: action.message,
      };
    case "loading_started":
      return {
        ...state,
        loading: true,
        error: "",
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
    case "mindmap_toggled":
      return {
        ...state,
        ui: {
          ...state.ui,
          mindmapVisible: !state.ui.mindmapVisible,
        },
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
    default:
      return state;
  }
}

export function useWorkspaceController() {
  const [state, dispatch] = useReducer(workspaceReducer, undefined, createInitialWorkspaceState);

  useEffect(() => {
    let cancelled = false;

    loadWorkspaceFromLocation()
      .then(({ summary, library }) => {
        if (!cancelled) {
          dispatch({ type: "loaded", summary, library });
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

  const summary = state.summary;
  const activeSeries = state.library?.series?.[0] ?? null;
  const selectedNode = useMemo(
    () => findNodeById(summary?.mindmap, state.selectedNodeId),
    [summary?.mindmap, state.selectedNodeId],
  );

  function onFocusChapter(chapterId) {
    dispatch({ type: "chapter_selected", chapterId });

    requestAnimationFrame(() => {
      document.getElementById(chapterId)?.scrollIntoView({ behavior: "smooth", block: "start" });
    });
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

  function onToggleMindmapVisibility() {
    dispatch({ type: "mindmap_toggled" });
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

  return {
    state,
    ui: state.ui,
    summary,
    activeSeries,
    selectedNode,
    onFocusChapter,
    onFocusNode,
    onToggleMindmapVisibility,
    onToggleSettingsPanel,
    onCloseSettingsPanel,
    onChangeSetting,
    onResetSettings,
  };
}
