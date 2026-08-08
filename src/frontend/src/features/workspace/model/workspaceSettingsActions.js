import {
  cancelRagModelDownload,
  cancelFasterWhisperModelDownload,
  downloadFasterWhisperModel,
  downloadRagModel,
  loadAsrApiKey,
  loadFasterWhisperModels,
  loadOpenaiApiKey,
  loadRagModels,
  subscribeFasterWhisperModelDownloadProgress,
  subscribeRagModelDownloadProgress,
  testAsrSettings,
  testProviderSettings,
  updateProviderSettings,
  updateWorkspaceSettings,
} from "./workspaceApi";
import { MODEL_DOWNLOAD_FAILED_MESSAGE } from "./modelDownloadMessages";
import { normalizeUiSettings, resetUiSettings } from "./workspaceState";

const PROVIDER_TEXT_SETTING_KEYS = new Set(["openaiBaseUrl", "openaiModel", "hfEndpoint"]);
const ASR_TEXT_SETTING_KEYS = new Set(["asrBaseUrl", "asrCloudModel"]);
const DOWNLOAD_FAILURE_VISIBLE_MS = 4000;
const HUGGINGFACE_OFFICIAL_ENDPOINT = "https://huggingface.co";

function isCompletedDownloadStatus(payload) {
  return payload?.status === "completed" || payload?.downloaded === true;
}

function isFailedDownloadStatus(payload) {
  return payload?.status === "failed";
}

function isCancelledDownloadStatus(payload) {
  return payload?.status === "cancelled";
}

function canLoadLocalAsrModels(provider, runtimeCapabilities) {
  return provider !== "aliyun_bailian" && (
    provider !== "faster_whisper" || runtimeCapabilities?.fasterWhisperAvailable !== false
  );
}

function scheduleFailureClear(dispatch, action) {
  window.setTimeout(() => dispatch(action), DOWNLOAD_FAILURE_VISIBLE_MS);
}

