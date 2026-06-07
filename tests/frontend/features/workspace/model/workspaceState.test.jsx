import { beforeEach, describe, expect, it } from "vitest";

import {
  buildSeriesGenerationTaskKey,
  buildVideoGenerationTaskKey,
  createInitialWorkspaceState,
  getGenerationTaskForSelection,
  loadChatSessionIdsByScope,
  loadChatSessionListsByScope,
  normalizeUiSettings,
  removeChatSessionForScope,
  removeScopedValue,
  resolveChatSessionsForScope,
} from "@src/features/workspace/model/workspaceState";
import { workspaceReducer } from "@src/features/workspace/model/workspaceReducer";
import { getPendingVideosForSeriesGeneration } from "@src/features/workspace/model/workspaceContentActions";

const CHAT_SESSION_STORAGE_KEY = "video-include.chat-sessions";

describe("workspace UI settings", () => {
  it("normalizes the web search setting with a safe disabled default", () => {
    expect(normalizeUiSettings({}).webSearchEnabled).toBe(false);
    expect(normalizeUiSettings({ webSearchEnabled: true }).webSearchEnabled).toBe(true);
  });

  it("normalizes the answer detail level with medium as the safe default", () => {
    expect(normalizeUiSettings({}).answerDetailLevel).toBe("medium");
    expect(normalizeUiSettings({ answerDetailLevel: "short" }).answerDetailLevel).toBe("short");
    expect(normalizeUiSettings({ answerDetailLevel: "long" }).answerDetailLevel).toBe("long");
    expect(normalizeUiSettings({ answerDetailLevel: "verbose" }).answerDetailLevel).toBe("medium");
  });

  it("normalizes the reasoning effort with medium as the safe default", () => {
    expect(normalizeUiSettings({}).reasoningEffort).toBe("none");
    expect(normalizeUiSettings({ reasoningEffort: "none" }).reasoningEffort).toBe("none");
    expect(normalizeUiSettings({ reasoningEffort: "low" }).reasoningEffort).toBe("low");
    expect(normalizeUiSettings({ reasoningEffort: "medium" }).reasoningEffort).toBe("medium");
    expect(normalizeUiSettings({ reasoningEffort: "high" }).reasoningEffort).toBe("high");
    expect(normalizeUiSettings({ reasoningEffort: "minimal" }).reasoningEffort).toBe("none");
  });

  it("normalizes LiteLLM provider values with openai as the default", () => {
    expect(normalizeUiSettings({}).llmProvider).toBe("openai");
    expect(normalizeUiSettings({ llmProvider: "deepseek" }).llmProvider).toBe("deepseek");
    expect(normalizeUiSettings({ llmProvider: "dashscope" }).llmProvider).toBe("dashscope");
    expect(normalizeUiSettings({ llmProvider: "openai_compatible" }).llmProvider).toBe("openai");
    expect(normalizeUiSettings({ llmProvider: "openai_like" }).llmProvider).toBe("openai");
    expect(normalizeUiSettings({ llmProvider: "ollama_chat" }).llmProvider).toBe("openai");
    expect(normalizeUiSettings({ llmProvider: "vllm" }).llmProvider).toBe("openai");
  });

  it("preserves an empty HuggingFace endpoint to use the official source", () => {
    expect(normalizeUiSettings({ hfEndpoint: "" }).hfEndpoint).toBe("");
    expect(normalizeUiSettings({ hfEndpoint: "   " }).hfEndpoint).toBe("");
    expect(normalizeUiSettings({ hfEndpoint: " https://hf-mirror.com " }).hfEndpoint).toBe("https://hf-mirror.com");
  });
});

