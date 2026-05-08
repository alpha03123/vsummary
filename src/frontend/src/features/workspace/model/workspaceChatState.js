import {
  buildAssistantChatMeta,
  formatDurationLabel,
  normalizeAgentToolTraceStep,
} from "./workspaceChatRuntime";
import {
  createWelcomeChatMessages,
  getChatMessagesForScope,
  setChatMessagesForScope,
} from "./workspaceState";

function applyChatThreadUpdate(state, chatScopeKey, nextMessages, chatPending) {
  return {
    ...state,
    chatPending,
    chatMessages: state.chatScopeKey === chatScopeKey ? nextMessages : state.chatMessages,
    chatThreads: setChatMessagesForScope(state.chatThreads, chatScopeKey, nextMessages),
    error: "",
  };
}

function transformChatThreadMessages(state, chatScopeKey, transform, chatPending = state.chatPending) {
  const currentMessages = getChatMessagesForScope(state.chatThreads, chatScopeKey);
  return applyChatThreadUpdate(state, chatScopeKey, transform(currentMessages), chatPending);
}

export function appendChatThreadMessage(state, chatScopeKey, message, chatPending) {
  const currentMessages = getChatMessagesForScope(state.chatThreads, chatScopeKey);
  return applyChatThreadUpdate(state, chatScopeKey, [...currentMessages, message], chatPending);
}

export function applyChatStreamEvent(state, chatScopeKey, requestId, event) {
  switch (event?.type) {
    case "thinking_started":
      return transformChatThreadMessages(state, chatScopeKey, (messages) =>
        upsertChatMessage(
          messages,
          buildThinkingMessage(
            requestId,
            {
              ...event.payload,
              previous_summary: messages.find((message) => message.id === `thought-${requestId}`)?.thoughtTrace?.summary ?? "",
              previous_stages: messages.find((message) => message.id === `thought-${requestId}`)?.thoughtTrace?.stages ?? [],
            },
            { status: "running" },
          ),
        ), true);
    case "thinking_delta":
      return transformChatThreadMessages(state, chatScopeKey, (messages) =>
        upsertChatMessage(messages, appendThinkingDelta(messages, requestId, event.payload?.delta)), true);
    case "stage_started":
    case "stage_completed":
      return transformChatThreadMessages(state, chatScopeKey, (messages) =>
        upsertChatMessage(messages, appendThinkingStage(messages, requestId, event)), true);
    case "thinking_completed":
      return transformChatThreadMessages(state, chatScopeKey, (messages) => {
        const currentThoughtTrace = messages.find((message) => message.id === `thought-${requestId}`)?.thoughtTrace ?? {};
        return upsertChatMessage(
          messages,
          buildThinkingMessage(
            requestId,
            {
              ...event.payload,
              previous_summary: currentThoughtTrace.summary ?? "",
              previous_stages: currentThoughtTrace.stages ?? [],
            },
            { status: "completed" },
          ),
        );
      }, true);
    case "tool_started":
      return transformChatThreadMessages(state, chatScopeKey, (messages) =>
        upsertChatMessage(messages, buildToolTraceMessage(requestId, messages, event, false)), true);
    case "tool_completed":
      return transformChatThreadMessages(state, chatScopeKey, (messages) => {
        const nextMessages = upsertChatMessage(messages, buildToolTraceMessage(requestId, messages, event, false));
        const seekReferenceMessage = buildSeekReferenceMessage(requestId, event);
        if (seekReferenceMessage == null) {
          return nextMessages;
        }
        return upsertChatMessage(nextMessages, seekReferenceMessage);
      }, true);
    case "tool_chain_completed":
      return transformChatThreadMessages(state, chatScopeKey, (messages) =>
        upsertChatMessage(messages, buildToolTraceMessage(requestId, messages, event, true)), true);
    case "answer_started":
      return transformChatThreadMessages(state, chatScopeKey, (messages) =>
        upsertChatMessage(messages, buildStreamingAnswerMessage(requestId, "", "running", null, null)), true);
    case "answer_delta":
      return transformChatThreadMessages(state, chatScopeKey, (messages) =>
        upsertChatMessage(messages, appendStreamingAnswerDelta(messages, requestId, event.payload?.delta)), true);
    case "answer_completed":
      return transformChatThreadMessages(state, chatScopeKey, (messages) =>
        upsertChatMessage(
          messages,
          buildStreamingAnswerMessage(
            requestId,
            typeof event.payload?.message === "string" ? event.payload.message : getMessageContent(messages, `assistant-${requestId}`),
            "completed",
            event.payload?.duration_ms,
            event.payload?.usage ?? null,
            Array.isArray(event.payload?.citations) ? event.payload.citations : null,
          ),
        ), false);
    case "error":
      return transformChatThreadMessages(
        state,
        chatScopeKey,
        (messages) => markChatStreamFailed(messages, requestId, event.payload?.message),
        false,
      );
    default:
      return state;
  }
}

