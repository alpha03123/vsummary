import { describe, expect, it, vi } from "vitest";

describe("workspaceContentActions media links", () => {
  it("uses the agent processing route for a linked video", async () => {
    vi.resetModules();
    const processAgentVideo = vi.fn(() => Promise.resolve({ status: "scheduled" }));
    vi.doMock("@src/features/workspace/model/workspaceApi", () => ({
      ...createWorkspaceApiMock(),
      processAgentVideo,
    }));
    const { createWorkspaceContentActions } = await import(
      "@src/features/workspace/model/workspaceContentActions"
    );
    const dispatch = vi.fn();
    const actions = createWorkspaceContentActions({
      state: {
        selectedSeriesId: "bilibili",
        selectedVideoId: "BV1example",
      },
      dispatch,
      selectedVideo: { id: "BV1example", isLinked: true, status: "linked" },
    });

    await actions.onProcessLinkedVideo();

    expect(processAgentVideo).toHaveBeenCalledWith("bilibili", "BV1example", {
      processingMode: undefined,
    });
    expect(dispatch).toHaveBeenCalledWith(expect.objectContaining({
      type: "generation_status_loaded",
      snapshot: expect.objectContaining({ status: "queued", stage: "queued" }),
    }));
  });

  it("starts only one request when the same video generation action is invoked twice", async () => {
    vi.resetModules();
    let resolveGeneration;
    const generateVideoSummary = vi.fn(() => new Promise((resolve) => {
      resolveGeneration = resolve;
    }));
    const loadWorkspaceLibrary = vi.fn(() => Promise.resolve({ series: [] }));
    vi.doMock("@src/features/workspace/model/workspaceApi", () => ({
      ...createWorkspaceApiMock(),
      generateVideoSummary,
      loadWorkspaceLibrary,
    }));
    const { createWorkspaceContentActions } = await import(
      "@src/features/workspace/model/workspaceContentActions"
    );
    const actions = createWorkspaceContentActions({
      state: {
        selectedSeriesId: "series-a",
        selectedVideoId: "video-a",
        processingMode: "summary",
        ui: { transcriptEnhancementEnabled: true },
      },
      dispatch: vi.fn(),
      selectedVideo: { id: "video-a", status: "pending" },
    });

    const first = actions.onGenerateVideo();
    const second = actions.onGenerateVideo();

    expect(generateVideoSummary).toHaveBeenCalledTimes(1);
    resolveGeneration({ jobId: "job-1", status: "queued" });
    await Promise.all([first, second]);
  });

  it("retries a downloaded pending video through the normal generation route", async () => {
    vi.resetModules();
    const generateVideoSummary = vi.fn(() => Promise.resolve({ jobId: "job-1", status: "queued" }));
    const loadWorkspaceLibrary = vi.fn(() => Promise.resolve({ series: [] }));
    vi.doMock("@src/features/workspace/model/workspaceApi", () => ({
      ...createWorkspaceApiMock(),
      generateVideoSummary,
      loadWorkspaceLibrary,
    }));
    const { createWorkspaceContentActions } = await import(
      "@src/features/workspace/model/workspaceContentActions"
    );
    const actions = createWorkspaceContentActions({
      state: {
        selectedSeriesId: "bilibili",
        selectedVideoId: "BV1example",
        ui: { transcriptEnhancementEnabled: true },
      },
      dispatch: vi.fn(),
      selectedVideo: { id: "BV1example", isLinked: false, status: "pending" },
    });

    await actions.onProcessLinkedVideo();

    expect(generateVideoSummary).toHaveBeenCalledWith("bilibili", "BV1example", {
      transcriptEnhancementEnabled: true,
    });
  });

  it("keeps a broken media error visible for the user", async () => {
    vi.resetModules();
    const generateVideoSummary = vi.fn(() => Promise.reject(new Error("503 source media unavailable: D:\\ABC\\lesson.mp4")));
    vi.doMock("@src/features/workspace/model/workspaceApi", () => ({
      ...createWorkspaceApiMock(),
      generateVideoSummary,
    }));
    const { createWorkspaceContentActions } = await import(
      "@src/features/workspace/model/workspaceContentActions"
    );
    const dispatch = vi.fn();
    const actions = createWorkspaceContentActions({
      state: {
        selectedSeriesId: "series-a",
        selectedVideoId: "video-a",
        ui: { transcriptEnhancementEnabled: true },
      },
      dispatch,
      selectedVideo: null,
    });

    await actions.onGenerateVideo();

    expect(dispatch).toHaveBeenCalledWith(expect.objectContaining({
      type: "load_failed",
      message: "503 source media unavailable: D:\\ABC\\lesson.mp4",
    }));
    expect(dispatch).toHaveBeenCalledWith(expect.objectContaining({
      type: "generation_status_loaded",
      snapshot: expect.objectContaining({ error: "503 source media unavailable: D:\\ABC\\lesson.mp4" }),
    }));
  });
});