describe("workspaceState chat session persistence", () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  it("hydrates persisted multi-session metadata from storage", () => {
    window.localStorage.setItem(
      CHAT_SESSION_STORAGE_KEY,
      JSON.stringify({
        activeSessionIdsByScope: {
          "series|series-a|series-home": "series|series-a|series-home::2",
        },
        sessionListsByScope: {
          "series|series-a|series-home": [
            {
              id: "series|series-a|series-home::2",
              title: "第二个问题",
              createdAt: 2,
              updatedAt: 3,
            },
            {
              id: "series|series-a|series-home",
              title: "当前对话",
              createdAt: 1,
              updatedAt: 1,
            },
          ],
        },
      }),
    );

    const initialState = createInitialWorkspaceState();

    expect(initialState.chatSessionIdsByScope).toEqual({
      "series|series-a|series-home": "series|series-a|series-home::2",
    });
    expect(initialState.chatSessionListsByScope).toEqual({
      "series|series-a|series-home": [
        expect.objectContaining({
          id: "series|series-a|series-home::2",
          title: "第二个问题",
          createdAt: 2,
          updatedAt: 3,
        }),
        expect.objectContaining({
          id: "series|series-a|series-home",
          title: "当前对话",
          createdAt: 1,
          updatedAt: 1,
        }),
      ],
    });
  });

  it("upgrades legacy single-session storage into a selectable session list", () => {
    window.localStorage.setItem(
      CHAT_SESSION_STORAGE_KEY,
      JSON.stringify({
        "series|series-a|series-home": "series|series-a|series-home::legacy",
      }),
    );

    const sessionIdsByScope = loadChatSessionIdsByScope();
    const sessionListsByScope = loadChatSessionListsByScope();
    const resolved = resolveChatSessionsForScope(
      sessionIdsByScope,
      sessionListsByScope,
      "series|series-a|series-home",
    );

    expect(resolved.activeSessionId).toBe("series|series-a|series-home::legacy");
    expect(resolved.sessions).toEqual([
      expect.objectContaining({
        id: "series|series-a|series-home::legacy",
        title: "当前对话",
      }),
    ]);
    expect(resolved.chatSessionListsByScope["series|series-a|series-home"]).toHaveLength(1);
  });

  it("removes deleted session metadata and scoped records", () => {
    const sessionListsByScope = {
      "series|series-a|series-home": [
        { id: "series|series-a|series-home::2", title: "第二个问题" },
        { id: "series|series-a|series-home", title: "当前对话" },
      ],
    };
    const chatThreads = {
      "series|series-a|series-home::2": [{ id: "msg-2", role: "assistant", content: "第二个回答" }],
      "series|series-a|series-home": [{ id: "msg-1", role: "assistant", content: "第一个回答" }],
    };

    expect(
      removeChatSessionForScope(
        sessionListsByScope,
        "series|series-a|series-home",
        "series|series-a|series-home::2",
      )["series|series-a|series-home"],
    ).toEqual([
      expect.objectContaining({ id: "series|series-a|series-home", title: "当前对话" }),
    ]);
    expect(removeScopedValue(chatThreads, "series|series-a|series-home::2")).toEqual({
      "series|series-a|series-home": [{ id: "msg-1", role: "assistant", content: "第一个回答" }],
    });
  });
});

describe("workspaceReducer knowledge memory status", () => {
  it("stores the latest long-term memory snapshot", () => {
    const state = createInitialWorkspaceState();
    const snapshot = {
      status: "running",
      stage: "index",
      progress: 20,
      detail: "正在重建长期记忆索引",
      error: null,
    };

    const nextState = workspaceReducer(state, {
      type: "knowledge_memory_status_loaded",
      snapshot,
    });

    expect(nextState.knowledgeMemorySnapshot).toBe(snapshot);
  });
});

