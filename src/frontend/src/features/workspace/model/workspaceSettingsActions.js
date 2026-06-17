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
import { MODEL_DOWNLOAD_FAILED_MESSAGE } from "./modelDownloadMessages";
import { normalizeUiSettings, resetUiSettings } from "./workspaceState";

const PROVIDER_TEXT_SETTING_KEYS = new Set(["openaiBaseUrl", "openaiModel", "hfEndpoint"]);
const DEFAULT_BASE_URL_BY_PROVIDER = {
  deepseek: "https://api.deepseek.com",
  ollama: "http://localhost:11434",
};
const DOWNLOAD_FAILURE_VISIBLE_MS = 4000;

function isCompletedDownloadStatus(payload) {
  return payload?.status === "completed" || payload?.downloaded === true;
}

function isFailedDownloadStatus(payload) {
  return payload?.status === "failed";
}

function scheduleFailureClear(dispatch, action) {
  window.setTimeout(() => dispatch(action), DOWNLOAD_FAILURE_VISIBLE_MS);
}

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
    if (PROVIDER_TEXT_SETTING_KEYS.has(key)) {
      dispatch({ type: "workspace_setting_edited", key, value });
      return;
    }

    const nextValue =
      key === "llmProvider" && !state.ui.openaiBaseUrl?.trim()
        ? {
            [key]: value,
            openaiBaseUrl: DEFAULT_BASE_URL_BY_PROVIDER[value] ?? state.ui.openaiBaseUrl,
          }
        : { [key]: value };
    const nextUi = normalizeUiSettings({
      ...state.ui,
      ...nextValue,
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
            ...nextUi,
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

  async function onSaveProviderSettings() {
    const nextUi = normalizeUiSettings(state.ui);
    if (nextUi.openaiBaseUrl && !isSaveableOpenaiBaseUrl(nextUi.openaiBaseUrl)) {
      dispatch({ type: "load_failed", message: "模型接口地址必须包含 http:// 或 https://。" });
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
        message: error instanceof Error ? error.message : "设置保存失败",
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
    let failedDispatched = false;
    const dispatchFailure = (message) => {
      failedDispatched = true;
      dispatch({
        type: "faster_whisper_model_download_failed",
        modelId,
        message,
      });
      scheduleFailureClear(dispatch, {
        type: "faster_whisper_model_download_failure_cleared",
        modelId,
      });
    };
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
          const message = snapshot.error || MODEL_DOWNLOAD_FAILED_MESSAGE;
          dispatchFailure(message);
          reject(new Error(message));
        }
        if (snapshot.status === "completed") {
          resolve();
        }
      });
    });
    try {
      const started = await downloadFasterWhisperModel(modelId);
      if (isFailedDownloadStatus(started)) {
        throw new Error(started.error || MODEL_DOWNLOAD_FAILED_MESSAGE);
      }
      if (isCompletedDownloadStatus(started)) {
        dispatch({
          type: "faster_whisper_model_download_progress_updated",
          modelId,
          status: "completed",
          progress: 100,
        });
      } else {
        await downloadCompleted;
      }
      if (state.ui.asrModelQuality === modelId) {
        const savedSettings = await updateWorkspaceSettings({
          ...state.ui,
          asrModelQuality: modelId,
        });
        dispatch({
          type: "workspace_settings_loaded",
          settings: {
            ...state.ui,
            ...savedSettings,
          },
        });
      }
      const models = await loadFasterWhisperModels();
      dispatch({ type: "faster_whisper_models_loaded", models });
    } catch (error) {
      const message = error instanceof Error ? error.message : "语音模型下载失败";
      if (!failedDispatched) {
        dispatchFailure(message);
      }
      dispatch({
        type: "load_failed",
        message,
      });
    } finally {
      unsubscribe();
    }
  }

  async function onDownloadRagModel(modelKey) {
    dispatch({ type: "rag_model_download_started", modelKey });
    let unsubscribe = () => {};
    let failedDispatched = false;
    const dispatchFailure = (message) => {
      failedDispatched = true;
      dispatch({
        type: "rag_model_download_failed",
        modelKey,
        message,
      });
      scheduleFailureClear(dispatch, {
        type: "rag_model_download_failure_cleared",
        modelKey,
      });
    };
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
          const message = snapshot.error || MODEL_DOWNLOAD_FAILED_MESSAGE;
          dispatchFailure(message);
          reject(new Error(message));
        }
        if (snapshot.status === "completed") {
          resolve();
        }
      });
    });
    try {
      const started = await downloadRagModel(modelKey);
      if (isFailedDownloadStatus(started)) {
        throw new Error(started.error || MODEL_DOWNLOAD_FAILED_MESSAGE);
      }
      if (isCompletedDownloadStatus(started)) {
        dispatch({
          type: "rag_model_download_progress_updated",
          modelKey,
          status: "completed",
          progress: 100,
          detail: started.detail,
          error: started.error,
        });
      } else {
        await downloadCompleted;
      }
      const models = await loadRagModels();
      dispatch({ type: "rag_models_loaded", models });
    } catch (error) {
      const message = error instanceof Error ? error.message : "RAG 模型下载失败";
      if (!failedDispatched) {
        dispatchFailure(message);
      }
      dispatch({
        type: "load_failed",
        message,
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
    onSaveProviderSettings,
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