function upsertChatMessage(messages, nextMessage) {
  const nextMessages = [...messages];
  const index = nextMessages.findIndex((message) => message.id === nextMessage.id);
  if (index === -1) {
    nextMessages.push(nextMessage);
    return nextMessages;
  }
  nextMessages[index] = {
    ...nextMessages[index],
    ...nextMessage,
  };
  return nextMessages;
}

function getMessageContent(messages, messageId) {
  return messages.find((message) => message.id === messageId)?.content ?? "";
}

function buildThinkingMessage(requestId, payload, { status }) {
  const previousSummary = typeof payload?.previous_summary === "string" ? payload.previous_summary : "";
  const previousStages = Array.isArray(payload?.previous_stages) ? payload.previous_stages : [];
  const durationMs = typeof payload?.duration_ms === "number" ? payload.duration_ms : null;
  const summary = typeof payload?.summary === "string" && payload.summary
    ? payload.summary
    : previousSummary;
  const hasStages = previousStages.length > 0;
  return {
    id: `thought-${requestId}`,
    role: "assistant",
    kind: "thought-trace",
    content: hasStages
      ? status === "running" ? "执行中" : status === "failed" ? "执行失败" : "执行完成"
      : status === "running" ? "思考中" : status === "failed" ? "思路失败" : "思路已完成",
    thoughtTrace: {
      status,
      summary,
      durationMs,
      stages: previousStages,
    },
    meta: status === "running"
      ? hasStages ? "Notebook Assistant • 执行中" : "Notebook Assistant • 思考中"
      : status === "failed"
        ? `Notebook Assistant • ${hasStages ? "执行失败" : "思路失败"}`
      : buildStatusMeta(hasStages ? "执行" : "思路", durationMs),
  };
}

function buildToolTraceMessage(requestId, messages, event, completed) {
  const messageId = `tool-trace-${requestId}`;
  const previous = messages.find((message) => message.id === messageId);
  const previousSteps = Array.isArray(previous?.toolTrace?.steps) ? previous.toolTrace.steps : [];

  let nextSteps = previousSteps;
  if (event.type === "tool_started" || event.type === "tool_completed") {
    const step = buildToolTraceStep(event);
    nextSteps = upsertToolStep(previousSteps, step);
  }
  if (completed) {
    nextSteps = nextSteps.map((step) => ({
      ...step,
      status: "completed",
    }));
  }

  const durationMs = sumVisibleToolDurations(nextSteps);
  const status = completed
    ? "completed"
    : nextSteps.some((step) => step.status === "running")
      ? "running"
      : "idle";
  const stepCount = nextSteps.length;

  return {
    id: messageId,
    role: "assistant",
    kind: "tool-trace",
    content: status === "running"
      ? `正在调用 ${Math.max(stepCount, 1)} 个工具`
      : `已调用 ${stepCount} 个工具`,
    toolTrace: {
      status,
      steps: nextSteps,
      durationMs: typeof durationMs === "number" ? durationMs : null,
      stageDurationMs: event.type === "tool_chain_completed" && typeof event.payload?.duration_ms === "number"
        ? event.payload.duration_ms
        : previous?.toolTrace?.stageDurationMs ?? null,
    },
    meta: completed
      ? buildStatusMeta("工具链", durationMs)
      : status === "running"
        ? "Notebook Assistant • 正在调用工具"
        : status === "failed"
          ? "Notebook Assistant • 工具链失败"
        : "Notebook Assistant • 等待下一步",
  };
}