describe("workspaceContentActions video cancellation", () => {
  it("moves the task to cancelled as soon as the cancel request succeeds", async () => {
    vi.resetModules();
    const cancelVideoSummary = vi.fn(() => Promise.resolve({ status: "cancelled" }));
    vi.doMock("@src/features/workspace/model/workspaceApi", () => ({
      ...createWorkspaceApiMock(),
      cancelVideoSummary,
    }));
    const { createWorkspaceContentActions } = await import(
      "@src/features/workspace/model/workspaceContentActions"
    );
    const dispatch = vi.fn();
    const actions = createWorkspaceContentActions({
      state: {
        selectedSeriesId: "series-a",
        selectedVideoId: "video-a",
        selectedContextType: "video",
        generationTasksByKey: {
          "video:series-a/video-a": {
            taskKey: "video:series-a/video-a",
            mode: "video",
            seriesId: "series-a",
            videoId: "video-a",
            snapshot: { status: "running", stage: "summarize", progress: 88 },
          },
        },
      },
      dispatch,
      selectedVideo: { id: "video-a", status: "pending" },
    });

    await actions.onCancelGeneration();

    expect(cancelVideoSummary).toHaveBeenCalledWith("series-a", "video-a");
    expect(dispatch).toHaveBeenNthCalledWith(1, {
      type: "video_generation_cancelling",
      seriesId: "series-a",
      videoId: "video-a",
    });
    expect(dispatch).toHaveBeenNthCalledWith(2, expect.objectContaining({
      type: "generation_cancelled",
      taskKey: "video:series-a/video-a",
      snapshot: expect.objectContaining({ status: "cancelled", stage: "cancelled" }),
    }));
  });
});

