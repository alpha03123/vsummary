import { act, renderHook, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { useWorkspaceController } from "./useWorkspaceController";

const workspaceApi = vi.hoisted(() => ({
  cancelFasterWhisperModelDownload: vi.fn(),
  createVideoNote: vi.fn(),
  deleteVideoNote: vi.fn(),
  downloadFasterWhisperModel: vi.fn(),
  generateVideoKnowledgeCards: vi.fn(),
  generateVideoMindmap: vi.fn(),
  generateVideoSummary: vi.fn(),
  getVideoPreviewUrl: vi.fn(),
  loadFasterWhisperModels: vi.fn(),
  loadProviderSettings: vi.fn(),
  loadVideoKnowledgeCards: vi.fn(),
  sendAgentChat: vi.fn(),
  loadVideoMindmap: vi.fn(),
  loadVideoNotes: vi.fn(),
  loadVideoSummary: vi.fn(),
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
    workspaceApi.sendAgentChat.mockResolvedValue({
      assistant_message: "相关内容在 02:08 左右，我已经帮你打开视频。",
      intent_type: "seek_video",
      scope_type: "video",
      reason: "定位到转写片段",
      out_of_scope_reason: "",
      tool_results: [
        {
          tool_name: "transcript_lookup",
          status: "ok",
          payload: {
            selected_tool: "video",
            query: "百度地图 API Key",
            seek_seconds: 128,
            match_end_seconds: 146,
            matched_text: "后续项目会用到百度地图 API，需要提前申请 API Key。",
            chapter_title: "准备工作",
          },
        },
      ],
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

    await act(async () => {
      await result.current.onSubmitChat("百度地图 API Key 在视频什么位置？");
    });

    expect(workspaceApi.sendAgentChat).toHaveBeenCalledWith(
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
    );
    await waitFor(() => expect(result.current.state.selectedToolId).toBe("preview"));
    expect(result.current.previewSeekRequest).toEqual(
      expect.objectContaining({
        seconds: 128,
        endSeconds: 146,
        query: "百度地图 API Key",
        matchedText: "后续项目会用到百度地图 API，需要提前申请 API Key。",
        chapterTitle: "准备工作",
      }),
    );
    expect(result.current.chatMessages.at(-1)).toEqual(
      expect.objectContaining({
        role: "assistant",
        content: "相关内容在 02:08 左右，我已经帮你打开视频。",
      }),
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

  it("supports library-scope chat before selecting a series", async () => {
    const { result } = renderHook(() => useWorkspaceController());

    await waitFor(() => expect(result.current.state.loading).toBe(false));

    await act(async () => {
      await result.current.onSubmitChat("这个知识库里先看什么？");
    });

    expect(workspaceApi.sendAgentChat).toHaveBeenCalledWith(
      "library|studio",
      "这个知识库里先看什么？",
      {
        scope_type: "library",
        series_id: null,
        series_title: null,
        video_id: null,
        video_title: null,
        selected_tool: "studio",
      },
    );
    expect(result.current.chatMessages.some((message) => message.content === "这个知识库里先看什么？")).toBe(true);
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
    workspaceApi.sendAgentChat.mockResolvedValueOnce({
      assistant_message: "我已经帮你记到笔记里了。",
      intent_type: "open_tool",
      scope_type: "video",
      reason: "整理重点",
      out_of_scope_reason: "",
      tool_results: [
        {
          tool_name: "save_note",
          status: "ok",
          payload: {
            action: "save_note",
            selected_tool: "notes",
            note_title: "重点",
            note_content: "记录一下这里讲了 API Key 的前置准备。",
            note_source: "agent",
          },
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
    workspaceApi.sendAgentChat.mockResolvedValueOnce({
      assistant_message: "我已经帮你打开知识卡片。",
      intent_type: "open_tool",
      scope_type: "video",
      reason: "切到知识卡片",
      out_of_scope_reason: "",
      tool_results: [
        {
          tool_name: "open_knowledge_cards",
          status: "ok",
          payload: {
            selected_tool: "knowledge-cards",
          },
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
});