describe("workspaceReducer generation task state", () => {
  it("preserves video generation task state across scope switches", () => {
    const library = {
      workspace: { id: "workspace", title: "Workspace" },
      series: [
        {
          id: "series-a",
          title: "Series A",
          videos: [
            { id: "video-1", title: "Video 1", source_name: "video-1.mp4", processed: false, status: "pending" },
            { id: "video-2", title: "Video 2", source_name: "video-2.mp4", processed: false, status: "pending" },
          ],
        },
      ],
    };
    let state = workspaceReducer(createInitialWorkspaceState(), {
      type: "workspace_loaded",
      library,
    });
    state = workspaceReducer(state, { type: "video_selected", seriesId: "series-a", videoId: "video-1" });
    state = workspaceReducer(state, {
      type: "generation_status_loaded",
      taskKey: buildVideoGenerationTaskKey("series-a", "video-1"),
      mode: "video",
      seriesId: "series-a",
      videoId: "video-1",
      snapshot: { status: "running", stage: "summarize", progress: 60, detail: "正在生成", error: null },
    });

    const switched = workspaceReducer(state, { type: "video_selected", seriesId: "series-a", videoId: "video-2" });

    expect(switched.generationTasksByKey[buildVideoGenerationTaskKey("series-a", "video-1")]).toEqual(
      expect.objectContaining({
        mode: "video",
        seriesId: "series-a",
        videoId: "video-1",
        snapshot: expect.objectContaining({ status: "running", progress: 60 }),
      }),
    );
  });

  it("keeps series generation task state when switching from series to video and back", () => {
    const library = {
      workspace: { id: "workspace", title: "Workspace" },
      series: [
        {
          id: "series-a",
          title: "Series A",
          videos: [
            { id: "video-1", title: "Video 1", source_name: "video-1.mp4", processed: false, status: "pending" },
          ],
        },
      ],
    };
    let state = workspaceReducer(createInitialWorkspaceState(), {
      type: "workspace_loaded",
      library,
    });
    state = workspaceReducer(state, { type: "series_selected", seriesId: "series-a" });
    state = workspaceReducer(state, {
      type: "generation_status_loaded",
      taskKey: buildSeriesGenerationTaskKey("series-a"),
      mode: "series",
      seriesId: "series-a",
      videoId: null,
      snapshot: { status: "running", stage: "batch", progress: 40, detail: "正在处理 2/5", error: null },
    });

    state = workspaceReducer(state, { type: "video_selected", seriesId: "series-a", videoId: "video-1" });
    const restored = workspaceReducer(state, { type: "series_context_selected" });

    expect(restored.generationTasksByKey[buildSeriesGenerationTaskKey("series-a")]).toEqual(
      expect.objectContaining({
        mode: "series",
        seriesId: "series-a",
        snapshot: expect.objectContaining({ status: "running", progress: 40 }),
      }),
    );
  });

  it("does not show a series generation task as the selected video's own generation task", () => {
    const state = {
      ...createInitialWorkspaceState(),
      selectedContextType: "video",
      selectedSeriesId: "series-a",
      selectedVideoId: "video-1",
      generationTasksByKey: {
        [buildSeriesGenerationTaskKey("series-a")]: {
          taskKey: buildSeriesGenerationTaskKey("series-a"),
          mode: "series",
          seriesId: "series-a",
          videoId: null,
          snapshot: {
            status: "running",
            stage: "transcribe",
            progress: 35,
            detail: "正在处理 1/3：Video 1",
            error: null,
          },
          subscriptionActive: true,
        },
      },
    };

    expect(getGenerationTaskForSelection(state)).toBeNull();
  });

  it("does not replace the currently selected summary with a stale background success", () => {
    const initialState = {
      ...createInitialWorkspaceState(),
      library: {
        workspace: { id: "workspace", title: "Workspace" },
        series: [
          {
            id: "series-a",
            title: "Series A",
            videos: [
              { id: "video-1", title: "Video 1", source_name: "video-1.mp4", processed: false, status: "pending" },
              { id: "video-2", title: "Video 2", source_name: "video-2.mp4", processed: false, status: "pending" },
            ],
          },
        ],
      },
      selectedSeriesId: "series-a",
      selectedVideoId: "video-2",
      selectedContextType: "video",
      summary: {
        title: "Current Video",
        chapters: [{ id: "chapter-current" }],
      },
      tools: {
        overview: { generated: false, status: "pending" },
        mindmap: { available: false, generated: false, status: "blocked" },
        knowledgeCards: { available: false, generated: false, status: "blocked" },
      },
    };

    const nextState = workspaceReducer(initialState, {
      type: "generation_succeeded",
      taskKey: buildVideoGenerationTaskKey("series-a", "video-1"),
      seriesId: "series-a",
      videoId: "video-1",
      summary: {
        title: "Background Video",
        chapters: [{ id: "chapter-background" }],
      },
    });

    expect(nextState.summary.title).toBe("Current Video");
    expect(
      nextState.library.series[0].videos.find((video) => video.id === "video-1"),
    ).toEqual(expect.objectContaining({ processed: true, status: "ready" }));
  });
});