describe("workspaceContentActions series cancellation", () => {
  it("keeps the series queue cancelling until backend cancellation finishes", async () => {
    vi.resetModules();
    let resolveDownloadCancel;
    const cancelVideoDownload = vi.fn(() => new Promise((resolve) => {
      resolveDownloadCancel = resolve;
    }));
    const cancelSeriesSummaries = vi.fn(() => Promise.resolve({ status: "cancelled" }));
    vi.doMock("@src/features/workspace/model/workspaceApi", () => ({
      ...createWorkspaceApiMock(),
      cancelVideoDownload,
      cancelSeriesSummaries,
    }));
    const { createWorkspaceContentActions } = await import(
      "@src/features/workspace/model/workspaceContentActions"
    );
    const dispatch = vi.fn();
    const actions = createWorkspaceContentActions({
      state: {
        selectedSeriesId: "series-a",
        selectedVideoId: null,
        selectedContextType: "series",
        seriesGenerationQueue: {
          seriesId: "series-a",
          status: "running",
          downloadVideoId: "video-1",
        },
      },
      dispatch,
      selectedVideo: null,
    });

    const cancelTask = actions.onCancelGeneration();
    await Promise.resolve();

    expect(dispatch).toHaveBeenCalledWith({
      type: "series_generation_queue_cancelling",
      seriesId: "series-a",
    });
    expect(dispatch).not.toHaveBeenCalledWith({
      type: "series_generation_queue_finished",
      seriesId: "series-a",
      status: "cancelled",
    });
    expect(cancelSeriesSummaries).toHaveBeenCalledWith("series-a", { runId: undefined });

    resolveDownloadCancel({});
    await cancelTask;

    expect(cancelVideoDownload).toHaveBeenCalledWith("series-a", "video-1");
    expect(cancelSeriesSummaries).toHaveBeenCalledWith("series-a", { runId: undefined });
    expect(dispatch).toHaveBeenCalledWith({
      type: "series_generation_queue_finished",
      seriesId: "series-a",
      status: "cancelled",
    });
  });

  it("does not let an old cancel completion finish a newer series run", async () => {
    vi.resetModules();
    let resolveSeriesCancel;
    const cancelSeriesSummaries = vi.fn(() => new Promise((resolve) => {
      resolveSeriesCancel = resolve;
    }));
    vi.doMock("@src/features/workspace/model/workspaceApi", () => ({
      ...createWorkspaceApiMock(),
      cancelSeriesSummaries,
      cancelVideoDownload: vi.fn(() => Promise.resolve({})),
    }));
    const { createWorkspaceContentActions } = await import(
      "@src/features/workspace/model/workspaceContentActions"
    );
    const firstDispatch = vi.fn();
    const firstActions = createWorkspaceContentActions({
      state: {
        selectedSeriesId: "series-a",
        selectedVideoId: null,
        selectedContextType: "series",
        seriesGenerationQueue: {
          runId: "series-a:old",
          seriesId: "series-a",
          status: "running",
          downloadVideoId: null,
        },
      },
      dispatch: firstDispatch,
      selectedVideo: null,
    });

    const cancelTask = firstActions.onCancelGeneration();
    await Promise.resolve();

    const secondDispatch = vi.fn();
    const secondActions = createWorkspaceContentActions({
      state: {
        selectedSeriesId: "series-a",
        selectedVideoId: null,
        selectedContextType: "series",
        library: {
          series: [
            {
              id: "series-a",
              videos: [{ id: "video-1", processed: false, status: "pending" }],
            },
          ],
        },
        ui: { transcriptEnhancementEnabled: true },
        seriesGenerationQueue: null,
        generationTasksByKey: {},
      },
      dispatch: secondDispatch,
      selectedVideo: null,
    });

    await secondActions.onGenerateSeries();
    resolveSeriesCancel({});
    await cancelTask;

    const secondStart = secondDispatch.mock.calls.find(([action]) => action.type === "series_generation_queue_started")?.[0];
    const staleFinish = firstDispatch.mock.calls.find(([action]) => action.type === "series_generation_queue_finished")?.[0];
    expect(secondStart?.runId).toBeTruthy();
    expect(staleFinish?.runId).not.toBe(secondStart?.runId);
  });

  it("cancels every pending linked video download when cancelling a series run", async () => {
    vi.resetModules();
    const cancelVideoDownload = vi.fn(() => Promise.resolve({ status: "cancelling" }));
    const cancelSeriesSummaries = vi.fn(() => Promise.resolve({ status: "cancelled" }));
    vi.doMock("@src/features/workspace/model/workspaceApi", () => ({
      ...createWorkspaceApiMock(),
      cancelVideoDownload,
      cancelSeriesSummaries,
    }));
    const { createWorkspaceContentActions } = await import(
      "@src/features/workspace/model/workspaceContentActions"
    );
    const actions = createWorkspaceContentActions({
      state: {
        selectedSeriesId: "series-a",
        selectedVideoId: null,
        selectedContextType: "series",
        library: {
          series: [
            {
              id: "series-a",
              videos: [
                { id: "linked-1", processed: false, status: "linked", isLinked: true },
                { id: "linked-2", processed: false, status: "linked", isLinked: true },
                { id: "local-1", processed: false, status: "pending" },
                { id: "ready-1", processed: true, status: "linked", isLinked: true },
              ],
            },
          ],
        },
        seriesGenerationQueue: {
          runId: "series-a:1",
          seriesId: "series-a",
          status: "running",
          downloadVideoId: "linked-1",
        },
      },
      dispatch: vi.fn(),
      selectedVideo: null,
    });

    await actions.onCancelGeneration();

    expect(cancelSeriesSummaries).toHaveBeenCalledWith("series-a", { runId: "series-a:1" });
    expect(cancelVideoDownload).toHaveBeenCalledTimes(2);
    expect(cancelVideoDownload).toHaveBeenCalledWith("series-a", "linked-1");
    expect(cancelVideoDownload).toHaveBeenCalledWith("series-a", "linked-2");
  });

  it("reloads library after series cancellation so completed partial results stay visible", async () => {
    vi.resetModules();
    const refreshedLibrary = {
      series: [
        {
          id: "series-a",
          videos: [
            { id: "video-1", processed: true, status: "ready" },
            { id: "video-2", processed: false, status: "pending" },
          ],
        },
      ],
    };
    const loadWorkspaceLibrary = vi.fn(() => Promise.resolve(refreshedLibrary));
    vi.doMock("@src/features/workspace/model/workspaceApi", () => ({
      ...createWorkspaceApiMock(),
      cancelSeriesSummaries: vi.fn(() => Promise.resolve({ status: "cancelled" })),
      cancelVideoDownload: vi.fn(() => Promise.resolve({})),
      loadWorkspaceLibrary,
    }));
    const { createWorkspaceContentActions } = await import(
      "@src/features/workspace/model/workspaceContentActions"
    );
    const dispatch = vi.fn();
    const actions = createWorkspaceContentActions({
      state: {
        selectedSeriesId: "series-a",
        selectedVideoId: null,
        selectedContextType: "series",
        library: {
          series: [
            {
              id: "series-a",
              videos: [
                { id: "video-1", processed: false, status: "pending" },
                { id: "video-2", processed: false, status: "pending" },
              ],
            },
          ],
        },
        seriesGenerationQueue: {
          runId: "series-a:1",
          seriesId: "series-a",
          status: "running",
          downloadVideoId: null,
        },
      },
      dispatch,
      selectedVideo: null,
    });

    await actions.onCancelGeneration();

    expect(loadWorkspaceLibrary).toHaveBeenCalledTimes(1);
    expect(dispatch).toHaveBeenCalledWith({ type: "workspace_loaded", library: refreshedLibrary });
  });

  it("skips failed linked video downloads and continues the series run", async () => {
    vi.resetModules();
    const startVideoDownload = vi.fn(() => Promise.resolve({ taskId: "download-task" }));
    const subscribeVideoDownloadProgress = vi.fn((seriesId, videoId, listener) => {
      queueMicrotask(() => {
        listener(
          videoId === "linked-1"
            ? { status: "failed", error: "yt-dlp 退出码 1：HTTP Error 403" }
            : { status: "completed", progress: 100 },
        );
      });
      return vi.fn();
    });
    const generateSeriesSummaries = vi.fn(() => Promise.resolve({
      completed_videos: ["linked-2"],
      skipped_videos: ["linked-1"],
      skipped_video_errors: [
        { video_id: "linked-1", title: "Linked 1", error: "源文件不存在" },
      ],
      cancelled_videos: [],
    }));
    const loadWorkspaceLibrary = vi.fn(() => Promise.resolve({
      series: [
        {
          id: "series-a",
          videos: [
            { id: "linked-1", processed: false, status: "linked", isLinked: true, title: "Linked 1" },
            { id: "linked-2", processed: true, status: "ready", isLinked: false, title: "Linked 2" },
          ],
        },
      ],
    }));
    vi.doMock("@src/features/workspace/model/workspaceApi", () => ({
      ...createWorkspaceApiMock(),
      generateSeriesSummaries,
      loadWorkspaceLibrary,
      startVideoDownload,
      subscribeVideoDownloadProgress,
    }));
    const { createWorkspaceContentActions } = await import(
      "@src/features/workspace/model/workspaceContentActions"
    );
    const dispatch = vi.fn();
    const actions = createWorkspaceContentActions({
      state: {
        selectedSeriesId: "series-a",
        selectedVideoId: null,
        selectedContextType: "series",
        library: {
          series: [
            {
              id: "series-a",
              videos: [
                { id: "linked-1", processed: false, status: "linked", isLinked: true, title: "Linked 1" },
                { id: "linked-2", processed: false, status: "linked", isLinked: true, title: "Linked 2" },
              ],
            },
          ],
        },
        ui: { transcriptEnhancementEnabled: true },
        seriesGenerationQueue: null,
        generationTasksByKey: {},
      },
      dispatch,
      selectedVideo: null,
    });

    await actions.onGenerateSeries();

    expect(startVideoDownload).toHaveBeenCalledWith("series-a", "linked-1");
    expect(startVideoDownload).toHaveBeenCalledWith("series-a", "linked-2");
    expect(generateSeriesSummaries).toHaveBeenCalledWith("series-a", {
      transcriptEnhancementEnabled: true,
      runId: expect.any(String),
    });
    const completedSnapshot = dispatch.mock.calls.find(([action]) => action.type === "generation_status_loaded")?.[0]?.snapshot;
    expect(completedSnapshot?.detail).toContain("跳过 1 个");
    expect(completedSnapshot?.detail).toContain("HTTP Error 403");
    expect(completedSnapshot?.detail).toContain("源文件不存在");
    expect(dispatch).toHaveBeenCalledWith(expect.objectContaining({
      type: "series_generation_queue_finished",
      seriesId: "series-a",
      status: "completed",
    }));
  });

  it("clears local video download state immediately after cancelling a selected download", async () => {
    vi.resetModules();
    const cancelVideoDownload = vi.fn(() => Promise.resolve({ status: "cancelling" }));
    vi.doMock("@src/features/workspace/model/workspaceApi", () => ({
      ...createWorkspaceApiMock(),
      cancelVideoDownload,
    }));
    const { createWorkspaceContentActions } = await import(
      "@src/features/workspace/model/workspaceContentActions"
    );
    const dispatch = vi.fn();
    const actions = createWorkspaceContentActions({
      state: {
        selectedSeriesId: "series-a",
        downloadingVideoKey: "series-a/linked-1",
      },
      dispatch,
      selectedVideo: null,
    });

    await actions.onDownloadVideo({ id: "linked-1" });

    expect(cancelVideoDownload).toHaveBeenCalledWith("series-a", "linked-1");
    expect(dispatch).toHaveBeenCalledWith({
      type: "video_download_cancel_requested",
      seriesId: "series-a",
      videoId: "linked-1",
    });
  });

  it("keeps a cancellation failure on the linked video instead of using the transient page error", async () => {
    vi.resetModules();
    const cancelVideoDownload = vi.fn(() => Promise.reject(new Error("取消请求未送达")));
    vi.doMock("@src/features/workspace/model/workspaceApi", () => ({
      ...createWorkspaceApiMock(),
      cancelVideoDownload,
    }));
    const { createWorkspaceContentActions } = await import(
      "@src/features/workspace/model/workspaceContentActions"
    );
    const dispatch = vi.fn();
    const actions = createWorkspaceContentActions({
      state: { selectedSeriesId: "series-a", downloadingVideoKey: "series-a/linked-1" },
      dispatch,
      selectedVideo: null,
    });

    await actions.onDownloadVideo({ id: "linked-1" });

    expect(dispatch).toHaveBeenCalledWith({
      type: "video_download_failed",
      seriesId: "series-a",
      videoId: "linked-1",
      error: "取消请求未送达",
    });
    expect(dispatch).not.toHaveBeenCalledWith(expect.objectContaining({ type: "load_failed" }));
  });

  it("exposes and cancels a running chaoxing import task", async () => {
    vi.resetModules();
    let progressListener;
    const importChaoxingCourse = vi.fn(() => Promise.resolve({
      taskId: "chaoxing-import-1",
      seriesId: "chaoxing-course-1",
    }));
    const cancelChaoxingImport = vi.fn(() => Promise.resolve({ status: "cancelling" }));
    const subscribeChaoxingImportProgress = vi.fn((taskId, listener) => {
      progressListener = listener;
      return vi.fn();
    });
    vi.doMock("@src/features/workspace/model/workspaceApi", () => ({
      ...createWorkspaceApiMock(),
      cancelChaoxingImport,
      importChaoxingCourse,
      subscribeChaoxingImportProgress,
    }));
    const { createWorkspaceContentActions } = await import(
      "@src/features/workspace/model/workspaceContentActions"
    );
    const actions = createWorkspaceContentActions({
      state: {},
      dispatch: vi.fn(),
      selectedVideo: null,
    });
    const onTaskStarted = vi.fn();

    const importTask = actions.onImportChaoxingCourse("course-1", null, { onTaskStarted });
    await Promise.resolve();
    await actions.onCancelChaoxingImport("chaoxing-import-1");
    progressListener({ status: "cancelled", detail: "超星课程导入已取消" });

    await expect(importTask).rejects.toThrow("超星课程导入已取消");
    expect(onTaskStarted).toHaveBeenCalledWith({
      taskId: "chaoxing-import-1",
      seriesId: "chaoxing-course-1",
    });
    expect(cancelChaoxingImport).toHaveBeenCalledWith("chaoxing-import-1");
  });
});

