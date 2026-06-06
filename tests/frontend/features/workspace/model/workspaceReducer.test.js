import { describe, expect, it } from "vitest";

import { MODEL_DOWNLOAD_FAILED_MESSAGE } from "@src/features/workspace/model/modelDownloadMessages";
import { workspaceReducer } from "@src/features/workspace/model/workspaceReducer";
import {
  buildSeriesGenerationTaskKey,
  buildVideoGenerationTaskKey,
  createInitialWorkspaceState,
} from "@src/features/workspace/model/workspaceState";

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

describe("workspaceReducer video generation cancellation", () => {
  it("marks video task snapshot as cancelling on video_generation_cancelling", () => {
    const taskKey = buildVideoGenerationTaskKey("series-a", "video-1");
    let state = workspaceReducer(createInitialWorkspaceState(), {
      type: "generation_started",
      videoKey: taskKey,
      seriesId: "series-a",
      videoId: "video-1",
    });

    state = workspaceReducer(state, {
      type: "video_generation_cancelling",
      seriesId: "series-a",
      videoId: "video-1",
    });

    expect(state.generationTasksByKey[taskKey].snapshot.status).toBe("cancelling");
    expect(state.generationTasksByKey[taskKey].snapshot.detail).toBe("正在停止当前任务");
  });

  it("series_generation_queue_cancelling sets queue status to cancelling", () => {
    let state = workspaceReducer(createInitialWorkspaceState(), {
      type: "series_generation_queue_started",
      seriesId: "series-a",
      total: 3,
    });

    state = workspaceReducer(state, {
      type: "series_generation_queue_cancelling",
      seriesId: "series-a",
    });

    expect(state.seriesGenerationQueue.status).toBe("cancelling");
  });

  it("ignores series status without run id while a run-scoped queue is active", () => {
    const taskKey = buildSeriesGenerationTaskKey("series-a");
    let state = workspaceReducer(createInitialWorkspaceState(), {
      type: "series_generation_queue_started",
      seriesId: "series-a",
      runId: "run-b",
      total: 3,
    });
    state = workspaceReducer(state, {
      type: "series_generation_started",
      seriesId: "series-a",
      runId: "run-b",
    });

    state = workspaceReducer(state, {
      type: "generation_status_loaded",
      taskKey,
      mode: "series",
      seriesId: "series-a",
      videoId: null,
      snapshot: {
        status: "cancelled",
        stage: "cancelled",
        progress: null,
        detail: "任务已取消",
        error: null,
      },
      subscriptionActive: false,
    });

    expect(state.seriesGenerationQueue).toEqual(expect.objectContaining({
      runId: "run-b",
      status: "running",
    }));
    expect(state.generationTasksByKey[taskKey]).toEqual(expect.objectContaining({
      runId: "run-b",
      snapshot: expect.objectContaining({ status: "running" }),
    }));
  });

  it("ignores stale series cancellation action from an older run", () => {
    const taskKey = buildSeriesGenerationTaskKey("series-a");
    let state = workspaceReducer(createInitialWorkspaceState(), {
      type: "series_generation_queue_started",
      seriesId: "series-a",
      runId: "run-b",
      total: 3,
    });
    state = workspaceReducer(state, {
      type: "series_generation_started",
      seriesId: "series-a",
      runId: "run-b",
    });

    state = workspaceReducer(state, {
      type: "generation_cancelled",
      taskKey,
      mode: "series",
      seriesId: "series-a",
      runId: "run-a",
      videoId: null,
    });

    expect(state.seriesGenerationQueue).toEqual(expect.objectContaining({
      runId: "run-b",
      status: "running",
    }));
    expect(state.generationTasksByKey[taskKey]).toEqual(expect.objectContaining({
      runId: "run-b",
      snapshot: expect.objectContaining({ status: "running" }),
    }));
  });

  it("ignores stale series success action from an older run", () => {
    const taskKey = buildSeriesGenerationTaskKey("series-a");
    let state = workspaceReducer(createInitialWorkspaceState(), {
      type: "series_generation_queue_started",
      seriesId: "series-a",
      runId: "run-b",
      total: 3,
    });
    state = workspaceReducer(state, {
      type: "series_generation_started",
      seriesId: "series-a",
      runId: "run-b",
    });

    state = workspaceReducer(state, {
      type: "series_generation_succeeded",
      taskKey,
      seriesId: "series-a",
      runId: "run-a",
      library: { series: [] },
    });

    expect(state.generationMode).toBe("series");
    expect(state.generationTasksByKey[taskKey]).toEqual(expect.objectContaining({
      runId: "run-b",
      snapshot: expect.objectContaining({ status: "running" }),
    }));
  });
});