describe("workspace chat stream errors", () => {
  it("adds a failed assistant message when a stream fails before any progress event", () => {
    const state = {
      ...createInitialWorkspaceState(),
      chatScopeKey: "video|series-a|video-a|studio",
      chatPending: true,
      chatMessages: [],
      chatThreads: {
        "video|series-a|video-a|studio": [],
      },
    };

    const nextState = workspaceReducer(state, {
      type: "chat_stream_event_received",
      chatScopeKey: "video|series-a|video-a|studio",
      requestId: 123,
      event: {
        type: "error",
        payload: { message: "模型请求被上游网关拦截" },
      },
    });

    expect(nextState.chatPending).toBe(false);
    expect(nextState.chatMessages).toEqual([
      expect.objectContaining({
        id: "assistant-123",
        content: "模型请求被上游网关拦截",
        streamingStatus: "failed",
      }),
    ]);
  });

  it("marks the understand-query stage as failed when the stream errors after that stage starts", () => {
    const chatScopeKey = "series|series-a|series-home";
    const requestId = 123;
    let state = {
      ...createInitialWorkspaceState(),
      chatScopeKey,
      chatPending: true,
      chatMessages: [],
      chatThreads: {
        [chatScopeKey]: [],
      },
    };

    state = workspaceReducer(state, {
      type: "chat_stream_event_received",
      chatScopeKey,
      requestId,
      event: {
        type: "thinking_started",
        payload: { message: "正在执行图节点" },
      },
    });
    state = workspaceReducer(state, {
      type: "chat_stream_event_received",
      chatScopeKey,
      requestId,
      event: {
        type: "stage_started",
        payload: {
          stage_id: "stage-understand-query",
          node_id: "understand_query",
          label: "理解问题",
        },
      },
    });
    state = workspaceReducer(state, {
      type: "chat_stream_event_received",
      chatScopeKey,
      requestId,
      event: {
        type: "error",
        payload: { message: "模型服务调用失败：APIConnectionError: Connection refused" },
      },
    });

    expect(state.chatPending).toBe(false);
    expect(state.chatMessages).toEqual([
      expect.objectContaining({
        id: `thought-${requestId}`,
        content: "执行失败",
        thoughtTrace: expect.objectContaining({
          status: "failed",
          summary: "模型服务调用失败：APIConnectionError: Connection refused",
          stages: [
            expect.objectContaining({
              nodeId: "understand_query",
              label: "理解问题",
              status: "failed",
            }),
          ],
        }),
      }),
    ]);
  });
});

