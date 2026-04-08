import { act, renderHook, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { useWorkspaceController } from "./useWorkspaceController";

const workspaceApi = vi.hoisted(() => ({
  clearAgentSession: vi.fn(),
  cancelFasterWhisperModelDownload: vi.fn(),
  createVideoNote: vi.fn(),
  deleteVideoNote: vi.fn(),
  downloadFasterWhisperModel: vi.fn(),
  generateVideoKnowledgeCards: vi.fn(),
  generateVideoMindmap: vi.fn(),
  generateVideoSummary: vi.fn(),
  getVideoPreviewUrl: vi.fn(),
  loadAgentContextUsage: vi.fn(),
  loadAgentSessionRecovery: vi.fn(),
  loadFasterWhisperModels: vi.fn(),
  loadProviderSettings: vi.fn(),
  loadVideoKnowledgeCards: vi.fn(),
  loadVideoMindmap: vi.fn(),
  loadVideoNotes: vi.fn(),
  loadVideoSummary: vi.fn(),
  streamAgentChat: vi.fn(),
  loadWorkspaceSettings: vi.fn(),
  loadVideoTools: vi.fn(),
  loadWorkspaceLibrary: vi.fn(),
  subscribeFasterWhisperModelDownloadProgress: vi.fn(),
  subscribeVideoGenerationProgress: vi.fn(),
  updateVideoNote: vi.fn(),
  updateProviderSettings: vi.fn(),
  updateWorkspaceSettings: vi.fn(),
}));

vi.mock("./workspaceApi", () => workspaceApi);

describe("useWorkspaceController", () => {
  beforeEach(() => {
    window.localStorage.clear();
    vi.clearAllMocks();

    workspaceApi.loadWorkspaceLibrary.mockResolvedValue({
      workspace: { id: "video-include", title: "Video Include" },
      series: [
        {
          id: "series-a",
          title: "Series A",
          videos: [
            {
              id: "video-1",
              title: "Video 1",
              sourceName: "video-1.mp4",
              processed: true,
              status: "ready",
            },
            {
              id: "video-2",
              title: "Video 2",
              sourceName: "video-2.mp4",
              processed: false,
              status: "idle",
            },
          ],
        },
      ],
    });
    workspaceApi.loadFasterWhisperModels.mockResolvedValue([]);
    workspaceApi.loadAgentContextUsage.mockResolvedValue({
      sessionId: "series|series-a|series-home",
      scopeType: "series",
      memoryKey: "series|series-a|series-home",
      estimatedTotalTokens: 2048,
      windowTokens: 200000,
      reservedOutputTokens: 20000,
      warningThresholdTokens: 120000,
      compactThresholdTokens: 160000,
      blockingThresholdTokens: 184000,
      remainingTokens: 197952,
      usagePercent: 1.02,
      level: "normal",
      sources: [
        { id: "system_prompt", label: "系统指令", estimatedTokens: 1000 },
        { id: "recent_messages", label: "最近消息", estimatedTokens: 500 },
        { id: "tool_results", label: "工具结果", estimatedTokens: 0 },
        { id: "workspace_context", label: "工作区上下文", estimatedTokens: 548 },
      ],
    });
    workspaceApi.loadAgentSessionRecovery.mockResolvedValue({
      sessionId: "series|series-a|series-home",
      restored: false,
      memoryKey: null,
      updatedAt: null,
      messageCount: 0,
      messages: [],
    });
    workspaceApi.clearAgentSession.mockResolvedValue({ status: "cleared" });
    workspaceApi.loadWorkspaceSettings.mockResolvedValue({
      theme: "light",
      showTakeaways: true,
      transcriptEnhancementEnabled: true,
      asrModelQuality: "large-v3-turbo",
      transcriptionMode: "fast",
    });
    workspaceApi.loadProviderSettings.mockResolvedValue({
      llmProvider: "openai_compatible",
      openaiBaseUrl: "http://127.0.0.1:8317/v1",
      openaiModel: "gpt-5.4",
      hasOpenaiApiKey: false,
      openaiApiKeyMasked: "",
      openaiApiKey: "",
    });
    workspaceApi.loadVideoTools.mockResolvedValue({
      seriesId: "series-a",
      videoId: "video-1",
      overview: { id: "overview", title: "AI概况", available: true, generated: true, status: "ready" },
      knowledgeCards: { id: "knowledge-cards", title: "知识卡片", available: true, generated: true, status: "ready" },
      mindmap: { id: "mindmap", title: "思维导图", available: true, generated: false, status: "available" },
      notes: { id: "notes", title: "笔记", available: true, generated: true, status: "ready" },
      preview: {
        id: "preview",
        title: "视频预览",
        available: true,
        generated: true,
        status: "ready",
        previewUrl: "/api/videos/series-a/video-1/preview",
      },
      aiTodo: "AI 已支持工具联动。",
    });
    workspaceApi.loadVideoSummary.mockResolvedValue({
      title: "Video 1",
      one_sentence_summary: "",
      core_problem: "",
      key_takeaways: [],
      chapters: [],
    });
    workspaceApi.loadVideoKnowledgeCards.mockResolvedValue({
      seriesId: "series-a",
      videoId: "video-1",
      title: "Video 1",
      cards: [],
    });
    workspaceApi.loadVideoMindmap.mockResolvedValue(null);
    workspaceApi.loadVideoNotes.mockResolvedValue({
      seriesId: "series-a",
      videoId: "video-1",
      title: "Video 1",
      notes: [],
    });
    workspaceApi.streamAgentChat.mockImplementation(async (sessionId, message, context, listener) => {
      listener({ type: "thinking_started", payload: { message: "正在分析当前问题" } });
      listener({ type: "thinking_completed", payload: { summary: "先读取转写全文，再定位视频时间点。", duration_ms: 20 } });
      listener({ type: "tool_started", payload: { tool_call_id: "tool-1", tool_name: "get_video_transcript", index: 1 } });
      listener({
        type: "tool_completed",
        payload: {
          tool_call_id: "tool-1",
          tool_name: "get_video_transcript",
          status: "ok",
          duration_ms: 10,
          payload: {
            series_id: "series-a",
            video_id: "video-1",
            title: "Video 1",
            generated: true,
            duration_seconds: 300,
            segments: [
              {
                start_seconds: 128,
                end_seconds: 146,
                text: "后续项目会用到百度地图 API，需要提前申请 API Key。",
              },
            ],
          },
        },
      });
      listener({ type: "tool_started", payload: { tool_call_id: "tool-2", tool_name: "video_seek", index: 2 } });
      listener({
        type: "tool_completed",
        payload: {
          tool_call_id: "tool-2",
          tool_name: "video_seek",
          status: "ok",
          duration_ms: 6,
          payload: {
            query: "百度地图 API Key",
            seek_seconds: 128,
            match_end_seconds: 146,
            matched_text: "后续项目会用到百度地图 API，需要提前申请 API Key。",
            chapter_title: "准备工作",
          },
        },
      });
      listener({ type: "tool_chain_completed", payload: { count: 2, duration_ms: 16 } });
      listener({ type: "answer_started", payload: { message: "正在组织回答" } });
      listener({ type: "answer_delta", payload: { delta: "相关内容在 02:08 左右，" } });
      listener({ type: "answer_delta", payload: { delta: "我已经帮你打开视频。" } });
      listener({
        type: "answer_completed",
        payload: {
          message: "相关内容在 02:08 左右，我已经帮你打开视频。",
          duration_ms: 30,
        },
      });
    });
    workspaceApi.getVideoPreviewUrl.mockReturnValue("/api/videos/series-a/video-1/preview");
    workspaceApi.subscribeFasterWhisperModelDownloadProgress.mockReturnValue(() => {});
    workspaceApi.subscribeVideoGenerationProgress.mockReturnValue(() => {});
    workspaceApi.createVideoNote.mockResolvedValue({
      id: "note-1",
      title: "重点",
      content: "记录一下这里讲了 API Key 的前置准备。",
      source: "agent",
      createdAt: "2026-04-04T10:00:00Z",
      updatedAt: "2026-04-04T10:00:00Z",
    });
    workspaceApi.deleteVideoNote.mockResolvedValue({ status: "deleted" });
    workspaceApi.updateVideoNote.mockResolvedValue({
      id: "note-1",
      title: "更新后的重点",
      content: "更新内容",
      source: "manual",
      createdAt: "2026-04-04T10:00:00Z",
      updatedAt: "2026-04-04T10:01:00Z",
    });
    workspaceApi.updateProviderSettings.mockResolvedValue({});
    workspaceApi.updateWorkspaceSettings.mockResolvedValue({});
    workspaceApi.generateVideoKnowledgeCards.mockResolvedValue({
      seriesId: "series-a",
      videoId: "video-1",
      title: "Video 1",
      cards: [],
    });
  });

  it("applies agent seek results to preview state", async () => {
    const { result } = renderHook(() => useWorkspaceController());

    await waitFor(() => expect(result.current.state.loading).toBe(false));

    act(() => {
      result.current.onSelectSeries("series-a");
    });
    act(() => {
      result.current.onSelectVideo("series-a", "video-1");
    });

    await waitFor(() => expect(result.current.tools?.preview?.previewUrl).toBe("/api/videos/series-a/video-1/preview"));
    await waitFor(() => expect(result.current.contextUsage?.estimatedTotalTokens).toBe(2048));

    await act(async () => {
      await result.current.onSubmitChat("百度地图 API Key 在视频什么位置？");
    });

    expect(workspaceApi.streamAgentChat).toHaveBeenCalledWith(
      "video|series-a|video-1|studio",
      "百度地图 API Key 在视频什么位置？",
      {
        scope_type: "video",
        series_id: "series-a",
        series_title: "Series A",
        video_id: "video-1",
        video_title: "Video 1",
        selected_tool: "studio",
      },
      expect.any(Function),
    );
    expect(result.current.state.selectedToolId).toBe("studio");
    expect(result.current.previewSeekRequest).toEqual(
      expect.objectContaining({
        seconds: 128,
        endSeconds: 146,
        query: "百度地图 API Key",
        matchedText: "后续项目会用到百度地图 API，需要提前申请 API Key。",
        chapterTitle: "准备工作",
      }),
    );
    expect(result.current.chatMessages).toEqual(expect.arrayContaining([
      expect.objectContaining({
        kind: "seek-reference",
        seekReference: expect.objectContaining({
          seconds: 128,
          endSeconds: 146,
          matchedText: "后续项目会用到百度地图 API，需要提前申请 API Key。",
        }),
      }),
    ]));
    expect(result.current.chatMessages.at(-1)).toEqual(
      expect.objectContaining({
        role: "assistant",
        content: "相关内容在 02:08 左右，我已经帮你打开视频。",
        meta: expect.stringMatching(/^Notebook Assistant • 用时 /),
      }),
    );
    expect(workspaceApi.loadAgentContextUsage).toHaveBeenCalledWith(
      "video|series-a|video-1|studio",
      {
        scope_type: "video",
        series_id: "series-a",
        series_title: "Series A",
        video_id: "video-1",
        video_title: "Video 1",
        selected_tool: "studio",
      },
    );
  });

  it("keeps chat history when switching videos inside the same series", async () => {
    const { result } = renderHook(() => useWorkspaceController());

    await waitFor(() => expect(result.current.state.loading).toBe(false));

    act(() => {
      result.current.onSelectSeries("series-a");
    });
    act(() => {
      result.current.onSelectVideo("series-a", "video-1");
    });

    await act(async () => {
      await result.current.onSubmitChat("帮我记住这个系列的重点");
    });

    act(() => {
      result.current.onSelectVideo("series-a", "video-2");
    });

    expect(result.current.chatMessages.some((message) => message.content === "帮我记住这个系列的重点")).toBe(false);
    expect(
      result.current.chatMessages.some((message) => message.content === "相关内容在 02:08 左右，我已经帮你打开视频。"),
    ).toBe(false);
    expect(result.current.chatMessages).toEqual(expect.arrayContaining([
      expect.objectContaining({ id: "assistant-welcome", role: "assistant" }),
    ]));
  });

  it("hydrates recovered chat messages for the current scope", async () => {
    workspaceApi.loadAgentSessionRecovery.mockResolvedValueOnce({
      sessionId: "series|series-a|series-home",
      restored: true,
      memoryKey: "series|series-a|series-home",
      updatedAt: "2026-04-05T10:00:00Z",
      messageCount: 2,
      messages: [
        {
          id: "recovered-series|series-a|series-home-0",
          role: "user",
          content: "之前的问题",
          meta: "You • 已恢复",
        },
        {
          id: "recovered-series|series-a|series-home-1",
          role: "assistant",
          content: "之前的回答",
          meta: "Notebook Assistant • 已恢复",
        },
      ],
    });

    const { result } = renderHook(() => useWorkspaceController());

    await waitFor(() => expect(result.current.state.loading).toBe(false));
    act(() => {
      result.current.onSelectSeries("series-a");
    });
    await waitFor(() => expect(result.current.chatMessages.some((message) => message.content === "之前的回答")).toBe(true));
    expect(workspaceApi.loadAgentSessionRecovery).toHaveBeenCalledWith(
      "series|series-a|series-home",
      {
        scope_type: "series",
        series_id: "series-a",
        series_title: "Series A",
        video_id: null,
        video_title: null,
        selected_tool: "series-home",
      },
    );
  });

  it("opens preview only after the user clicks a seek reference", async () => {
    const { result } = renderHook(() => useWorkspaceController());

    await waitFor(() => expect(result.current.state.loading).toBe(false));
    act(() => {
      result.current.onSelectSeries("series-a");
    });
    act(() => {
      result.current.onSelectVideo("series-a", "video-1");
    });

    await act(async () => {
      await result.current.onSubmitChat("百度地图 API Key 在视频什么位置？");
    });

    const seekReference = result.current.chatMessages.find((message) => message.kind === "seek-reference")?.seekReference;
    expect(result.current.state.selectedToolId).toBe("studio");

    act(() => {
      result.current.onOpenSeekReference(seekReference);
    });

    expect(result.current.state.selectedToolId).toBe("preview");
    expect(result.current.previewSeekRequest).toEqual(
      expect.objectContaining({
        seconds: 128,
        endSeconds: 146,
      }),
    );
  });

  it("restores the previously active chat session for the selected scope", async () => {
    window.localStorage.setItem(
      "video-include.chat-sessions",
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
    workspaceApi.loadAgentSessionRecovery.mockResolvedValueOnce({
      sessionId: "series|series-a|series-home::2",
      restored: true,
      memoryKey: "series|series-a|series-home::2",
      updatedAt: "2026-04-05T10:00:00Z",
      messageCount: 2,
      messages: [
        {
          id: "recovered-series|series-a|series-home::2-0",
          role: "user",
          content: "第二个问题",
          meta: "You • 已恢复",
        },
        {
          id: "recovered-series|series-a|series-home::2-1",
          role: "assistant",
          content: "第二个回答",
          meta: "Notebook Assistant • 已恢复",
        },
      ],
    });

    const { result } = renderHook(() => useWorkspaceController());

    await waitFor(() => expect(result.current.state.loading).toBe(false));
    act(() => {
      result.current.onSelectSeries("series-a");
    });

    await waitFor(() => expect(result.current.activeChatSessionId).toBe("series|series-a|series-home::2"));
    await waitFor(() => expect(result.current.chatMessages.some((message) => message.content === "第二个回答")).toBe(true));
    expect(result.current.chatSessions).toEqual([
      expect.objectContaining({ id: "series|series-a|series-home::2", title: "第二个问题" }),
      expect.objectContaining({ id: "series|series-a|series-home", title: "当前对话" }),
    ]);
  });

  it("starts a new chat session and clears the visible history", async () => {
    const { result } = renderHook(() => useWorkspaceController());

    await waitFor(() => expect(result.current.state.loading).toBe(false));
    act(() => {
      result.current.onSelectSeries("series-a");
    });

    await act(async () => {
      await result.current.onSubmitChat("这个系列先看哪一节？");
    });
    expect(result.current.chatMessages.some((message) => message.content === "这个系列先看哪一节？")).toBe(true);

    act(() => {
      result.current.onStartNewChat();
    });

    expect(result.current.chatMessages).toEqual([
      expect.objectContaining({
        id: "assistant-welcome",
        role: "assistant",
      }),
    ]);
    expect(result.current.chatSessions).toHaveLength(2);
    expect(result.current.activeChatSessionId).toContain("::");
  });

  it("switches between chat sessions within the same scope", async () => {
    const { result } = renderHook(() => useWorkspaceController());

    await waitFor(() => expect(result.current.state.loading).toBe(false));
    act(() => {
      result.current.onSelectSeries("series-a");
    });

    await act(async () => {
      await result.current.onSubmitChat("第一个问题");
    });
    const firstSessionId = result.current.activeChatSessionId;

    act(() => {
      result.current.onStartNewChat();
    });
    const secondSessionId = result.current.activeChatSessionId;

    await act(async () => {
      await result.current.onSubmitChat("第二个问题");
    });

    act(() => {
      result.current.onSelectChatSession(firstSessionId);
    });

    expect(firstSessionId).not.toBe(secondSessionId);
    expect(result.current.chatMessages.some((message) => message.content === "第一个问题")).toBe(true);
    expect(result.current.chatMessages.some((message) => message.content === "第二个问题")).toBe(false);
  });

  it("deletes only the active chat session", async () => {
    const { result } = renderHook(() => useWorkspaceController());

    await waitFor(() => expect(result.current.state.loading).toBe(false));
    act(() => {
      result.current.onSelectSeries("series-a");
    });

    await act(async () => {
      await result.current.onSubmitChat("第一个问题");
    });
    const firstSessionId = result.current.activeChatSessionId;

    act(() => {
      result.current.onStartNewChat();
    });

    await act(async () => {
      await result.current.onSubmitChat("第二个问题");
    });
    const secondSessionId = result.current.activeChatSessionId;

    await act(async () => {
      await result.current.onClearChat();
    });

    expect(workspaceApi.clearAgentSession).toHaveBeenCalledWith(
      secondSessionId,
      expect.any(Object),
    );
    expect(result.current.chatSessions.some((session) => session.id === secondSessionId)).toBe(false);
    expect(result.current.activeChatSessionId).toBe(firstSessionId);
    expect(result.current.chatMessages.some((message) => message.content === "第一个问题")).toBe(true);
  });

  it("recreates a fresh default session when deleting the last chat session", async () => {
    const { result } = renderHook(() => useWorkspaceController());

    await waitFor(() => expect(result.current.state.loading).toBe(false));
    act(() => {
      result.current.onSelectSeries("series-a");
    });

    await act(async () => {
      await result.current.onSubmitChat("这个系列先看哪一节？");
    });
    const deletedSessionId = result.current.state.chatScopeKey;

    await act(async () => {
      await result.current.onClearChat();
    });

    expect(workspaceApi.clearAgentSession).toHaveBeenCalledWith(
      deletedSessionId,
      {
        scope_type: "series",
        series_id: "series-a",
        series_title: "Series A",
        video_id: null,
        video_title: null,
        selected_tool: "series-home",
      },
    );
    expect(result.current.chatSessions).toEqual([
      expect.objectContaining({
        id: "series|series-a|series-home",
        title: "当前对话",
      }),
    ]);
    expect(result.current.activeChatSessionId).toBe("series|series-a|series-home");
    expect(result.current.chatMessages).toEqual([
      expect.objectContaining({
        id: "assistant-welcome",
        role: "assistant",
      }),
    ]);
  });

  it("creates note when agent returns save_note action", async () => {
    workspaceApi.loadVideoNotes.mockResolvedValueOnce({
      seriesId: "series-a",
      videoId: "video-1",
      title: "Video 1",
      notes: [
        {
          id: "note-1",
          title: "重点",
          content: "记录一下这里讲了 API Key 的前置准备。",
          source: "agent",
          createdAt: "2026-04-04T10:00:00Z",
          updatedAt: "2026-04-04T10:00:00Z",
        },
      ],
    });
    workspaceApi.streamAgentChat.mockImplementationOnce(async (_sessionId, _message, _context, listener) => {
      listener({ type: "thinking_started", payload: { message: "正在分析当前问题" } });
      listener({ type: "tool_started", payload: { tool_call_id: "tool-1", tool_name: "save_note", index: 1 } });
      listener({
        type: "tool_completed",
        payload: {
          tool_call_id: "tool-1",
          tool_name: "save_note",
          status: "ok",
          duration_ms: 8,
          payload: {
            action: "save_note",
            selected_tool: "notes",
            note_title: "重点",
            note_content: "记录一下这里讲了 API Key 的前置准备。",
            note_source: "agent",
          },
        },
      });
      listener({ type: "tool_chain_completed", payload: { count: 1, duration_ms: 8 } });
      listener({ type: "answer_started", payload: { message: "正在组织回答" } });
      listener({ type: "answer_delta", payload: { delta: "我已经帮你记到笔记里了。" } });
      listener({ type: "answer_completed", payload: { message: "我已经帮你记到笔记里了。", duration_ms: 12 } });
    });

    const { result } = renderHook(() => useWorkspaceController());

    await waitFor(() => expect(result.current.state.loading).toBe(false));

    act(() => {
      result.current.onSelectSeries("series-a");
    });
    act(() => {
      result.current.onSelectVideo("series-a", "video-1");
    });

    await act(async () => {
      await result.current.onSubmitChat("帮我记一下这个视频重点");
    });

    expect(workspaceApi.createVideoNote).toHaveBeenCalledWith("series-a", "video-1", {
      title: "重点",
      content: "记录一下这里讲了 API Key 的前置准备。",
      source: "agent",
    });
    await waitFor(() => expect(result.current.state.selectedToolId).toBe("notes"));
    expect(result.current.notes?.notes[0]).toEqual(
      expect.objectContaining({
        id: "note-1",
        title: "重点",
        source: "agent",
      }),
    );
    expect(result.current.chatMessages).toEqual(expect.arrayContaining([
      expect.objectContaining({
        kind: "tool-trace",
        toolTrace: expect.objectContaining({
          steps: [
            expect.objectContaining({
              toolName: "save_note",
              label: "保存笔记",
              target: "重点",
            }),
          ],
        }),
      }),
      expect.objectContaining({
        role: "assistant",
        content: "我已经帮你记到笔记里了。",
      }),
    ]));
  });

  it("loads knowledge cards when switching to the knowledge cards tool", async () => {
    const { result } = renderHook(() => useWorkspaceController());

    await waitFor(() => expect(result.current.state.loading).toBe(false));

    act(() => {
      result.current.onSelectSeries("series-a");
    });
    act(() => {
      result.current.onSelectVideo("series-a", "video-1");
    });

    await waitFor(() => expect(result.current.tools?.knowledgeCards?.generated).toBe(true));

    act(() => {
      result.current.onSelectTool("knowledge-cards");
    });

    await waitFor(() => {
      expect(workspaceApi.loadVideoKnowledgeCards).toHaveBeenCalledWith("series-a", "video-1");
    });
  });

  it("marks knowledge cards as generated after a successful generation request", async () => {
    workspaceApi.loadVideoTools.mockResolvedValueOnce({
      seriesId: "series-a",
      videoId: "video-1",
      overview: { id: "overview", title: "AI概况", available: true, generated: true, status: "ready" },
      knowledgeCards: { id: "knowledge-cards", title: "知识卡片", available: true, generated: false, status: "available" },
      mindmap: { id: "mindmap", title: "思维导图", available: true, generated: false, status: "available" },
      notes: { id: "notes", title: "笔记", available: true, generated: true, status: "ready" },
      preview: {
        id: "preview",
        title: "视频预览",
        available: true,
        generated: true,
        status: "ready",
        previewUrl: "/api/videos/series-a/video-1/preview",
      },
      aiTodo: "AI 已支持工具联动。",
    });
    workspaceApi.generateVideoKnowledgeCards.mockResolvedValueOnce({
      seriesId: "series-a",
      videoId: "video-1",
      title: "Video 1",
      cards: [
        {
          id: "card-1",
          kind: "concept",
          title: "懒加载",
          summary: "按需加载资源。",
          details: "减少初始加载成本。",
          tags: ["performance"],
          sourceRefs: [],
        },
      ],
    });
    workspaceApi.loadVideoKnowledgeCards.mockResolvedValueOnce({
      seriesId: "series-a",
      videoId: "video-1",
      title: "Video 1",
      cards: [
        {
          id: "card-1",
          kind: "concept",
          title: "懒加载",
          summary: "按需加载资源。",
          details: "减少初始加载成本。",
          tags: ["performance"],
          sourceRefs: [],
        },
      ],
    });

    const { result } = renderHook(() => useWorkspaceController());

    await waitFor(() => expect(result.current.state.loading).toBe(false));

    act(() => {
      result.current.onSelectSeries("series-a");
    });
    act(() => {
      result.current.onSelectVideo("series-a", "video-1");
    });

    await waitFor(() => expect(result.current.tools?.knowledgeCards?.generated).toBe(false));
    act(() => {
      result.current.onSelectTool("knowledge-cards");
    });

    await act(async () => {
      await result.current.onGenerateKnowledgeCards();
    });

    expect(result.current.tools?.knowledgeCards?.generated).toBe(true);
    expect(result.current.knowledgeCards?.cards).toHaveLength(1);
    expect(result.current.knowledgeCardsFeedback).toEqual({
      tone: "success",
      message: "已生成 1 张知识卡片",
    });
  });

  it("switches to knowledge cards when agent returns an open-tool action", async () => {
    workspaceApi.streamAgentChat.mockImplementationOnce(async (_sessionId, _message, _context, listener) => {
      listener({ type: "thinking_started", payload: { message: "正在分析当前问题" } });
      listener({ type: "tool_started", payload: { tool_call_id: "tool-1", tool_name: "open_knowledge_cards", index: 1 } });
      listener({
        type: "tool_completed",
        payload: {
          tool_call_id: "tool-1",
          tool_name: "open_knowledge_cards",
          status: "ok",
          duration_ms: 6,
          payload: {
            selected_tool: "knowledge-cards",
          },
        },
      });
      listener({ type: "tool_chain_completed", payload: { count: 1, duration_ms: 6 } });
      listener({ type: "answer_started", payload: { message: "正在组织回答" } });
      listener({ type: "answer_delta", payload: { delta: "我已经帮你打开知识卡片。" } });
      listener({ type: "answer_completed", payload: { message: "我已经帮你打开知识卡片。", duration_ms: 9 } });
    });

    const { result } = renderHook(() => useWorkspaceController());

    await waitFor(() => expect(result.current.state.loading).toBe(false));

    act(() => {
      result.current.onSelectSeries("series-a");
    });
    act(() => {
      result.current.onSelectVideo("series-a", "video-1");
    });

    await act(async () => {
      await result.current.onSubmitChat("打开知识卡片");
    });

    await waitFor(() => expect(result.current.state.selectedToolId).toBe("knowledge-cards"));
    expect(result.current.chatMessages.at(-1)).toEqual(
      expect.objectContaining({
        role: "assistant",
        content: "我已经帮你打开知识卡片。",
      }),
    );
  });

  it("switches to series overview when agent returns a series-level open-tool action", async () => {
    workspaceApi.streamAgentChat.mockImplementationOnce(async (_sessionId, _message, _context, listener) => {
      listener({ type: "thinking_started", payload: { message: "正在分析当前问题" } });
      listener({ type: "tool_started", payload: { tool_call_id: "tool-1", tool_name: "open_series_overview", index: 1 } });
      listener({
        type: "tool_completed",
        payload: {
          tool_call_id: "tool-1",
          tool_name: "open_series_overview",
          status: "ok",
          duration_ms: 4,
          payload: {
            selected_tool: "series-overview",
          },
        },
      });
      listener({ type: "tool_chain_completed", payload: { count: 1, duration_ms: 4 } });
      listener({ type: "answer_started", payload: { message: "正在组织回答" } });
      listener({ type: "answer_delta", payload: { delta: "我已经帮你打开系列概览。" } });
      listener({ type: "answer_completed", payload: { message: "我已经帮你打开系列概览。", duration_ms: 8 } });
    });

    const { result } = renderHook(() => useWorkspaceController());

    await waitFor(() => expect(result.current.state.loading).toBe(false));

    act(() => {
      result.current.onSelectSeries("series-a");
    });

    await act(async () => {
      await result.current.onSubmitChat("打开系列概览");
    });

    await waitFor(() => expect(result.current.state.selectedToolId).toBe("series-overview"));
    expect(result.current.chatMessages).toEqual(expect.arrayContaining([
      expect.objectContaining({
        kind: "tool-trace",
        toolTrace: expect.objectContaining({
          steps: [
            expect.objectContaining({
              toolName: "open_series_overview",
              label: "打开系列概览",
            }),
          ],
        }),
      }),
    ]));
  });

  it("records visible tool-chain messages before the final assistant reply", async () => {
    workspaceApi.streamAgentChat.mockImplementationOnce(async (_sessionId, _message, _context, listener) => {
      listener({ type: "thinking_started", payload: { message: "正在分析当前问题" } });
      listener({ type: "thinking_delta", payload: { delta: "先读取系列视频，" } });
      listener({ type: "thinking_delta", payload: { delta: "再读取视频概况。" } });
      listener({ type: "thinking_completed", payload: { summary: "先读取系列视频，再读取视频概况。", duration_ms: 14 } });
      listener({ type: "tool_started", payload: { tool_call_id: "tool-1", tool_name: "list_series_videos", index: 1 } });
      listener({
        type: "tool_completed",
        payload: {
          tool_call_id: "tool-1",
          tool_name: "list_series_videos",
          status: "ok",
          duration_ms: 5,
          payload: {
            series_id: "series-a",
            series_title: "Series A",
            videos: [
              { video_id: "video-1", title: "Video 1", processed: true, status: "ready" },
            ],
          },
        },
      });
      listener({ type: "tool_started", payload: { tool_call_id: "tool-2", tool_name: "get_video_summary", index: 2 } });
      listener({
        type: "tool_completed",
        payload: {
          tool_call_id: "tool-2",
          tool_name: "get_video_summary",
          status: "ok",
          duration_ms: 11,
          payload: {
            series_id: "series-a",
            video_id: "video-1",
            title: "Video 1",
            generated: true,
            one_sentence_summary: "Video 1 的一句话总结",
            core_problem: "",
            key_takeaways: [],
            chapters: [],
          },
        },
      });
      listener({ type: "tool_chain_completed", payload: { count: 2, duration_ms: 16 } });
      listener({ type: "answer_started", payload: { message: "正在组织回答" } });
      listener({ type: "answer_delta", payload: { delta: "我已经整理了当前系列里" } });
      listener({ type: "answer_delta", payload: { delta: "已生成概况的几个视频重点。" } });
      listener({
        type: "answer_completed",
        payload: {
          message: "我已经整理了当前系列里已生成概况的几个视频重点。",
          duration_ms: 22,
        },
      });
    });

    const { result } = renderHook(() => useWorkspaceController());

    await waitFor(() => expect(result.current.state.loading).toBe(false));

    act(() => {
      result.current.onSelectSeries("series-a");
    });

    await act(async () => {
      await result.current.onSubmitChat("总结当前系列");
    });

    expect(result.current.chatMessages).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          kind: "thought-trace",
          thoughtTrace: expect.objectContaining({
            status: "completed",
            summary: "先读取系列视频，再读取视频概况。",
          }),
        }),
        expect.objectContaining({
          kind: "tool-trace",
          content: "已调用 2 个工具",
          toolTrace: expect.objectContaining({
            status: "completed",
            steps: [
              expect.objectContaining({
                toolName: "list_series_videos",
                label: "读取系列视频列表",
                target: "Series A",
              }),
              expect.objectContaining({
                toolName: "get_video_summary",
                label: "读取视频概况",
                target: "Video 1",
              }),
            ],
          }),
        }),
        expect.objectContaining({ content: "我已经整理了当前系列里已生成概况的几个视频重点。" }),
      ]),
    );
  });
});
