import { beforeEach, describe, expect, it, vi } from "vitest";

import { isSaveableOpenaiBaseUrl, toProviderTestErrorMessage, createWorkspaceSettingsActions } from "@src/features/workspace/model/workspaceSettingsActions";
import {
  cancelRagModelDownload,
  cancelFasterWhisperModelDownload,
  discoverProviderModels,
  downloadFasterWhisperModel,
  downloadRagModel,
  loadFasterWhisperModels,
  loadRagModels,
  subscribeFasterWhisperModelDownloadProgress,
  subscribeRagModelDownloadProgress,
  updateProviderSettings,
  updateWorkspaceSettings,
} from "@src/features/workspace/model/workspaceApi";

vi.mock("@src/features/workspace/model/workspaceApi", () => ({
  cancelRagModelDownload: vi.fn(),
  cancelFasterWhisperModelDownload: vi.fn(),
  discoverProviderModels: vi.fn(),
  downloadFasterWhisperModel: vi.fn(),
  downloadRagModel: vi.fn(),
  loadFasterWhisperModels: vi.fn(),
  loadOpenaiApiKey: vi.fn(),
  loadRagModels: vi.fn(),
  subscribeFasterWhisperModelDownloadProgress: vi.fn(),
  subscribeRagModelDownloadProgress: vi.fn(),
  testProviderSettings: vi.fn(),
  updateProviderSettings: vi.fn(),
  updateWorkspaceSettings: vi.fn(),
}));

beforeEach(() => {
  vi.clearAllMocks();
});

describe("toProviderTestErrorMessage", () => {
  it("keeps backend model timeout message without HTTP status prefix", () => {
    expect(toProviderTestErrorMessage(new Error("503 模型超时"))).toBe("模型超时");
  });

  it("treats aborted provider tests as model timeout", () => {
    expect(toProviderTestErrorMessage(new DOMException("This operation was aborted", "AbortError"))).toBe("模型超时");
  });
});

describe("isSaveableOpenaiBaseUrl", () => {
  it("does not save incomplete edits while the user is typing", () => {
    expect(isSaveableOpenaiBaseUrl("")).toBe(false);
    expect(isSaveableOpenaiBaseUrl("https://")).toBe(false);
    expect(isSaveableOpenaiBaseUrl("api.example.com")).toBe(false);
  });

  it("accepts complete OpenAI-compatible base URLs without removing trailing slash", () => {
    expect(isSaveableOpenaiBaseUrl("https://api.example.com/")).toBe(true);
    expect(isSaveableOpenaiBaseUrl("http://127.0.0.1:8317/v1/")).toBe(true);
  });
});

