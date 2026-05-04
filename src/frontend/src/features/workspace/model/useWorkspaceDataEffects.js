import { useEffect } from "react";

import {
  checkBackendHealth,
  loadAgentContextUsage,
  loadAgentMemoryStatus,
  loadAgentSessionRecovery,
  loadFasterWhisperModels,
  loadSeriesGenerationStatus,
  loadProviderSettings,
  loadVideoKnowledgeCards,
  loadVideoGenerationStatus,
  loadVideoMindmap,
  loadVideoNotes,
  loadVideoSummary,
  loadVideoTools,
  loadWorkspaceLibrary,
  loadWorkspaceSettings,
  subscribeSeriesGenerationProgress,
  subscribeVideoGenerationProgress,
} from "./workspaceApi";
import { buildAgentChatContextPayload } from "./workspaceChatRuntime";
import { BACKEND_HEALTH_RETRY_DELAY_MS } from "./workspaceControllerConstants";
import {
  buildSeriesGenerationTaskKey,
  buildVideoGenerationTaskKey,
  findVideoById,
  getGenerationTaskForSelection,
  hasRecoveredChatScope,
  isGenerationSnapshotActive,
} from "./workspaceState";

const generationSubscriptions = new Map();

function clearGenerationSubscription(taskKey) {
  const unsubscribe = generationSubscriptions.get(taskKey);
  if (typeof unsubscribe === "function") {
    unsubscribe();
  }
  generationSubscriptions.delete(taskKey);
}

function ensureVideoGenerationSubscription({ seriesId, videoId, dispatch }) {
  const taskKey = buildVideoGenerationTaskKey(seriesId, videoId);
  if (!taskKey || generationSubscriptions.has(taskKey)) {
    return;
  }
  const unsubscribe = subscribeVideoGenerationProgress(seriesId, videoId, (snapshot) => {
    dispatch({
      type: "generation_progress_updated",
      taskKey,
      mode: "video",
      seriesId,
      videoId,
      progress: snapshot.progress,
      snapshot,
      subscriptionActive: isGenerationSnapshotActive(snapshot),
    });
    if (snapshot.status === "completed" || snapshot.status === "failed" || snapshot.status === "cancelled") {
      clearGenerationSubscription(taskKey);
    }
  });
  generationSubscriptions.set(taskKey, unsubscribe);
}

function ensureSeriesGenerationSubscription({ seriesId, dispatch }) {
  const taskKey = buildSeriesGenerationTaskKey(seriesId);
  if (!taskKey || generationSubscriptions.has(taskKey)) {
    return;
  }
  const unsubscribe = subscribeSeriesGenerationProgress(seriesId, (snapshot) => {
    dispatch({
      type: "generation_progress_updated",
      taskKey,
      mode: "series",
      seriesId,
      videoId: null,
      progress: snapshot.progress,
      snapshot,
      subscriptionActive: isGenerationSnapshotActive(snapshot),
    });
    if (snapshot.status === "completed" || snapshot.status === "failed" || snapshot.status === "cancelled") {
      clearGenerationSubscription(taskKey);
    }
  });
  generationSubscriptions.set(taskKey, unsubscribe);
}

