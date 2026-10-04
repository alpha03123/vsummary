import { beforeEach, describe, expect, it, vi } from "vitest";
import { createWorkspaceSettingsActions } from "@src/local-features/workspace/model/workspaceSettingsActions";

const api = {
  discoverProviderModels: vi.fn(),
  downloadFasterWhisperModel: vi.fn(),
  downloadRagModel: vi.fn(),
  loadFasterWhisperModels: vi.fn(),
  loadRagModels: vi.fn(),
  updateProviderSettings: vi.fn(),
  updateWorkspaceSettings: vi.fn(),
};
const { discoverProviderModels, downloadFasterWhisperModel, downloadRagModel,
  loadFasterWhisperModels, loadRagModels, updateProviderSettings, updateWorkspaceSettings } = api;
const coreApi = { subscribeDurableJobProgress: vi.fn() };
const { subscribeDurableJobProgress } = coreApi;

beforeEach(() => {
  vi.clearAllMocks();
});

describe("createWorkspaceSettingsActions downloads", () => {
  it("refreshes the ASR model list after a job completes during subscription", async () => {
    const actions = [];
    subscribeDurableJobProgress.mockImplementation((_jobId, listener) => {
      listener({ status: "completed", progress: 100 });
      return () => {};
    });
    downloadFasterWhisperModel.mockResolvedValue({
      jobId: "job-asr",
    });
    loadFasterWhisperModels.mockResolvedValue([
      {
        id: "medium",
        downloaded: true,
      },
    ]);

    const controller = createWorkspaceSettingsActions({
      api, coreApi,
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
    subscribeDurableJobProgress.mockImplementation((_jobId, listener) => {
      listener({ status: "completed", progress: 100 });
      return () => {};
    });
    downloadFasterWhisperModel.mockResolvedValue({ jobId: "job-medium" });
    loadFasterWhisperModels.mockResolvedValue([
      {
        id: "medium",
        downloaded: true,
      },
    ]);

    const dispatch = vi.fn();
    const controller = createWorkspaceSettingsActions({
      api, coreApi,
      state: {
        ui: {
          asrModelQuality: "large-v3-turbo",
        },
      },
      dispatch,
    });

    await controller.onDownloadFasterWhisperModel("medium");

    expect(updateWorkspaceSettings).not.toHaveBeenCalled();
    expect(dispatch).toHaveBeenCalledWith({
      type: "faster_whisper_models_loaded",
      models: [{ id: "medium", downloaded: true }],
    });
    expect(dispatch).not.toHaveBeenCalledWith(expect.objectContaining({ type: "load_failed" }));
  });

  it("refreshes the RAG model list after a job completes during subscription", async () => {
    const actions = [];
    subscribeDurableJobProgress.mockImplementation((_jobId, listener) => {
      listener({ status: "completed", progress: 100 });
      return () => {};
    });
    downloadRagModel.mockResolvedValue({
      jobId: "job-rag",
    });
    loadRagModels.mockResolvedValue([
      {
        key: "embedding",
        status: "completed",
        downloaded: true,
      },
    ]);

    const controller = createWorkspaceSettingsActions({
      api, coreApi,
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
});

describe("createWorkspaceSettingsActions provider settings", () => {
  it("probes models with the current provider draft without saving it", async () => {
    discoverProviderModels.mockResolvedValue(["gpt-5.4-mini", "gpt-5.4"]);
    const actions = [];
    const controller = createWorkspaceSettingsActions({
      api, coreApi,
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

  it("edits provider text fields locally without saving on every keystroke", async () => {
    const actions = [];
    const controller = createWorkspaceSettingsActions({
      api, coreApi,
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
});
