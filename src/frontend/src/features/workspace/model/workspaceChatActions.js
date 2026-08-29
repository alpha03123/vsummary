import {
  clearAgentSession,
  loadAgentContextUsage,
  streamAgentChat,
} from "./workspaceApi";
import { buildAgentChatContextPayload, normalizeAgentToolId } from "./workspaceChatRuntime";
import { createNextChatSessionMeta, getChatSessionListForScope } from "./workspaceState";

export function createWorkspaceChatActions({
  state,
  dispatch,
  contentActions,
  chatAbortControllerRef,
}) {
  async function onSubmitChat(message) {
    const trimmedMessage = message.trim();
    if (!trimmedMessage || state.chatPending) {
      return;
    }

    if (state.selectedContextType === "series") {
      const series = state.library?.series?.find((item) => item.id === state.selectedSeriesId);
      if (series && (!Array.isArray(series.videos) || series.videos.length === 0)) {
        dispatch({ type: "load_failed", message: "此系列没有视频" });
        return;
      }
    }

    const sessionId = state.chatScopeKey;
    if (!sessionId) {
      throw new Error("当前未处于 series 或 video 上下文，无法发起 AI 对话。");
    }
    const context = buildAgentChatContextPayload(
      state.library,
      state.selectedContextType,
      state.selectedSeriesId,
      state.selectedVideoId,
      state.selectedToolId,
    );

    const requestId = Date.now();
    const abortController = new AbortController();
    chatAbortControllerRef.current = {
      controller: abortController,
      requestId,
      sessionId,
    };

    dispatch({
      type: "chat_request_started",
      chatScopeKey: sessionId,
      userMessageId: `user-${requestId}`,
      message: trimmedMessage,
    });

    try {
      await streamAgentChat(sessionId, trimmedMessage, context, async (event) => {
        dispatch({
          type: "chat_stream_event_received",
          chatScopeKey: sessionId,
          requestId,
          event,
        });

        await applyAgentStreamSideEffects(event);
      }, { signal: abortController.signal });
      if (chatAbortControllerRef.current?.requestId !== requestId) {
        return;
      }
      const usage = await loadAgentContextUsage(sessionId, context);
      dispatch({
        type: "context_usage_loaded",
        chatScopeKey: sessionId,
        currentScopeKey: state.chatScopeKey,
        usage,
      });
    } catch (error) {
      if (isChatRequestAborted(error)) {
        return;
      }
      const message = error instanceof Error ? error.message : "AI 对话失败";
      if (!error?.streamErrorDispatched) {
        dispatch({
          type: "chat_stream_event_received",
          chatScopeKey: sessionId,
          requestId,
          event: {
            type: "error",
            payload: { message },
          },
        });
      }
      dispatch({ type: "chat_pending_cleared" });
      dispatch({
        type: "load_failed",
        message,
      });
    } finally {
      if (chatAbortControllerRef.current?.requestId === requestId) {
        chatAbortControllerRef.current = null;
      }
    }
  }

  function onCancelChat() {
    const activeRequest = chatAbortControllerRef.current;
    if (!activeRequest) {
      return;
    }
    chatAbortControllerRef.current = null;
    activeRequest.controller.abort();
    dispatch({
      type: "chat_stream_event_received",
      chatScopeKey: activeRequest.sessionId,
      requestId: activeRequest.requestId,
      event: {
        type: "cancelled",
        payload: { message: "本次对话已中断" },
      },
    });
  }

  function onStartNewChat() {
    const chatBaseScopeKey = state.chatBaseScopeKey;
    if (!chatBaseScopeKey) {
      throw new Error("当前未处于 series 或 video 上下文，无法新建对话。");
    }
    const sessionId = `${chatBaseScopeKey}::${Date.now()}`;
    const sessionMeta = createNextChatSessionMeta(state.chatSessionListsByScope, chatBaseScopeKey, sessionId);
    dispatch({
      type: "chat_session_started",
      chatBaseScopeKey,
      sessionId,
      sessionMeta,
    });
  }

  function onSelectChatSession(sessionId) {
    if (!state.chatBaseScopeKey || !sessionId) {
      return;
    }
    dispatch({
      type: "chat_session_selected",
      chatBaseScopeKey: state.chatBaseScopeKey,
      sessionId,
    });
  }

  async function onClearChat() {
    const sessionId = state.chatScopeKey;
    if (!sessionId) {
      throw new Error("当前未处于 series 或 video 上下文，无法清空对话。");
    }
    const context = buildAgentChatContextPayload(
      state.library,
      state.selectedContextType,
      state.selectedSeriesId,
      state.selectedVideoId,
      state.selectedToolId,
    );
    try {
      await clearAgentSession(sessionId, context);
      dispatch({
        type: "chat_session_removed",
        chatBaseScopeKey: state.chatBaseScopeKey,
        sessionId,
      });
    } catch (error) {
      dispatch({
        type: "load_failed",
        message: error instanceof Error ? error.message : "清空对话失败",
      });
    }
  }

  function onOpenCitationReference(reference) {
    if (!reference) {
      return;
    }

    if (state.selectedToolId === "preview") {
      if (typeof reference.seconds !== "number") {
        return;
      }
      if (reference.videoId && reference.videoId !== state.selectedVideoId) {
        return;
      }
      dispatchPlayerSeek(reference);
      return;
    }

    if (state.selectedToolId === "overview") {
      if (reference.videoId && reference.videoId !== state.selectedVideoId) {
        return;
      }
      if (typeof reference.seconds !== "number" && !reference.chapterId) {
        return;
      }
      dispatch({
        type: "citation_focus_requested",
        focus: {
          ...reference,
          requestId: `${Date.now()}-${reference.seconds ?? reference.chapterId}`,
        },
      });
      return;
    }

    if (state.selectedToolId === "series-overview" && reference.videoId) {
      dispatch({
        type: "citation_focus_requested",
        focus: {
          ...reference,
          requestId: `${Date.now()}-${reference.videoId}`,
        },
      });
    }
  }

  function onOpenSeekReference(reference) {
    if (!reference || typeof reference.seconds !== "number") {
      return;
    }
    dispatchPlayerSeek(reference);
  }

  function dispatchPlayerSeek(reference) {
    dispatch({
      type: "player_seek_requested",
      seconds: reference.seconds,
      endSeconds: typeof reference.endSeconds === "number" ? reference.endSeconds : null,
      query: typeof reference.query === "string" ? reference.query : "",
      matchedText: typeof reference.matchedText === "string" ? reference.matchedText : "",
      chapterTitle: typeof reference.chapterTitle === "string" ? reference.chapterTitle : "",
      requestId: `${Date.now()}-${reference.seconds}`,
    });
  }

  async function applyAgentStreamSideEffects(event) {
    if (event?.type !== "tool_completed") {
      return;
    }

    const payload = event.payload?.payload ?? {};

    if (payload.selected_tool) {
      const nextToolId = normalizeAgentToolId(payload.selected_tool);
      if (nextToolId) {
        dispatch({ type: "tool_selected", toolId: nextToolId });
      }
    }

    if (typeof payload.seek_seconds === "number") {
      dispatch({
        type: "player_seek_requested",
        seconds: payload.seek_seconds,
        endSeconds: typeof payload.match_end_seconds === "number" ? payload.match_end_seconds : null,
        query: typeof payload.query === "string" ? payload.query : "",
        matchedText: typeof payload.matched_text === "string" ? payload.matched_text : "",
        chapterTitle: typeof payload.chapter_title === "string" ? payload.chapter_title : "",
        requestId: `${Date.now()}-${payload.seek_seconds}`,
      });
    }

    if (payload.action === "generate_overview") {
      void contentActions.onGenerateVideo();
    }

    if (payload.action === "generate_mindmap") {
      void contentActions.onGenerateMindmap();
    }

    if (
      payload.action === "save_note" &&
      typeof payload.note_title === "string" &&
      typeof payload.note_content === "string"
    ) {
      await contentActions.onCreateNote({
        title: payload.note_title,
        content: payload.note_content,
        source: typeof payload.note_source === "string" ? payload.note_source : "agent",
      });
    }
  }

  return {
    onSubmitChat,
    onCancelChat,
    onStartNewChat,
    onSelectChatSession,
    onClearChat,
    onOpenSeekReference,
    onOpenCitationReference,
  };
}

function isChatRequestAborted(error) {
  return error instanceof DOMException && error.name === "AbortError";
}
