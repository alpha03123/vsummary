import { describe, expect, it } from "vitest";

import { MODEL_DOWNLOAD_FAILED_MESSAGE } from "@src/local-features/workspace/model/modelDownloadMessages";
import { workspaceReducer } from "@workspace/workspace/model/workspaceReducer";
import { buildWorkspacePageModel } from "@workspace/workspace/ui/workspacePageModel";
import {
  buildSeriesGenerationTaskKey,
  buildVideoGenerationTaskKey,
  createInitialWorkspaceState,
} from "@workspace/workspace/model/workspaceState";

describe("workspaceReducer series overview", () => {
  it("stores summaries independently from the selected video summary", () => {
    let state = workspaceReducer(createInitialWorkspaceState(), {
      type: "series_overview_loading_started",
    });
    state = workspaceReducer(state, {
      type: "series_overview_loaded",
      summariesByVideoId: {
        "video-1": { title: "第一讲" },
        "video-2": { title: "第二讲" },
      },
    });

    expect(state.seriesOverviewLoading).toBe(false);
    expect(state.seriesOverviewSummariesByVideoId).toEqual({
      "video-1": { title: "第一讲" },
      "video-2": { title: "第二讲" },
    });
    expect(state.summary).toBeNull();
  });
});

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

  it("tracks multiple faster-whisper model downloads independently", () => {
    let state = {
      modelDownloadsById: {},
      downloadingModelId: null,
      modelDownloadStatus: null,
      modelDownloadProgress: null,
      modelDownloadErrorModelId: null,
      modelDownloadError: null,
      fasterWhisperModelsLoading: false,
      error: "",
    };

    state = workspaceReducer(state, {
      type: "faster_whisper_model_download_started",
      modelId: "medium",
    });
    state = workspaceReducer(state, {
      type: "faster_whisper_model_download_started",
      modelId: "large-v3",
    });
    state = workspaceReducer(state, {
      type: "faster_whisper_model_download_progress_updated",
      modelId: "medium",
      status: "running",
      progress: 5,
    });

    expect(state.modelDownloadsById).toEqual({
      medium: expect.objectContaining({ status: "running", progress: 5, error: null }),
      "large-v3": expect.objectContaining({ status: "running", progress: 0, error: null }),
    });
  });

  it("clears faster-whisper model download state after cancellation completes", () => {
    const state = {
      modelDownloadsById: {
        "large-v3-turbo": { status: "cancelling", progress: 32, error: null },
      },
      downloadingModelId: "large-v3-turbo",
      modelDownloadStatus: "cancelling",
      modelDownloadProgress: 32,
      modelDownloadErrorModelId: null,
      modelDownloadError: null,
    };

    const nextState = workspaceReducer(state, {
      type: "faster_whisper_model_download_progress_updated",
      modelId: "large-v3-turbo",
      status: "cancelled",
      progress: null,
    });

    expect(nextState.downloadingModelId).toBeNull();
    expect(nextState.modelDownloadStatus).toBeNull();
    expect(nextState.modelDownloadProgress).toBeNull();
    expect(nextState.modelDownloadsById).toEqual({});
  });

  it("preserves running faster-whisper downloads when model list refreshes", () => {
    const state = {
      fasterWhisperModels: [],
      fasterWhisperModelsLoading: false,
      downloadingModelId: "large-v3",
      modelDownloadsById: {
        "large-v3": { status: "running", progress: 5, error: null },
      },
      modelDownloadStatus: "running",
      modelDownloadProgress: 5,
      modelDownloadErrorModelId: null,
      modelDownloadError: null,
    };

    const nextState = workspaceReducer(state, {
      type: "faster_whisper_models_loaded",
      models: [
        { id: "small", downloaded: true, current: false },
        { id: "large-v3", downloaded: false, current: false },
      ],
    });

    expect(nextState.modelDownloadsById["large-v3"]).toEqual({
      status: "running",
      progress: 5,
      error: null,
    });
  });

  it("stores RAG download failure on the matching model", () => {
    const state = {
      downloadingRagModelKeys: ["embedding", "reranker"],
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

    expect(nextState.downloadingRagModelKeys).toEqual(["reranker"]);
    expect(nextState.ragModelsLoading).toBe(false);
    expect(nextState.ragModels[0]).toMatchObject({
      status: "failed",
      progress: null,
      error: MODEL_DOWNLOAD_FAILED_MESSAGE,
    });
  });

  it("tracks multiple RAG model downloads independently", () => {
    let state = {
      downloadingRagModelKeys: [],
      ragModelsLoading: false,
      ragModels: [
        { key: "embedding", status: "idle", progress: null, error: null },
        { key: "reranker", status: "idle", progress: null, error: null },
      ],
      error: "",
    };

    state = workspaceReducer(state, {
      type: "rag_model_download_started",
      modelKey: "embedding",
    });
    state = workspaceReducer(state, {
      type: "rag_model_download_started",
      modelKey: "reranker",
    });
    state = workspaceReducer(state, {
      type: "rag_model_download_progress_updated",
      modelKey: "embedding",
      status: "completed",
      progress: 100,
    });

    expect(state.downloadingRagModelKeys).toEqual(["reranker"]);
    expect(state.ragModels).toEqual([
      expect.objectContaining({ key: "embedding", status: "completed", progress: 100 }),
      expect.objectContaining({ key: "reranker", status: "running", progress: 0 }),
    ]);
  });
});

