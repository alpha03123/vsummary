import { describe, expect, it } from "vitest";

import { MODEL_DOWNLOAD_FAILED_MESSAGE } from "@src/features/workspace/model/modelDownloadMessages";
import { workspaceReducer } from "@src/features/workspace/model/workspaceReducer";

describe("workspaceReducer model download failures", () => {
  it("keeps faster-whisper download failure on the matching model", () => {
    const state = {
      downloadingModelId: "large-v3-turbo",
      modelDownloadStatus: "running",
      modelDownloadProgress: 5,
      modelDownloadErrorModelId: null,
      modelDownloadError: null,
    };

    const nextState = workspaceReducer(state, {
      type: "faster_whisper_model_download_failed",
      modelId: "large-v3-turbo",
      message: MODEL_DOWNLOAD_FAILED_MESSAGE,
    });

    expect(nextState.downloadingModelId).toBeNull();
    expect(nextState.modelDownloadStatus).toBe("failed");
    expect(nextState.modelDownloadErrorModelId).toBe("large-v3-turbo");
    expect(nextState.modelDownloadError).toBe(MODEL_DOWNLOAD_FAILED_MESSAGE);
  });

  it("stores RAG download failure on the matching model", () => {
    const state = {
      downloadingRagModelKey: "embedding",
      ragModelsLoading: true,
      ragModels: [
        {
          key: "embedding",
          status: "running",
          progress: 5,
          error: null,
        },
      ],
    };

    const nextState = workspaceReducer(state, {
      type: "rag_model_download_failed",
      modelKey: "embedding",
      message: MODEL_DOWNLOAD_FAILED_MESSAGE,
    });

    expect(nextState.downloadingRagModelKey).toBeNull();
    expect(nextState.ragModelsLoading).toBe(false);
    expect(nextState.ragModels[0]).toMatchObject({
      status: "failed",
      progress: null,
      error: MODEL_DOWNLOAD_FAILED_MESSAGE,
    });
  });
});
