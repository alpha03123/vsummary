import {useEffect} from 'react';
export function createLocalWorkspaceEffects(api){
const {loadFasterWhisperModels,loadProviderSettings,loadProviderUsage,loadRagModels,loadWorkspaceSettings}=api;
return function LocalWorkspaceEffects({state,dispatch}){
useEffect(() => {
    if (!state.backendReady) {
      return;
    }

    let cancelled = false;
    let timeoutId = null;

    const pollRagModels = async () => {
      try {
        const models = await loadRagModels();
        if (cancelled) {
          return;
        }
        dispatch({ type: "rag_models_loaded", models });
        const hasRunningDownload = models.some((model) => model.status === "running");
        timeoutId = window.setTimeout(pollRagModels, hasRunningDownload ? 1000 : 5000);
      } catch {
        if (!cancelled) {
          timeoutId = window.setTimeout(pollRagModels, 5000);
        }
      }
    };

    dispatch({ type: "rag_models_loading_started" });
    pollRagModels();

    return () => {
      cancelled = true;
      if (timeoutId != null) {
        window.clearTimeout(timeoutId);
      }
    };
  }, [dispatch, state.backendReady]);
useEffect(() => {
    if (
      !state.backendReady
      || state.ui.asrProvider === "aliyun_bailian"
      || (
        state.ui.asrProvider === "faster_whisper"
        && state.ui.runtimeCapabilities?.fasterWhisperAvailable === false
      )
    ) {
      return;
    }

    let cancelled = false;
    let timeoutId = null;

    const pollFasterWhisperModels = async () => {
      try {
        const models = await loadFasterWhisperModels(state.ui.asrProvider);
        if (cancelled) {
          return;
        }
        dispatch({ type: "faster_whisper_models_loaded", models });
        if (models.some((model) => model.status === "running")) {
          timeoutId = window.setTimeout(pollFasterWhisperModels, 1000);
        }
      } catch (error) {
        if (!cancelled) {
          dispatch({
            type: "load_failed",
            message: error instanceof Error ? error.message : "语音模型列表加载失败",
          });
        }
      }
    };

    dispatch({ type: "faster_whisper_models_loading_started" });
    pollFasterWhisperModels();

    return () => {
      cancelled = true;
      if (timeoutId != null) {
        window.clearTimeout(timeoutId);
      }
    };
  }, [dispatch, state.backendReady, state.ui.asrProvider]);
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
    if (!state.backendReady || (!state.settingsPanelOpen && !state.usagePageOpen)) {
      return;
    }

    let cancelled = false;
    const range = state.providerUsageRange ?? "7d";
    dispatch({ type: "provider_usage_loading_started", range });
    loadProviderUsage(range)
      .then((usage) => {
        if (!cancelled) {
          dispatch({ type: "provider_usage_loaded", range, usage });
        }
      })
      .catch((error) => {
        if (!cancelled) {
          dispatch({
            type: "provider_usage_load_failed",
            message: error instanceof Error ? error.message : "用量统计加载失败",
          });
        }
      });

    return () => {
      cancelled = true;
    };
  }, [dispatch, state.backendReady, state.settingsPanelOpen, state.usagePageOpen, state.providerUsageRange]);
return null;
};
}