describe("workspaceReducer video generation cancellation", () => {
  it("does not rewind a restored job on replay, but resets progress for a new job", () => {
    const taskKey = buildVideoGenerationTaskKey("series-a","video-1");
    const base = {type:"generation_status_loaded",taskKey,mode:"video",seriesId:"series-a",videoId:"video-1",jobId:"job-1",subscriptionActive:true};
    let state = workspaceReducer(createInitialWorkspaceState(),{...base,
      snapshot:{status:"running",stage:"understand_frames",progress:88,sequence:8,steps:[{id:"ai_summary",status:"running"}]}});
    const restored = state;
    state = workspaceReducer(state,{...base,type:"generation_progress_updated",progress:0,
      snapshot:{status:"running",stage:"queued",progress:0,sequence:1,steps:[]}});
    expect(state).toBe(restored);
    state = workspaceReducer(state,{...base,snapshot:{status:"running",stage:"understand_frames",progress:null,sequence:9}});
    expect(state.generationTasksByKey[taskKey].snapshot.progress).toBe(88);
    state = workspaceReducer(state,{...base,jobId:"job-2",snapshot:{status:"queued",stage:"queued",progress:0,sequence:1}});
    expect(state.generationTasksByKey[taskKey].snapshot.progress).toBe(0);
  });
  it("does not let a stale idle status hide a just-started durable job", () => {
    const taskKey = buildVideoGenerationTaskKey("series-a", "video-1");
    let state = {
      ...createInitialWorkspaceState(),
      selectedContextType: "video",
      selectedSeriesId: "series-a",
      selectedVideoId: "video-1",
    };
    state = workspaceReducer(state, {
      type: "generation_started",
      videoKey: taskKey,
      seriesId: "series-a",
      videoId: "video-1",
    });

    state = workspaceReducer(state, {
      type: "generation_status_loaded",
      taskKey,
      mode: "video",
      seriesId: "series-a",
      videoId: "video-1",
      jobId: null,
      snapshot: { status: "idle", stage: null, progress: null, detail: null, error: null },
      subscriptionActive: false,
    });

    expect(state.generationTasksByKey[taskKey].snapshot.status).toBe("running");
    expect(state.generationSnapshot.status).toBe("running");
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

describe("workspaceReducer chat drawer", () => {
  it("closes the chat drawer when returning to the library home", () => {
    const start = {
      ...createInitialWorkspaceState(),
      chatDrawerOpen: true,
      selectedSeriesId: "series-1",
      selectedContextType: "series",
    };
    const home = workspaceReducer(start, { type: "library_home_selected" });
    expect(home.selectedContextType).toBeNull();
    expect(home.chatDrawerOpen).toBe(false);
  });

  it("video_selected resets playerSeekRequest but keeps chatDrawerOpen", () => {
    const start = workspaceReducer(createInitialWorkspaceState(), { type: "chat_drawer_opened" });
    const request = { seconds: 5, endSeconds: null, query: "", matchedText: "", chapterTitle: "x", requestId: 1 };
    const withRequest = workspaceReducer(start, { type: "player_seek_requested", ...request });
    expect(withRequest.playerSeekRequest).toEqual(request);
    const afterVideo = workspaceReducer(withRequest, { type: "video_selected", seriesId: "s", videoId: "v" });
    expect(afterVideo.playerSeekRequest).toBeNull();
    expect(afterVideo.chatDrawerOpen).toBe(true);
  });

  it("keeps loaded video content when selecting the current video again", () => {
    const current = {
      ...createInitialWorkspaceState(),
      selectedContextType: "video",
      selectedSeriesId: "series-1",
      selectedVideoId: "video-1",
      tools: { overview: { generated: true } },
      summary: { title: "已加载概况", chapters: [] },
      summaryLoading: false,
    };

    const next = workspaceReducer(current, {
      type: "video_selected",
      seriesId: "series-1",
      videoId: "video-1",
    });

    expect(next).toBe(current);
    expect(next.tools).toBe(current.tools);
    expect(next.summary).toBe(current.summary);
  });
});

describe("series queue guards", () => {
  it("does not read a missing queue while a series scope is selected", () => {
    const state = {
      ...createInitialWorkspaceState(),
      selectedContextType: "series",
      selectedSeriesId: undefined,
      seriesGenerationQueue: undefined,
    };
    expect(() => buildWorkspacePageModel({
      state,
      selectedContextType: state.selectedContextType,
      seriesGenerationQueue: state.seriesGenerationQueue,
      currentGenerationTask: null,
    })).not.toThrow();
  });
});

describe("workspaceReducer video download cancellation", () => {
  it("retains a download failure for the video that triggered it", () => {
    const state = {
      downloadingVideoKey: "series-a/linked-1",
      videoDownloadProgress: 42,
      library: {
        series: [{ id: "series-a", videos: [{ id: "linked-1", isLinked: true, status: "downloading" }] }],
      },
    };

    const nextState = workspaceReducer(state, {
      type: "video_download_failed",
      seriesId: "series-a",
      videoId: "linked-1",
      error: "download failed",
    });

    expect(nextState.videoDownloadError).toBe("download failed");
    expect(nextState.videoDownloadErrorKey).toBe("series-a/linked-1");
    const page = buildWorkspacePageModel({state: nextState, selectedContextType: "series"});
    expect(page.generation.videoDownloadError).toBe("download failed");
    expect(page.generation.videoDownloadErrorKey).toBe("series-a/linked-1");
    const refreshed = workspaceReducer(nextState, { type: "tools_loaded", tools: null });
    expect(refreshed.videoDownloadError).toBe("download failed");
    const dismissed = workspaceReducer(refreshed, { type: "error_cleared" });
    expect(dismissed.videoDownloadError).toBeNull();
    expect(dismissed.videoDownloadErrorKey).toBeNull();
    expect(nextState.library.series[0].videos[0].status).toBe("linked");
  });

  it("keeps the download locked while cancellation is pending", () => {
    const state = {
      downloadingVideoKey: "series-a/linked-1",
      videoDownloadProgress: 42,
      library: {
        series: [
          {
            id: "series-a",
            videos: [
              { id: "linked-1", isLinked: true, status: "downloading" },
            ],
          },
        ],
      },
    };

    const nextState = workspaceReducer(state, {
      type: "video_download_cancel_requested",
      seriesId: "series-a",
      videoId: "linked-1",
    });

    expect(nextState.downloadingVideoKey).toBe("series-a/linked-1");
    expect(nextState.videoDownloadProgress).toBeNull();
    expect(nextState.library.series[0].videos[0].status).toBe("downloading");
  });

  it("restores the linked card only after download cancellation is confirmed", () => {
    const state = {
      downloadingVideoKey: "series-a/linked-1",
      videoDownloadProgress: 42,
      library: {
        series: [{ id: "series-a", videos: [{ id: "linked-1", isLinked: true, status: "downloading" }] }],
      },
    };

    const nextState = workspaceReducer(state, {
      type: "video_download_cancelled",
      seriesId: "series-a",
      videoId: "linked-1",
    });

    expect(nextState.downloadingVideoKey).toBeNull();
    expect(nextState.library.series[0].videos[0].status).toBe("linked");
  });
});

describe("workspaceReducer completed video generation refresh", () => {
  it("updates the current AI summary card from the completed job readback", () => {
    const state = {
      selectedContextType: "video",
      selectedSeriesId: "series-a",
      selectedVideoId: "video-1",
      library: { series: [{ id: "series-a", videos: [{ id: "video-1", processed: false, status: "pending" }] }] },
      tools: { aiSummary: { generated: false, status: "available" } },
      aiSummary: null,
      toolsLoading: true,
      aiSummaryLoading: true,
      generatingAiSummary: true,
    };
    const completedTools = {
      overview: { generated: true, status: "ready" },
      aiSummary: { generated: true, status: "ready" },
    };
    const aiSummary = { title: "同步 AI 概括", content: "已与逐字稿一同生成", citations: [] };

    const nextState = workspaceReducer(state, {
      type: "video_generation_content_refreshed",
      seriesId: "series-a",
      videoId: "video-1",
      library: { series: [{ id: "series-a", videos: [{ id: "video-1", processed: true, status: "ready" }] }] },
      tools: completedTools,
      aiSummary,
    });

    expect(nextState.tools).toBe(completedTools);
    expect(nextState.aiSummary).toBe(aiSummary);
    expect(nextState.aiSummaryLoading).toBe(false);
    expect(nextState.generatingAiSummary).toBe(false);
  });

  it("does not replace a different video panel when a previous job completes", () => {
    const state = {
      selectedContextType: "video",
      selectedSeriesId: "series-a",
      selectedVideoId: "video-2",
      library: { series: [{ id: "series-a", videos: [{ id: "video-1" }, { id: "video-2" }] }] },
      tools: { aiSummary: { generated: false } },
      aiSummary: { title: "Video 2" },
    };

    const nextState = workspaceReducer(state, {
      type: "video_generation_content_refreshed",
      seriesId: "series-a",
      videoId: "video-1",
      library: { series: [{ id: "series-a", videos: [{ id: "video-1", processed: true }, { id: "video-2" }] }] },
      tools: { aiSummary: { generated: true } },
      aiSummary: { title: "Video 1" },
    });

    expect(nextState.aiSummary).toEqual({ title: "Video 2" });
    expect(nextState.tools).toEqual({ aiSummary: { generated: false } });
  });
});