describe("createWorkspaceSettingsActions downloads", () => {
  it("requests faster-whisper download cancellation", async () => {
    const actions = [];
    cancelFasterWhisperModelDownload.mockResolvedValue({
      status: "cancelling",
      task_id: "asr-download/faster_whisper/large-v3-turbo",
    });
    const controller = createWorkspaceSettingsActions({
      state: { ui: {} },
      dispatch: (action) => actions.push(action),
    });

    await controller.onCancelFasterWhisperModelDownload("large-v3-turbo");

    expect(cancelFasterWhisperModelDownload).toHaveBeenCalledWith("faster_whisper", "large-v3-turbo");
    expect(actions).toEqual([
      {
        type: "faster_whisper_model_download_cancel_requested",
        modelId: "large-v3-turbo",
      },
    ]);
  });

  it("requests RAG download cancellation", async () => {
    const actions = [];
    cancelRagModelDownload.mockResolvedValue({
      status: "cancelling",
      task_id: "rag-model-download/embedding",
    });
    const controller = createWorkspaceSettingsActions({
      state: { ui: {} },
      dispatch: (action) => actions.push(action),
    });

    await controller.onCancelRagModelDownload("embedding");

    expect(cancelRagModelDownload).toHaveBeenCalledWith("embedding");
    expect(actions).toEqual([
      { type: "rag_model_download_cancel_requested", modelKey: "embedding" },
    ]);
  });

  it("does not show a global failure when faster-whisper download is cancelled", async () => {
    const actions = [];
    subscribeFasterWhisperModelDownloadProgress.mockImplementation((provider, modelId, listener) => {
      expect(provider).toBe("faster_whisper");
      expect(modelId).toBe("large-v3-turbo");
      listener({
        status: "cancelled",
        progress: null,
      });
      return () => {};
    });
    downloadFasterWhisperModel.mockResolvedValue({
      id: "large-v3-turbo",
      downloaded: false,
      status: "running",
    });
    loadFasterWhisperModels.mockResolvedValue([
      {
        id: "large-v3-turbo",
        downloaded: false,
      },
    ]);

    const controller = createWorkspaceSettingsActions({
      state: {
        ui: {
          asrModelQuality: "large-v3-turbo",
        },
      },
      dispatch: (action) => actions.push(action),
    });

    await controller.onDownloadFasterWhisperModel("large-v3-turbo");

    expect(updateWorkspaceSettings).not.toHaveBeenCalled();
    expect(actions).toContainEqual({
      type: "faster_whisper_model_download_progress_updated",
      modelId: "large-v3-turbo",
      status: "cancelled",
      progress: null,
    });
    expect(actions.some((action) => action.type === "load_failed")).toBe(false);
  });

  it("keeps backend faster-whisper download errors instead of replacing them", async () => {
    vi.useFakeTimers();
    const actions = [];
    subscribeFasterWhisperModelDownloadProgress.mockImplementation((provider, modelId, listener) => {
      expect(provider).toBe("faster_whisper");
      expect(modelId).toBe("large-v3-turbo");
      listener({
        status: "failed",
        error: "ConnectTimeout: huggingface.co timed out",
      });
      return () => {};
    });
    downloadFasterWhisperModel.mockResolvedValue({
      id: "large-v3-turbo",
      downloaded: false,
    });
    loadFasterWhisperModels.mockResolvedValue([]);

    const controller = createWorkspaceSettingsActions({
      state: { ui: {} },
      dispatch: (action) => actions.push(action),
    });

    await controller.onDownloadFasterWhisperModel("large-v3-turbo");

    expect(actions).toContainEqual({
      type: "faster_whisper_model_download_failed",
      modelId: "large-v3-turbo",
      message: "ConnectTimeout: huggingface.co timed out",
    });
    expect(actions).toContainEqual({
      type: "load_failed",
      message: "ConnectTimeout: huggingface.co timed out",
    });

    vi.advanceTimersByTime(4000);
    expect(actions).toContainEqual({
      type: "faster_whisper_model_download_failure_cleared",
      modelId: "large-v3-turbo",
    });
    vi.useRealTimers();
  });

  it("finishes faster-whisper download when POST already returns a downloaded model", async () => {
    const actions = [];
    subscribeFasterWhisperModelDownloadProgress.mockReturnValue(() => {});
    downloadFasterWhisperModel.mockResolvedValue({
      id: "medium",
      downloaded: true,
    });
    loadFasterWhisperModels.mockResolvedValue([
      {
        id: "medium",
        downloaded: true,
      },
    ]);

    const controller = createWorkspaceSettingsActions({
      state: {
        ui: {
          asrModelQuality: "large-v3-turbo",
        },
      },
      dispatch: (action) => actions.push(action),
    });

    await controller.onDownloadFasterWhisperModel("medium");

    expect(loadFasterWhisperModels).toHaveBeenCalled();
    expect(actions).toContainEqual({
      type: "faster_whisper_models_loaded",
      models: [
        {
          id: "medium",
          downloaded: true,
        },
      ],
    });
  });

  it("does not switch the default ASR model after downloading a different model", async () => {
    const listeners = {};
    subscribeFasterWhisperModelDownloadProgress.mockImplementation((modelId, listener) => {
      listeners[modelId] = listener;
      return () => {};
    });
    downloadFasterWhisperModel.mockImplementation(async (modelId) => {
      listeners[modelId]({
        status: "completed",
        progress: 100,
      });
      return {
        id: modelId,
        downloaded: true,
      };
    });
    loadFasterWhisperModels.mockResolvedValue([
      {
        id: "medium",
        downloaded: true,
      },
    ]);

    const controller = createWorkspaceSettingsActions({
      state: {
        ui: {
          asrModelQuality: "large-v3-turbo",
        },
      },
      dispatch: () => {},
    });

    await controller.onDownloadFasterWhisperModel("medium");

    expect(updateWorkspaceSettings).not.toHaveBeenCalled();
  });

  it("keeps backend RAG download errors instead of replacing them", async () => {
    vi.useFakeTimers();
    const actions = [];
    subscribeRagModelDownloadProgress.mockImplementation((modelKey, listener) => {
      listener({
        status: "failed",
        error: "LocalEntryNotFoundError: cannot find requested files",
      });
      return () => {};
    });
    downloadRagModel.mockResolvedValue({
      key: "embedding",
      downloaded: false,
      status: "running",
    });
    loadRagModels.mockResolvedValue([]);

    const controller = createWorkspaceSettingsActions({
      state: { ui: {} },
      dispatch: (action) => actions.push(action),
    });

    await controller.onDownloadRagModel("embedding");

    expect(actions).toContainEqual({
      type: "rag_model_download_failed",
      modelKey: "embedding",
      message: "LocalEntryNotFoundError: cannot find requested files",
    });
    expect(actions).toContainEqual({
      type: "load_failed",
      message: "LocalEntryNotFoundError: cannot find requested files",
    });

    vi.advanceTimersByTime(4000);
    expect(actions).toContainEqual({
      type: "rag_model_download_failure_cleared",
      modelKey: "embedding",
    });
    vi.useRealTimers();
  });

  it("finishes RAG download when POST already returns a completed status", async () => {
    const actions = [];
    subscribeRagModelDownloadProgress.mockReturnValue(() => {});
    downloadRagModel.mockResolvedValue({
      key: "embedding",
      status: "completed",
      downloaded: true,
    });
    loadRagModels.mockResolvedValue([
      {
        key: "embedding",
        status: "completed",
        downloaded: true,
      },
    ]);

    const controller = createWorkspaceSettingsActions({
      state: { ui: {} },
      dispatch: (action) => actions.push(action),
    });

    await controller.onDownloadRagModel("embedding");

    expect(loadRagModels).toHaveBeenCalled();
    expect(actions).toContainEqual({
      type: "rag_models_loaded",
      models: [
        {
          key: "embedding",
          status: "completed",
          downloaded: true,
        },
      ],
    });
  });

  it("does not show a global failure when RAG download is cancelled", async () => {
    const actions = [];
    subscribeRagModelDownloadProgress.mockImplementation((modelKey, listener) => {
      expect(modelKey).toBe("embedding");
      listener({ status: "cancelled", progress: null });
      return () => {};
    });
    downloadRagModel.mockResolvedValue({ key: "embedding", downloaded: false, status: "running" });
    loadRagModels.mockResolvedValue([]);
    const controller = createWorkspaceSettingsActions({
      state: { ui: {} },
      dispatch: (action) => actions.push(action),
    });

    await controller.onDownloadRagModel("embedding");

    expect(actions).toContainEqual(expect.objectContaining({
      type: "rag_model_download_progress_updated",
      modelKey: "embedding",
      status: "cancelled",
    }));
    expect(actions.some((action) => action.type === "load_failed")).toBe(false);
  });
});

