import {
  downloadFasterWhisperModel,
  downloadRagModel,
  loadFasterWhisperModels,
  loadOpenaiApiKey,
  loadRagModels,
  subscribeFasterWhisperModelDownloadProgress,
  subscribeRagModelDownloadProgress,
  testProviderSettings,
  updateProviderSettings,
  updateWorkspaceSettings,
} from "./workspaceApi";
import { normalizeUiSettings, resetUiSettings } from "./workspaceState";

export function createWorkspaceSettingsActions({ state, dispatch }) {
  function onToggleSettingsPanel() {
    dispatch({ type: "settings_panel_toggled" });
  }

  function onOpenSettingsPanel(initialTab = "general") {
    dispatch({ type: "settings_panel_opened", initialTab });
  }

  function onCloseSettingsPanel() {
    dispatch({ type: "settings_panel_closed" });
  }

  async function onChangeSetting(key, value) {
    if (key === "openaiBaseUrl") {
      dispatch({ type: "workspace_setting_edited", key, value });
      if (!isSaveableOpenaiBaseUrl(value)) {
        return;
      }
      try {
        await updateProviderSettings({
          ...normalizeUiSettings(state.ui),
          openaiBaseUrl: value,
        });
      } catch (error) {
        dispatch({
          type: "load_failed",
          message: error instanceof Error ? error.message : "设置保存失败",
        });
      }
      return;
    }

    const nextUi = normalizeUiSettings({
      ...state.ui,
      [key]: value,
    });
    dispatch({ type: "workspace_settings_loaded", settings: nextUi });

    if (key === "openaiApiKey") {
      return;
    }

    try {
      if (key === "llmProvider" || key === "openaiBaseUrl" || key === "openaiModel" || key === "hfEndpoint") {
        const savedProviderSettings = await updateProviderSettings(nextUi);
        dispatch({
          type: "workspace_settings_loaded",
          settings: {
            ...nextUi,
            ...savedProviderSettings,
            openaiApiKey: "",
          },
        });
      } else {
        const savedSettings = await updateWorkspaceSettings(nextUi);
        dispatch({
          type: "workspace_settings_loaded",
          settings: {
            ...state.ui,
            ...savedSettings,
          },
        });
        const models = await loadFasterWhisperModels();
        dispatch({ type: "faster_whisper_models_loaded", models });
      }
    } catch (error) {
      dispatch({
        type: "load_failed",
        message: error instanceof Error ? error.message : "设置保存失败",
      });
    }
  }

  async function onSaveApiKey() {
    const nextUi = normalizeUiSettings(state.ui);
    if (!nextUi.openaiApiKey.trim()) {
      return;
    }
    try {
      const savedProviderSettings = await updateProviderSettings(nextUi);
      dispatch({
        type: "workspace_settings_loaded",
        settings: {
          ...nextUi,
          ...savedProviderSettings,
          openaiApiKey: "",
        },
      });
    } catch (error) {
      dispatch({
        type: "load_failed",
        message: error instanceof Error ? error.message : "API Key 保存失败",
      });
    }
  }

  async function onRevealOpenaiApiKey() {
    try {
      const openaiApiKey = await loadOpenaiApiKey();
      dispatch({
        type: "workspace_settings_loaded",
        settings: {
          ...state.ui,
          openaiApiKey,
        },
      });
      return openaiApiKey;
    } catch (error) {
      const message = error instanceof Error ? error.message : "API Key 读取失败";
      dispatch({ type: "load_failed", message });
      return "";
    }
  }

  async function onTestProviderConnection() {
    const nextUi = normalizeUiSettings(state.ui);
    try {
      const result = await testProviderSettings(nextUi);
      return {
        ok: result.ok === true,
        message: typeof result.message === "string" ? result.message : "模型连接成功",
      };
    } catch (error) {
      const message = toProviderTestErrorMessage(error);
      dispatch({ type: "load_failed", message });
      return {
        ok: false,
        message,
      };
    }
  }

  async function onResetSettings() {
    const nextUi = normalizeUiSettings({
      ...state.ui,
      ...resetUiSettings(),
      llmProvider: state.ui.llmProvider,
      openaiBaseUrl: state.ui.openaiBaseUrl,
      openaiModel: state.ui.openaiModel,
      hasOpenaiApiKey: state.ui.hasOpenaiApiKey,
      openaiApiKeyMasked: state.ui.openaiApiKeyMasked,
      openaiApiKey: "",
    });
    dispatch({ type: "workspace_settings_loaded", settings: nextUi });

    try {
      const savedSettings = await updateWorkspaceSettings(nextUi);
      dispatch({
        type: "workspace_settings_loaded",
        settings: {
          ...nextUi,
          ...savedSettings,
        },
      });
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
    let unsubscribe = () => {};
    const downloadCompleted = new Promise((resolve, reject) => {
      unsubscribe = subscribeFasterWhisperModelDownloadProgress(modelId, (snapshot) => {
      if (snapshot.status === "running" || snapshot.status === "completed") {
        dispatch({
          type: "faster_whisper_model_download_progress_updated",
          modelId,
          status: snapshot.status,
          progress: snapshot.progress,
        });
      }

      if (snapshot.status === "failed") {
        reject(new Error(snapshot.error ?? "语音模型下载失败"));
      }
      if (snapshot.status === "completed") {
        resolve();
      }
      });
    });
    try {
      await downloadFasterWhisperModel(modelId);
      await downloadCompleted;
      const savedSettings = await updateWorkspaceSettings({
        ...state.ui,
        asrModelQuality: modelId,
      });
      dispatch({ type: "workspace_settings_loaded", settings: savedSettings });
      const models = await loadFasterWhisperModels();
      dispatch({ type: "faster_whisper_models_loaded", models });
    } catch (error) {
      dispatch({
        type: "load_failed",
        message: error instanceof Error ? error.message : "语音模型下载失败",
      });
    } finally {
      unsubscribe();
    }
  }

  async function onDownloadRagModel(modelKey) {
    dispatch({ type: "rag_model_download_started", modelKey });
    let unsubscribe = () => {};
    const downloadCompleted = new Promise((resolve, reject) => {
      unsubscribe = subscribeRagModelDownloadProgress(modelKey, (snapshot) => {
        if (snapshot.status === "running" || snapshot.status === "completed") {
          dispatch({
            type: "rag_model_download_progress_updated",
            modelKey,
            status: snapshot.status,
            progress: snapshot.progress,
            detail: snapshot.detail,
            error: snapshot.error,
          });
        }

        if (snapshot.status === "failed") {
          reject(new Error(snapshot.error ?? "RAG 模型下载失败"));
        }
        if (snapshot.status === "completed") {
          resolve();
        }
      });
    });
    try {
      await downloadRagModel(modelKey);
      await downloadCompleted;
      const models = await loadRagModels();
      dispatch({ type: "rag_models_loaded", models });
    } catch (error) {
      dispatch({
        type: "load_failed",
        message: error instanceof Error ? error.message : "RAG 模型下载失败",
      });
    } finally {
      unsubscribe();
    }
  }

  return {
    onToggleSettingsPanel,
    onOpenSettingsPanel,
    onCloseSettingsPanel,
    onChangeSetting,
    onSaveApiKey,
    onRevealOpenaiApiKey,
    onTestProviderConnection,
    onResetSettings,
    onDownloadFasterWhisperModel,
    onDownloadRagModel,
  };
}

export function toProviderTestErrorMessage(error) {
  if (error instanceof DOMException && error.name === "AbortError") {
    return "模型超时";
  }
  const message = error instanceof Error ? error.message : "模型连接测试失败";
  if (/^\d{3}\s+模型超时$/.test(message)) {
    return "模型超时";
  }
  return message;
}

export function isSaveableOpenaiBaseUrl(value) {
  const normalized = typeof value === "string" ? value.trim() : "";
  if (!normalized.startsWith("http://") && !normalized.startsWith("https://")) {
    return false;
  }
  try {
    const parsed = new URL(normalized);
    return Boolean(parsed.hostname);
  } catch {
    return false;
  }
}