function upsertToolStep(steps, nextStep) {
  const nextSteps = [...steps];
  const index = nextSteps.findIndex((step) => step.id === nextStep.id);
  if (index === -1) {
    nextSteps.push(nextStep);
    return nextSteps;
  }
  nextSteps[index] = {
    ...nextSteps[index],
    ...nextStep,
  };
  return nextSteps;
}

function buildToolTraceStep(event) {
  const payload = event.payload ?? {};
  const normalized = normalizeAgentToolTraceStep({
    tool_name: payload.tool_name ?? event.payload?.tool_name,
    payload: payload.payload ?? payload,
  });
  return {
    id: typeof payload.tool_call_id === "string" ? payload.tool_call_id : `${payload.tool_name ?? "tool"}-${payload.index ?? 0}`,
    toolName: normalized.toolName,
    label: normalized.label,
    target: normalized.target,
    status: event.type === "tool_started" ? "running" : "completed",
    durationMs: typeof payload.duration_ms === "number" ? payload.duration_ms : null,
  };
}

function sumVisibleToolDurations(steps) {
  const durations = steps
    .map((step) => step.durationMs)
    .filter((durationMs) => typeof durationMs === "number" && durationMs >= 0);
  if (!durations.length) {
    return null;
  }
  return durations.reduce((total, durationMs) => total + durationMs, 0);
}

function appendStreamingAnswerDelta(messages, requestId, delta) {
  const currentContent = getMessageContent(messages, `assistant-${requestId}`);
  const currentUsage = messages.find((message) => message.id === `assistant-${requestId}`)?.usage ?? null;
  const currentCitations = messages.find((message) => message.id === `assistant-${requestId}`)?.citations ?? null;
  return buildStreamingAnswerMessage(
    requestId,
    `${currentContent}${typeof delta === "string" ? delta : ""}`,
    "running",
    null,
    currentUsage,
    currentCitations,
  );
}

function appendThinkingDelta(messages, requestId, delta) {
  const messageId = `thought-${requestId}`;
  const currentMessage = messages.find((message) => message.id === messageId);
  const currentSummary = currentMessage?.thoughtTrace?.summary ?? "";
  const nextSummary = `${currentSummary}${typeof delta === "string" ? delta : ""}`;
  return buildThinkingMessage(
    requestId,
    {
      summary: nextSummary,
      duration_ms: currentMessage?.thoughtTrace?.durationMs ?? null,
      previous_stages: currentMessage?.thoughtTrace?.stages ?? [],
    },
    { status: "running" },
  );
}

function appendThinkingStage(messages, requestId, event) {
  const messageId = `thought-${requestId}`;
  const currentMessage = messages.find((message) => message.id === messageId);
  const currentStages = Array.isArray(currentMessage?.thoughtTrace?.stages) ? currentMessage.thoughtTrace.stages : [];
  const nextStage = buildThinkingStage(event);
  return buildThinkingMessage(
    requestId,
    {
      summary: currentMessage?.thoughtTrace?.summary ?? "",
      duration_ms: currentMessage?.thoughtTrace?.durationMs ?? null,
      previous_stages: upsertThinkingStage(currentStages, nextStage),
    },
    { status: "running" },
  );
}

function buildThinkingStage(event) {
  const payload = event?.payload ?? {};
  const nodeId = typeof payload.node_id === "string" ? payload.node_id : "unknown";
  return {
    id: typeof payload.stage_id === "string" ? payload.stage_id : `${nodeId}-stage`,
    nodeId,
    label: typeof payload.label === "string" && payload.label.trim() ? payload.label.trim() : nodeId,
    status: event?.type === "stage_started" ? "running" : "completed",
    durationMs: typeof payload.duration_ms === "number" ? payload.duration_ms : null,
  };
}

function upsertThinkingStage(stages, nextStage) {
  const nextStages = [...stages];
  const index = nextStages.findIndex((stage) => stage.id === nextStage.id);
  if (index === -1) {
    nextStages.push(nextStage);
    return nextStages;
  }
  nextStages[index] = {
    ...nextStages[index],
    ...nextStage,
  };
  return nextStages;
}