function createWorkspaceApiMock() {
  return {
    cancelChaoxingInit: vi.fn(),
    cancelChaoxingImport: vi.fn(),
    cancelVideoSummary: vi.fn(),
    createVideoNote: vi.fn(),
    deleteSeries: vi.fn(),
    deleteVideoNote: vi.fn(),
    deleteVideoSource: vi.fn(),
    generateSeriesSummaries: vi.fn(),
    generateVideoKnowledgeCards: vi.fn(),
    generateVideoMindmap: vi.fn(),
    generateVideoSummary: vi.fn(),
    processAgentVideo: vi.fn(),
    importChaoxingCourse: vi.fn(),
    importLocalPlaygroundVideos: vi.fn(),
    importLocalSeries: vi.fn(),
    importLocalSeriesVideos: vi.fn(),
    initChaoxing: vi.fn(),
    loadChaoxingCourses: vi.fn(),
    loadChaoxingStatus: vi.fn(),
    loadWorkspaceLibrary: vi.fn(),
    resolveBilibiliSeries: vi.fn(),
    resolveBilibiliVideo: vi.fn(),
    relinkExternalVideo: vi.fn(),
    startVideoDownload: vi.fn(),
    subscribeChaoxingImportProgress: vi.fn(),
    subscribeVideoDownloadProgress: vi.fn(),
    updateVideoNote: vi.fn(),
  };
}