describe("workspaceContentActions series generation", () => {
  it("selects only unprocessed videos for one-click sequential generation", () => {
    const library = {
      series: [
        {
          id: "series-a",
          videos: [
            { id: "video-1", processed: true },
            { id: "video-2", processed: false },
            { id: "video-3", processed: false, status: "linked", isLinked: true },
          ],
        },
      ],
    };

    expect(getPendingVideosForSeriesGeneration(library, "series-a").map((video) => video.id)).toEqual([
      "video-2",
      "video-3",
    ]);
  });

  it("tracks one-click series queue from backend series progress", () => {
    let state = workspaceReducer(createInitialWorkspaceState(), {
      type: "series_generation_queue_started",
      seriesId: "series-a",
      total: 3,
    });
    state = workspaceReducer(state, {
      type: "generation_progress_updated",
      taskKey: buildSeriesGenerationTaskKey("series-a"),
      mode: "series",
      seriesId: "series-a",
      videoId: null,
      progress: 66.67,
      snapshot: {
        status: "running",
        stage: "batch",
        progress: 33.34,
        detail: "已完成 1 / 3，完成 1，取消 0",
        error: null,
      },
      subscriptionActive: true,
    });

    expect(state.seriesGenerationQueue).toEqual(
      expect.objectContaining({
        seriesId: "series-a",
        total: 3,
        completed: 1,
        detail: "已完成 1/3",
        status: "running",
      }),
    );
  });

  it("ignores per-worker series progress detail for queue completed count", () => {
    let state = workspaceReducer(createInitialWorkspaceState(), {
      type: "series_generation_queue_started",
      seriesId: "series-a",
      total: 4,
    });
    state = workspaceReducer(state, {
      type: "generation_progress_updated",
      taskKey: buildSeriesGenerationTaskKey("series-a"),
      mode: "series",
      seriesId: "series-a",
      videoId: null,
      progress: 75,
      snapshot: {
        status: "running",
        stage: "transcribe",
        progress: 75,
        detail: "正在处理 3/4：Video 3",
        error: null,
      },
      subscriptionActive: true,
    });

    expect(state.seriesGenerationQueue).toEqual(
      expect.objectContaining({
        completed: 0,
        detail: "已完成 0/4",
      }),
    );
  });

  it("clears active linked video download when series queue is cancelled", () => {
    let state = workspaceReducer(
      {
        ...createInitialWorkspaceState(),
        library: {
          series: [
            {
              id: "series-a",
              title: "Series A",
              videos: [
                {
                  id: "video-1",
                  title: "Video 1",
                  sourceName: "video-1.mp4",
                  processed: false,
                  status: "linked",
                  isLinked: true,
                },
              ],
            },
          ],
        },
      },
      {
        type: "series_generation_queue_started",
        seriesId: "series-a",
        total: 1,
      },
    );
    state = workspaceReducer(state, {
      type: "series_generation_queue_download_started",
      seriesId: "series-a",
      videoId: "video-1",
      videoTitle: "Video 1",
      detail: "正在下载未缓存视频 1/1",
    });
    state = workspaceReducer(state, {
      type: "video_download_started",
      seriesId: "series-a",
      videoId: "video-1",
    });

    state = workspaceReducer(state, {
      type: "series_generation_queue_finished",
      seriesId: "series-a",
      status: "cancelled",
    });

    expect(state.downloadingVideoKey).toBeNull();
    expect(state.videoDownloadProgress).toBeNull();
    expect(state.library.series[0].videos[0].status).toBe("linked");
  });

  it("clears series queue download marker when terminal series progress arrives", () => {
    let state = workspaceReducer(
      {
        ...createInitialWorkspaceState(),
        library: {
          series: [
            {
              id: "series-a",
              title: "Series A",
              videos: [
                {
                  id: "video-1",
                  title: "Video 1",
                  sourceName: "video-1.mp4",
                  processed: false,
                  status: "linked",
                  isLinked: true,
                },
              ],
            },
          ],
        },
        selectedContextType: "series",
        selectedSeriesId: "series-a",
      },
      {
        type: "series_generation_queue_started",
        seriesId: "series-a",
        total: 1,
      },
    );
    state = workspaceReducer(state, {
      type: "series_generation_queue_download_started",
      seriesId: "series-a",
      videoId: "video-1",
      videoTitle: "Video 1",
      detail: "正在下载未缓存视频 1/1",
    });

    state = workspaceReducer(state, {
      type: "generation_progress_updated",
      taskKey: buildSeriesGenerationTaskKey("series-a"),
      mode: "series",
      seriesId: "series-a",
      videoId: null,
      progress: null,
      snapshot: {
        status: "cancelled",
        stage: "cancelled",
        progress: null,
        detail: "任务已取消",
        error: null,
      },
      subscriptionActive: false,
    });

    expect(state.seriesGenerationQueue).toEqual(
      expect.objectContaining({
        status: "cancelled",
        downloadVideoId: null,
        downloadVideoTitle: null,
      }),
    );
  });

  it("ignores stale series cancellation from an older queue run", () => {
    let state = workspaceReducer(createInitialWorkspaceState(), {
      type: "series_generation_queue_started",
      seriesId: "series-a",
      runId: "run-a",
      total: 2,
    });
    state = workspaceReducer(state, {
      type: "series_generation_queue_cancelling",
      seriesId: "series-a",
      runId: "run-a",
    });
    state = workspaceReducer(state, {
      type: "series_generation_queue_started",
      seriesId: "series-a",
      runId: "run-b",
      total: 2,
    });

    state = workspaceReducer(state, {
      type: "series_generation_queue_finished",
      seriesId: "series-a",
      runId: "run-a",
      status: "cancelled",
    });

    expect(state.seriesGenerationQueue).toEqual(
      expect.objectContaining({
        runId: "run-b",
        status: "running",
      }),
    );
  });

  it("ignores stale terminal series progress from an older queue run", () => {
    let state = workspaceReducer(createInitialWorkspaceState(), {
      type: "series_generation_queue_started",
      seriesId: "series-a",
      runId: "run-b",
      total: 2,
    });

    state = workspaceReducer(state, {
      type: "generation_progress_updated",
      taskKey: buildSeriesGenerationTaskKey("series-a"),
      mode: "series",
      seriesId: "series-a",
      runId: "run-a",
      videoId: null,
      progress: null,
      snapshot: {
        status: "cancelled",
        stage: "cancelled",
        progress: null,
        detail: "任务已取消",
        error: null,
      },
      subscriptionActive: false,
    });

    expect(state.seriesGenerationQueue).toEqual(
      expect.objectContaining({
        runId: "run-b",
        status: "running",
      }),
    );
  });
});