function buildStreamingAnswerMessage(requestId, content, status, durationMs, usage, citations = null) {
  return {
    id: `assistant-${requestId}`,
    role: "assistant",
    content,
    streamingStatus: status,
    usage,
    citations,
    meta: status === "running"
      ? "Notebook Assistant • 输出中"
      : status === "failed"
        ? "Notebook Assistant • 输出失败"
      : buildAssistantChatMeta(durationMs, usage),
  };
}

function markChatStreamFailed(messages, requestId, errorMessage) {
  const nextMessages = [...messages];
  const nextErrorMessage = typeof errorMessage === "string" && errorMessage.trim()
    ? errorMessage.trim()
    : "AI 对话失败";
  const thoughtIndex = nextMessages.findIndex((message) => message.id === `thought-${requestId}`);
  if (thoughtIndex !== -1) {
    const currentMessage = nextMessages[thoughtIndex];
    nextMessages[thoughtIndex] = buildThinkingMessage(
      requestId,
      {
        summary: nextErrorMessage,
        duration_ms: currentMessage?.thoughtTrace?.durationMs ?? null,
        previous_stages: (currentMessage?.thoughtTrace?.stages ?? []).map((stage) => ({
          ...stage,
          status: stage.status === "running" ? "failed" : stage.status,
        })),
      },
      { status: "failed" },
    );
  }

  const toolTraceIndex = nextMessages.findIndex((message) => message.id === `tool-trace-${requestId}`);
  if (toolTraceIndex !== -1) {
    const currentMessage = nextMessages[toolTraceIndex];
    const currentSteps = Array.isArray(currentMessage?.toolTrace?.steps) ? currentMessage.toolTrace.steps : [];
    nextMessages[toolTraceIndex] = {
      ...currentMessage,
      content: "工具调用失败",
      toolTrace: {
        ...currentMessage.toolTrace,
        status: "failed",
        steps: currentSteps.map((step) => ({
          ...step,
          status: step.status === "running" ? "failed" : step.status,
        })),
      },
      meta: "Notebook Assistant • 工具链失败",
    };
  }

  const answerIndex = nextMessages.findIndex((message) => message.id === `assistant-${requestId}`);
  if (answerIndex !== -1) {
    const currentMessage = nextMessages[answerIndex];
    nextMessages[answerIndex] = buildStreamingAnswerMessage(
      requestId,
      currentMessage?.content || nextErrorMessage,
      "failed",
      null,
      currentMessage?.usage ?? null,
      currentMessage?.citations ?? null,
    );
  }

  if (thoughtIndex === -1 && toolTraceIndex === -1 && answerIndex === -1) {
    nextMessages.push(buildStreamingAnswerMessage(requestId, nextErrorMessage, "failed", null, null));
  }

  return nextMessages;
}

function buildStatusMeta(label, durationMs) {
  const durationLabel = formatDurationLabel(durationMs);
  if (!durationLabel) {
    return `Notebook Assistant • ${label}完成`;
  }
  return `Notebook Assistant • ${label}用时 ${durationLabel}`;
}

function buildSeekReferenceMessage(requestId, event) {
  const payload = event?.payload?.payload ?? {};
  if (typeof payload.seek_seconds !== "number") {
    return null;
  }
  const toolCallId = typeof event?.payload?.tool_call_id === "string" ? event.payload.tool_call_id : "seek";
  return {
    id: `seek-reference-${requestId}-${toolCallId}`,
    role: "assistant",
    kind: "seek-reference",
    content: "已找到相关视频片段",
    seekReference: {
      seconds: payload.seek_seconds,
      endSeconds: typeof payload.match_end_seconds === "number" ? payload.match_end_seconds : null,
      matchedText: typeof payload.matched_text === "string" ? payload.matched_text : "",
      chapterTitle: typeof payload.chapter_title === "string" ? payload.chapter_title : "",
      query: typeof payload.query === "string" ? payload.query : "",
    },
    meta: "Notebook Assistant • 证据定位",
  };
}