export function createWorkspaceSettingsActions({ state, dispatch }) {
  const currentAsrProvider = () => state.ui.asrProvider || "faster_whisper";

  function onToggleSettingsPanel() {
    dispatch({ type: "settings_panel_toggled" });
  }

  function onOpenSettingsPanel(initialTab = "general") {
    dispatch({ type: "settings_panel_opened", initialTab });
  }

  function onCloseSettingsPanel() {
    dispatch({ type: "settings_panel_closed" });
  }

  function onOpenUsagePage() {
    dispatch({ type: "usage_page_opened" });
  }

  function onCloseUsagePage() {
    dispatch({ type: "usage_page_closed" });
  }

  function onChangeProviderUsageRange(range) {
    dispatch({ type: "provider_usage_range_changed", range });
  }

  async function onChangeSetting(key, value) {
    if (PROVIDER_TEXT_SETTING_KEYS.has(key) || ASR_TEXT_SETTING_KEYS.has(key)) {
      dispatch({ type: "workspace_setting_edited", key, value });
      return;
    }

    if (key === "asrProvider" && value === "faster_whisper" && state.ui.runtimeCapabilities?.fasterWhisperAvailable === false) {
      dispatch({ type: "load_failed", message: state.ui.runtimeCapabilities.unavailableReason });
      return;
    }
    if (key === "ragEmbeddingDevice" && value === "gpu" && state.ui.runtimeCapabilities?.gpuEmbeddingAvailable === false) {
      dispatch({ type: "load_failed", message: state.ui.runtimeCapabilities.unavailableReason });
      return;
    }

    let nextUi = normalizeUiSettings({
      ...state.ui,
      [key]: value,
    });
    if (key === "asrProvider" && value !== "aliyun_bailian") {
      try {
        const models = await loadFasterWhisperModels(value);
        const recommendedModel = models.find((model) => model.recommended) ?? models[0];
        if (!recommendedModel) {
          throw new Error("当前 ASR provider 未提供可用模型");
        }
        nextUi = { ...nextUi, asrModelQuality: recommendedModel.id };
        dispatch({ type: "faster_whisper_models_loaded", models });
      } catch (error) {
        dispatch({
          type: "load_failed",
          message: error instanceof Error ? error.message : "语音模型列表加载失败",
        });
        return;
      }
    }
    dispatch({ type: "workspace_settings_loaded", settings: nextUi });

    if (key === "openaiApiKey" || key === "asrApiKey") {
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
        if (canLoadLocalAsrModels(savedSettings.asrProvider, savedSettings.runtimeCapabilities)) {
          const models = await loadFasterWhisperModels(savedSettings.asrProvider);
          dispatch({ type: "faster_whisper_models_loaded", models });
        }
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

  async function onSaveAsrSettings() {
    const nextUi = normalizeUiSettings(state.ui);
    if (nextUi.asrBaseUrl && !isSaveableOpenaiBaseUrl(nextUi.asrBaseUrl)) {
      dispatch({ type: "load_failed", message: "ASR API 地址必须包含 http:// 或 https://。" });
      return;
    }
    try {
      const savedSettings = await updateWorkspaceSettings(nextUi);
      dispatch({
        type: "workspace_settings_loaded",
        settings: {
          ...nextUi,
          ...savedSettings,
          asrApiKey: "",
        },
      });
    } catch (error) {
      dispatch({
        type: "load_failed",
        message: error instanceof Error ? error.message : "ASR 设置保存失败",
      });
    }
  }

  async function onRevealAsrApiKey() {
    try {
      const asrApiKey = await loadAsrApiKey();
      dispatch({
        type: "workspace_settings_loaded",
        settings: {
          ...state.ui,
          asrApiKey,
        },
      });
      return asrApiKey;
    } catch (error) {
      const message = error instanceof Error ? error.message : "ASR API Key 读取失败";
      dispatch({ type: "load_failed", message });
      return "";
    }
  }

  async function onSaveProviderSettings() {
    const normalizedUi = normalizeUiSettings(state.ui);
    const nextUi = {
      ...normalizedUi,
      hfEndpoint: normalizedUi.hfEndpoint || HUGGINGFACE_OFFICIAL_ENDPOINT,
    };
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

  async function onTestAsrConnection() {
    const nextUi = normalizeUiSettings(state.ui);
    try {
      const result = await testAsrSettings(nextUi);
      return {
        ok: result.ok === true,
        message: typeof result.message === "string" ? result.message : "ASR 连接正常",
      };
    } catch (error) {
      const message = toAsrTestErrorMessage(error);
      dispatch({ type: "load_failed", message });
      return {
        ok: false,
        message,
      };
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
      asrApiKey: "",
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
      if (canLoadLocalAsrModels(nextUi.asrProvider, nextUi.runtimeCapabilities)) {
        const models = await loadFasterWhisperModels(nextUi.asrProvider);
        dispatch({ type: "faster_whisper_models_loaded", models });
      }
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
    let cancelled = false;
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
      unsubscribe = subscribeFasterWhisperModelDownloadProgress(currentAsrProvider(), modelId, (snapshot) => {
        if (
          snapshot.status === "running" ||
          snapshot.status === "cancelling" ||
          snapshot.status === "completed" ||
          snapshot.status === "cancelled"
        ) {
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
        if (snapshot.status === "cancelled") {
          cancelled = true;
          resolve();
        }
      });
    });
    try {
      const started = await downloadFasterWhisperModel(currentAsrProvider(), modelId);
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
      } else if (isCancelledDownloadStatus(started)) {
        cancelled = true;
        dispatch({
          type: "faster_whisper_model_download_progress_updated",
          modelId,
          status: "cancelled",
          progress: null,
        });
      } else {
        await downloadCompleted;
      }
      if (!cancelled && state.ui.asrModelQuality === modelId) {
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
      if (canLoadLocalAsrModels(currentAsrProvider(), state.ui.runtimeCapabilities)) {
        const models = await loadFasterWhisperModels(currentAsrProvider());
        dispatch({ type: "faster_whisper_models_loaded", models });
      }
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

  async function onCancelFasterWhisperModelDownload(modelId) {
    dispatch({ type: "faster_whisper_model_download_cancel_requested", modelId });
    try {
      await cancelFasterWhisperModelDownload(currentAsrProvider(), modelId);
    } catch (error) {
      const message = error instanceof Error ? error.message : "语音模型取消失败";
      dispatch({
        type: "load_failed",
        message,
      });
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
        if (
          snapshot.status === "running" ||
          snapshot.status === "cancelling" ||
          snapshot.status === "completed" ||
          snapshot.status === "cancelled"
        ) {
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
        if (snapshot.status === "cancelled") {
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
      } else if (isCancelledDownloadStatus(started)) {
        dispatch({
          type: "rag_model_download_progress_updated",
          modelKey,
          status: "cancelled",
          progress: null,
          detail: started.detail,
          error: null,
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

  async function onCancelRagModelDownload(modelKey) {
    dispatch({ type: "rag_model_download_cancel_requested", modelKey });
    try {
      await cancelRagModelDownload(modelKey);
    } catch (error) {
      const message = error instanceof Error ? error.message : "RAG 模型取消失败";
      dispatch({ type: "load_failed", message });
    }
  }

  return {
    onToggleSettingsPanel,
    onOpenSettingsPanel,
    onCloseSettingsPanel,
    onOpenUsagePage,
    onCloseUsagePage,
    onChangeSetting,
    onChangeProviderUsageRange,
    onSaveProviderSettings,
    onSaveApiKey,
    onSaveAsrSettings,
    onRevealAsrApiKey,
    onTestAsrConnection,
    onRevealOpenaiApiKey,
    onTestProviderConnection,
    onResetSettings,
    onDownloadFasterWhisperModel,
    onCancelFasterWhisperModelDownload,
    onDownloadRagModel,
    onCancelRagModelDownload,
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

export function toAsrTestErrorMessage(error) {
  if (error instanceof DOMException && error.name === "AbortError") {
    return "ASR 连接测试超时";
  }
  const message = error instanceof Error ? error.message : "ASR 连接测试失败";
  if (/^\d{3}\s+/.test(message)) {
    return message.replace(/^\d{3}\s+/, "");
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