export function useWorkspaceDataEffects(state, dispatch) {
  useEffect(() => () => {
    for (const taskKey of generationSubscriptions.keys()) {
      clearGenerationSubscription(taskKey);
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    let timeoutId = null;

    const pollBackendHealth = async () => {
      try {
        await checkBackendHealth();
        if (!cancelled) {
          dispatch({ type: "backend_health_ready" });
        }
      } catch {
        if (cancelled) {
          return;
        }
        timeoutId = window.setTimeout(pollBackendHealth, BACKEND_HEALTH_RETRY_DELAY_MS);
      }
    };

    pollBackendHealth();

    return () => {
      cancelled = true;
      if (timeoutId != null) {
        window.clearTimeout(timeoutId);
      }
    };
  }, [dispatch]);

  useEffect(() => {
    if (!state.backendReady) {
      return;
    }

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
  }, [dispatch, state.backendReady]);

  useEffect(() => {
    if (!state.backendReady) {
      return;
    }

    let cancelled = false;
    let timeoutId = null;

    const pollMemoryStatus = async () => {
      try {
        const snapshot = await loadAgentMemoryStatus();
        if (cancelled) {
          return;
        }
        dispatch({ type: "knowledge_memory_status_loaded", snapshot });
        timeoutId = window.setTimeout(
          pollMemoryStatus,
          snapshot.status === "running" ? 1000 : 5000,
        );
      } catch {
        if (!cancelled) {
          timeoutId = window.setTimeout(pollMemoryStatus, 5000);
        }
      }
    };

    pollMemoryStatus();

    return () => {
      cancelled = true;
      if (timeoutId != null) {
        window.clearTimeout(timeoutId);
      }
    };
  }, [dispatch, state.backendReady]);

  useEffect(() => {
    if (!state.backendReady) {
      return;
    }

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
  }, [dispatch, state.backendReady]);

  useEffect(() => {
    if (!state.backendReady) {
      return;
    }

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
  }, [dispatch, state.backendReady]);

  useEffect(() => {
    if (!state.backendReady || !state.settingsPanelOpen) {
      return;
    }

    let cancelled = false;
    loadProviderSettings()
      .then((settings) => {
        if (!cancelled) {
          dispatch({ type: "provider_settings_loaded", settings });
        }
      })
      .catch((error) => {
        if (!cancelled) {
          dispatch({
            type: "load_failed",
            message: error instanceof Error ? error.message : "供应商设置加载失败",
          });
        }
      });

    return () => {
      cancelled = true;
    };
  }, [dispatch, state.backendReady, state.settingsPanelOpen]);

  useEffect(() => {
    if (typeof document === "undefined") {
      return;
    }
    const root = document.documentElement;
    const shouldAnimate = root.dataset.workspaceThemeReady === "true";
    if (shouldAnimate) {
      root.classList.add("theme-transitioning");
    }
    root.classList.toggle("dark", state.ui.theme === "dark");
    root.dataset.workspaceThemeReady = "true";
    if (!shouldAnimate) {
      return;
    }
    const timeoutId = window.setTimeout(() => {
      root.classList.remove("theme-transitioning");
    }, 560);
    return () => {
      window.clearTimeout(timeoutId);
      root.classList.remove("theme-transitioning");
    };
  }, [state.ui.theme]);

  useEffect(() => {
    if (!state.backendReady) {
      return;
    }
    if (state.selectedContextType === "video" && state.selectedSeriesId && state.selectedVideoId) {
      let cancelled = false;
      loadVideoGenerationStatus(state.selectedSeriesId, state.selectedVideoId)
        .then(({ snapshot }) => {
          if (cancelled) {
            return;
          }
          dispatch({
            type: "generation_status_loaded",
            taskKey: buildVideoGenerationTaskKey(state.selectedSeriesId, state.selectedVideoId),
            mode: "video",
            seriesId: state.selectedSeriesId,
            videoId: state.selectedVideoId,
            snapshot,
            subscriptionActive: isGenerationSnapshotActive(snapshot),
          });
        })
        .catch(() => {});

      return () => {
        cancelled = true;
      };
    }

    if (state.selectedContextType === "series" && state.selectedSeriesId) {
      let cancelled = false;
      loadSeriesGenerationStatus(state.selectedSeriesId)
        .then(({ snapshot }) => {
          if (cancelled) {
            return;
          }
          dispatch({
            type: "generation_status_loaded",
            taskKey: buildSeriesGenerationTaskKey(state.selectedSeriesId),
            mode: "series",
            seriesId: state.selectedSeriesId,
            videoId: null,
            snapshot,
            subscriptionActive: isGenerationSnapshotActive(snapshot),
          });
        })
        .catch(() => {});

      return () => {
        cancelled = true;
      };
    }
  }, [
    dispatch,
    state.backendReady,
    state.selectedContextType,
    state.selectedSeriesId,
    state.selectedVideoId,
  ]);

  useEffect(() => {
    const currentTask = getGenerationTaskForSelection(state);
    if (!currentTask) {
      return;
    }

    if (currentTask.mode === "video" && currentTask.seriesId && currentTask.videoId) {
      if (isGenerationSnapshotActive(currentTask.snapshot)) {
        ensureVideoGenerationSubscription({
          seriesId: currentTask.seriesId,
          videoId: currentTask.videoId,
          dispatch,
        });
      } else {
        clearGenerationSubscription(currentTask.taskKey);
      }
      return;
    }

    if (currentTask.mode === "series" && currentTask.seriesId) {
      if (isGenerationSnapshotActive(currentTask.snapshot)) {
        ensureSeriesGenerationSubscription({
          seriesId: currentTask.seriesId,
          dispatch,
        });
      } else {
        clearGenerationSubscription(currentTask.taskKey);
      }
    }
  }, [dispatch, state]);

  useEffect(() => {
    if (!state.library || !state.chatScopeKey || !state.chatBaseScopeKey) {
      return;
    }
    const sessionId = state.chatScopeKey;
    if (hasRecoveredChatScope(state.chatRecoveryByScope, sessionId)) {
      return;
    }
    const context = buildAgentChatContextPayload(
      state.library,
      state.selectedContextType,
      state.selectedSeriesId,
      state.selectedVideoId,
      state.selectedToolId,
    );

    let cancelled = false;
    dispatch({ type: "chat_recovery_started" });
    loadAgentSessionRecovery(sessionId, context)
      .then((recovery) => {
        if (!cancelled) {
          dispatch({
            type: "chat_recovery_loaded",
            chatScopeKey: sessionId,
            restored: recovery.restored,
            messages: recovery.messages,
          });
        }
      })
      .catch((error) => {
        if (!cancelled) {
          dispatch({
            type: "load_failed",
            message: error instanceof Error ? error.message : "会话恢复失败",
          });
        }
      });

    return () => {
      cancelled = true;
    };
  }, [
    dispatch,
    state.library,
    state.chatScopeKey,
    state.chatBaseScopeKey,
    state.selectedContextType,
    state.selectedSeriesId,
    state.selectedVideoId,
    state.selectedToolId,
    state.chatRecoveryByScope,
  ]);

  useEffect(() => {
    if (!state.library || !state.chatScopeKey || !state.chatBaseScopeKey) {
      return;
    }
    const sessionId = state.chatScopeKey;
    const context = buildAgentChatContextPayload(
      state.library,
      state.selectedContextType,
      state.selectedSeriesId,
      state.selectedVideoId,
      state.selectedToolId,
    );

    let cancelled = false;
    dispatch({ type: "context_usage_loading_started" });
    loadAgentContextUsage(sessionId, context)
      .then((usage) => {
        if (!cancelled) {
          dispatch({
            type: "context_usage_loaded",
            chatScopeKey: sessionId,
            currentScopeKey: state.chatScopeKey,
            usage,
          });
        }
      })
      .catch((error) => {
        if (!cancelled) {
          dispatch({
            type: "load_failed",
            message: error instanceof Error ? error.message : "上下文预算加载失败",
          });
        }
      });

    return () => {
      cancelled = true;
    };
  }, [
    dispatch,
    state.library,
    state.chatScopeKey,
    state.chatBaseScopeKey,
    state.selectedContextType,
    state.selectedSeriesId,
    state.selectedVideoId,
    state.selectedToolId,
  ]);

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
  }, [dispatch, state.library, state.selectedSeriesId, state.selectedVideoId, state.selectedContextType]);

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
  }, [dispatch, state.library, state.selectedSeriesId, state.selectedVideoId, state.selectedContextType, state.tools?.overview.generated]);

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
  }, [dispatch, state.library, state.selectedSeriesId, state.selectedVideoId, state.selectedContextType, state.selectedToolId, state.tools?.mindmap.generated]);

  useEffect(() => {
    const selectedVideo = findVideoById(state.library, state.selectedSeriesId, state.selectedVideoId);
    if (
      !selectedVideo ||
      state.selectedContextType !== "video" ||
      state.selectedToolId !== "knowledge-cards" ||
      !state.tools?.knowledgeCards.generated
    ) {
      dispatch({ type: "knowledge_cards_cleared" });
      return;
    }

    let cancelled = false;
    dispatch({ type: "knowledge_cards_loading_started" });
    loadVideoKnowledgeCards(state.selectedSeriesId, state.selectedVideoId)
      .then((cards) => {
        if (!cancelled) {
          dispatch({ type: "knowledge_cards_loaded", cards });
        }
      })
      .catch((error) => {
        if (!cancelled) {
          dispatch({
            type: "load_failed",
            message: error instanceof Error ? error.message : "知识卡片加载失败",
          });
        }
      });

    return () => {
      cancelled = true;
    };
  }, [dispatch, state.library, state.selectedSeriesId, state.selectedVideoId, state.selectedContextType, state.selectedToolId, state.tools?.knowledgeCards.generated]);

  useEffect(() => {
    const selectedVideo = findVideoById(state.library, state.selectedSeriesId, state.selectedVideoId);
    if (
      !selectedVideo ||
      state.selectedContextType !== "video" ||
      state.selectedToolId !== "notes"
    ) {
      dispatch({ type: "notes_cleared" });
      return;
    }

    let cancelled = false;
    dispatch({ type: "notes_loading_started" });
    loadVideoNotes(state.selectedSeriesId, state.selectedVideoId)
      .then((notes) => {
        if (!cancelled) {
          dispatch({ type: "notes_loaded", notes });
        }
      })
      .catch((error) => {
        if (!cancelled) {
          dispatch({
            type: "load_failed",
            message: error instanceof Error ? error.message : "笔记加载失败",
          });
        }
      });

    return () => {
      cancelled = true;
    };
  }, [dispatch, state.library, state.selectedSeriesId, state.selectedVideoId, state.selectedContextType, state.selectedToolId]);
}
