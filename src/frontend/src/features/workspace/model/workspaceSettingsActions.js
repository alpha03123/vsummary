import {
  cancelFasterWhisperModelDownload,
  cancelRagModelDownload,
  downloadFasterWhisperModel,
  downloadRagModel,
  loadFasterWhisperModels,
  loadRagModels,
  subscribeFasterWhisperModelDownloadProgress,
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

  async function onTestProviderConnection() {
    const nextUi = normalizeUiSettings(state.ui);
    try {
      const result = await testProviderSettings(nextUi);
      return {
        ok: result.ok === true,
        message: typeof result.message === "string" ? result.message : "模型连接成功",
      };
    } catch (error) {
      const message = error instanceof Error ? error.message : "模型连接测试失败";
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
      if (snapshot.status === "running" || snapshot.status === "cancelling" || snapshot.status === "completed") {
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
      if (snapshot.status === "cancelled") {
        dispatch({ type: "faster_whisper_model_download_cancelled" });
        reject(new Error("模型下载已取消"));
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
      if (error instanceof Error && (error.message.includes("409") || error.message.includes("取消"))) {
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
    } catch (error) {
      dispatch({
        type: "load_failed",
        message: error instanceof Error ? error.message : "取消语音模型下载失败",
      });
    }
  }

  async function onDownloadRagModel(modelKey) {
    dispatch({ type: "rag_model_download_started", modelKey });
    try {
      await downloadRagModel(modelKey);
      const models = await loadRagModels();
      dispatch({ type: "rag_models_loaded", models });
    } catch (error) {
      dispatch({
        type: "load_failed",
        message: error instanceof Error ? error.message : "RAG 模型下载失败",
      });
    }
  }

  async function onCancelRagModelDownload(modelKey) {
    try {
      await cancelRagModelDownload(modelKey);
      dispatch({ type: "rag_model_download_cancelled" });
      const models = await loadRagModels();
      dispatch({ type: "rag_models_loaded", models });
    } catch (error) {
      dispatch({
        type: "load_failed",
        message: error instanceof Error ? error.message : "取消 RAG 模型下载失败",
      });
    }
  }

  return {
    onToggleSettingsPanel,
    onOpenSettingsPanel,
    onCloseSettingsPanel,
    onChangeSetting,
    onSaveApiKey,
    onTestProviderConnection,
    onResetSettings,
    onDownloadFasterWhisperModel,
    onCancelFasterWhisperModelDownload,
    onDownloadRagModel,
    onCancelRagModelDownload,
  };
}