describe("createWorkspaceSettingsActions provider settings", () => {
  it("probes models with the current provider draft without saving it", async () => {
    discoverProviderModels.mockResolvedValue(["gpt-5.4-mini", "gpt-5.4"]);
    const actions = [];
    const controller = createWorkspaceSettingsActions({
      state: {
        ui: {
          llmProvider: "openai",
          openaiBaseUrl: "https://api.example.com",
          openaiModel: "gpt-5.4",
          openaiApiKey: "sk-test",
          hfEndpoint: "https://hf-mirror.com",
        },
      },
      dispatch: (action) => actions.push(action),
    });

    await expect(controller.onDiscoverProviderModels()).resolves.toEqual(["gpt-5.4-mini", "gpt-5.4"]);
    expect(discoverProviderModels).toHaveBeenCalledWith(expect.objectContaining({
      llmProvider: "openai",
      openaiBaseUrl: "https://api.example.com",
      openaiModel: "gpt-5.4",
    }));
    expect(updateProviderSettings).not.toHaveBeenCalled();
    expect(actions).toEqual([]);
  });

  it("saves a model selected from the detected-model list", async () => {
    updateProviderSettings.mockResolvedValue({
      llmProvider: "openai",
      openaiBaseUrl: "https://api.example.com",
      openaiModel: "gpt-5.4-mini",
      hfEndpoint: "https://hf-mirror.com",
      openaiApiKey: "",
    });
    const controller = createWorkspaceSettingsActions({
      state: {
        ui: {
          llmProvider: "openai",
          openaiBaseUrl: "https://api.example.com",
          openaiModel: "gpt-5.4",
          openaiApiKey: "",
          hfEndpoint: "https://hf-mirror.com",
        },
      },
      dispatch: vi.fn(),
    });

    await controller.onSelectProviderModel("gpt-5.4-mini");

    expect(updateProviderSettings).toHaveBeenCalledWith(expect.objectContaining({
      openaiModel: "gpt-5.4-mini",
    }));
  });

  it("does not request local ASR models after saving Aliyun settings", async () => {
    updateWorkspaceSettings.mockResolvedValue({
      asrProvider: "aliyun_bailian",
      runtimeCapabilities: null,
    });
    const controller = createWorkspaceSettingsActions({
      state: {
        ui: {
          asrProvider: "aliyun_bailian",
          answerDetailLevel: "medium",
        },
      },
      dispatch: vi.fn(),
    });

    await controller.onChangeSetting("answerDetailLevel", "long");

    expect(loadFasterWhisperModels).not.toHaveBeenCalled();
  });

  it("edits provider text fields locally without saving on every keystroke", async () => {
    const actions = [];
    const controller = createWorkspaceSettingsActions({
      state: {
        ui: {
          llmProvider: "openai",
          openaiBaseUrl: "",
          openaiModel: "gpt-5.4",
          hfEndpoint: "https://hf-mirror.com",
        },
      },
      dispatch: (action) => actions.push(action),
    });

    await controller.onChangeSetting("hfEndpoint", "");
    await controller.onChangeSetting("openaiModel", "gpt-5.4-mini");

    expect(updateProviderSettings).not.toHaveBeenCalled();
    expect(actions).toEqual([
      { type: "workspace_setting_edited", key: "hfEndpoint", value: "" },
      { type: "workspace_setting_edited", key: "openaiModel", value: "gpt-5.4-mini" },
    ]);
  });

  it("saves an empty HuggingFace endpoint as the official source", async () => {
    updateProviderSettings.mockResolvedValue({
      llmProvider: "openai",
      openaiBaseUrl: "",
      openaiModel: "gpt-5.4",
      hfEndpoint: "https://huggingface.co",
      openaiApiKey: "",
    });
    const actions = [];
    const controller = createWorkspaceSettingsActions({
      state: {
        ui: {
          llmProvider: "openai",
          openaiBaseUrl: "",
          openaiModel: "gpt-5.4",
          hfEndpoint: "",
        },
      },
      dispatch: (action) => actions.push(action),
    });

    await controller.onSaveProviderSettings();

    expect(updateProviderSettings).toHaveBeenCalledTimes(1);
    expect(updateProviderSettings).toHaveBeenCalledWith(expect.objectContaining({
      hfEndpoint: "https://huggingface.co",
      openaiModel: "gpt-5.4",
    }));
    expect(actions).toContainEqual({
      type: "workspace_settings_loaded",
      settings: expect.objectContaining({ hfEndpoint: "https://huggingface.co" }),
    });
  });
});
