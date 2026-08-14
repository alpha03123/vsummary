import {
  toWorkspaceCards,
  toWorkspaceContextUsage,
  toWorkspaceKnowledgeCards,
  toWorkspaceLibrary,
  toWorkspaceMindmap,
  toWorkspaceNote,
  toWorkspaceNotes,
  toWorkspaceSummary,
  toWorkspaceTools,
} from "./workspaceViewModel";

export async function loadWorkspaceLibrary() {
  return toWorkspaceLibrary(await fetchJson("/api/videos"));
}

export async function checkBackendHealth() {
  const response = await fetch("/api/health");
  if (!response.ok) {
    throw new Error(`health check failed: ${response.status}`);
  }
  return response.json();
}

export async function loadWorkspaceSettings() {
  const payload = await fetchJson("/api/settings");
  return toWorkspaceSettings(payload);
}

function toWorkspaceSettings(payload) {
  return {
    theme: payload.theme,
    showTakeaways: payload.show_takeaways,
    layoutMode: payload.layout_mode,
    transcriptEnhancementEnabled: payload.transcript_enhancement_enabled,
    asrProvider: payload.asr_provider,
    asrModelQuality: payload.asr_model_quality,
    transcriptionMode: payload.transcription_mode,
    asrCloudModel: payload.asr_cloud_model,
    asrBaseUrl: payload.asr_base_url,
    hasAsrApiKey: payload.has_asr_api_key,
    asrApiKeyMasked: payload.asr_api_key_masked,
    asrApiKey: "",
    ragEmbeddingDevice: payload.rag_embedding_device,
    ragMaxHits: payload.rag_max_hits,
    ragRerankEnabled: payload.rag_rerank_enabled,
    webSearchEnabled: payload.web_search_enabled,
    windowTokens: payload.window_tokens,
    answerDetailLevel: payload.answer_detail_level,
    reasoningEffort: payload.reasoning_effort,
    talkCustomPrompt: payload.talk_custom_prompt,
    videoGenerationConcurrency: payload.video_generation_concurrency,
    chaoxingRequestDelaySeconds: payload.chaoxing_request_delay_seconds,
    chaoxingInitCourseDelaySeconds: payload.chaoxing_init_course_delay_seconds,
    runtimeCapabilities: payload.runtime_capabilities,
  };
}

export async function loadProviderSettings() {
  const payload = await fetchJson("/api/provider-settings");
  return {
    llmProvider: payload.llm_provider,
    openaiBaseUrl: payload.openai_base_url,
    openaiModel: payload.openai_model,
    hasOpenaiApiKey: payload.has_openai_api_key,
    openaiApiKeyMasked: payload.openai_api_key_masked,
    hfEndpoint: payload.hf_endpoint,
    openaiApiKey: "",
  };
}

export async function loadProviderUsage(range = "7d") {
  const payload = await fetchJson(`/api/provider-settings/usage?range=${encodeURIComponent(range)}`);
  return toProviderUsage(payload);
}

export async function loadOpenaiApiKey() {
  const payload = await fetchJson("/api/provider-settings/openai-api-key");
  return typeof payload.openai_api_key === "string" ? payload.openai_api_key : "";
}

export async function loadAsrApiKey() {
  const payload = await fetchJson("/api/settings/asr-api-key");
  return typeof payload.asr_api_key === "string" ? payload.asr_api_key : "";
}

export async function updateWorkspaceSettings(settings) {
  const payload = await fetchJson("/api/settings", {
    method: "PUT",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      theme: settings.theme,
      show_takeaways: settings.showTakeaways,
      layout_mode: settings.layoutMode,
      transcript_enhancement_enabled: settings.transcriptEnhancementEnabled,
      asr_provider: settings.asrProvider,
      asr_model_quality: settings.asrModelQuality,
      transcription_mode: settings.transcriptionMode,
      asr_cloud_model: settings.asrCloudModel,
      asr_base_url: settings.asrBaseUrl,
      asr_api_key: settings.asrApiKey && settings.asrApiKey.trim() ? settings.asrApiKey : null,
      rag_embedding_device: settings.ragEmbeddingDevice,
      rag_max_hits: settings.ragMaxHits,
      rag_rerank_enabled: settings.ragRerankEnabled,
      web_search_enabled: settings.webSearchEnabled,
      window_tokens: settings.windowTokens,
      answer_detail_level: settings.answerDetailLevel,
      reasoning_effort: settings.reasoningEffort,
      talk_custom_prompt: settings.talkCustomPrompt,
      video_generation_concurrency: settings.videoGenerationConcurrency,
      chaoxing_request_delay_seconds: settings.chaoxingRequestDelaySeconds,
      chaoxing_init_course_delay_seconds: settings.chaoxingInitCourseDelaySeconds,
    }),
  });
  return toWorkspaceSettings(payload);
}

export async function updateProviderSettings(settings) {
  const payload = await fetchJson("/api/provider-settings", {
    method: "PUT",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      llm_provider: settings.llmProvider,
      openai_base_url: settings.openaiBaseUrl,
      openai_model: settings.openaiModel,
      openai_api_key: settings.openaiApiKey.trim() ? settings.openaiApiKey : null,
      hf_endpoint: settings.hfEndpoint,
    }),
  });
  return {
    llmProvider: payload.llm_provider,
    openaiBaseUrl: payload.openai_base_url,
    openaiModel: payload.openai_model,
    hasOpenaiApiKey: payload.has_openai_api_key,
    openaiApiKeyMasked: payload.openai_api_key_masked,
    hfEndpoint: payload.hf_endpoint,
    openaiApiKey: "",
  };
}

export async function testProviderSettings(settings) {
  const controller = new AbortController();
  const timeoutId = window.setTimeout(() => controller.abort(), 5000);
  try {
    return await fetchJson("/api/provider-settings/test", {
      method: "POST",
      signal: controller.signal,
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        llm_provider: settings.llmProvider,
        openai_base_url: settings.openaiBaseUrl,
        openai_model: settings.openaiModel,
        openai_api_key: settings.openaiApiKey.trim() ? settings.openaiApiKey : null,
        hf_endpoint: settings.hfEndpoint,
      }),
    });
  } finally {
    window.clearTimeout(timeoutId);
  }
}

export async function testAsrSettings(settings) {
  const controller = new AbortController();
  const timeoutId = window.setTimeout(() => controller.abort(), 10000);
  try {
    return await fetchJson("/api/settings/asr/test", {
      method: "POST",
      signal: controller.signal,
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        asr_provider: settings.asrProvider,
        asr_cloud_model: settings.asrCloudModel,
        asr_base_url: settings.asrBaseUrl,
        asr_api_key: settings.asrApiKey.trim() ? settings.asrApiKey : null,
      }),
    });
  } finally {
    window.clearTimeout(timeoutId);
  }
}

export async function loadFasterWhisperModels(provider = "faster_whisper") {
  return fetchJson(`/api/asr/${encodeURIComponent(provider)}/models`);
}

export async function loadRagModels() {
  return fetchJson("/api/rag/models");
}

export async function downloadRagModel(modelKey) {
  return fetchJson(`/api/rag/models/${encodeURIComponent(modelKey)}/download`, {
    method: "POST",
  });
}

export async function cancelRagModelDownload(modelKey) {
  return fetchJson(`/api/rag/models/${encodeURIComponent(modelKey)}/download/cancel`, {
    method: "POST",
  });
}

export function subscribeRagModelDownloadProgress(modelKey, listener) {
  return subscribeProgress(
    `/api/rag/models/${encodeURIComponent(modelKey)}/download/progress`,
    listener,
    "RAG 模型下载进度连接已中断",
  );
}

export async function downloadFasterWhisperModel(provider, modelId) {
  return fetchJson(`/api/asr/${encodeURIComponent(provider)}/models/${encodeURIComponent(modelId)}/download`, {
    method: "POST",
  });
}

export async function cancelFasterWhisperModelDownload(provider, modelId) {
  return fetchJson(`/api/asr/${encodeURIComponent(provider)}/models/${encodeURIComponent(modelId)}/download/cancel`, {
    method: "POST",
  });
}

export function subscribeFasterWhisperModelDownloadProgress(provider, modelId, listener) {
  return subscribeProgress(
    `/api/asr/${encodeURIComponent(provider)}/models/${encodeURIComponent(modelId)}/download/progress`,
    listener,
    "模型下载进度连接已中断",
  );
}

function subscribeProgress(path, listener, connectionErrorMessage) {
  const eventSource = new EventSource(path);
  let terminal = false;

  eventSource.onmessage = (event) => {
    const snapshot = parseProgressMessage(event.data);
    listener(snapshot);
    if (snapshot.status === "completed" || snapshot.status === "failed" || snapshot.status === "cancelled") {
      terminal = true;
      eventSource.close();
    }
  };

  eventSource.onerror = () => {
    if (terminal) {
      return;
    }
    listener({
      status: "failed",
      stage: "failed",
      progress: null,
      detail: null,
      error: connectionErrorMessage,
    });
    eventSource.close();
  };

  return () => {
    terminal = true;
    eventSource.close();
  };
}

export async function loadVideoSummary(seriesId, videoId) {
  return toWorkspaceSummary(await fetchJson(`/api/videos/${encodeURIComponent(seriesId)}/${encodeURIComponent(videoId)}/summary`));
}

export async function updateVideoSummary(seriesId, videoId, summary) {
  return toWorkspaceSummary(
    await fetchJson(`/api/videos/${encodeURIComponent(seriesId)}/${encodeURIComponent(videoId)}/summary`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ markdown: summary }),
    }),
  );
}

export async function loadVideoSummaryMarkdown(seriesId, videoId) {
  const payload = await fetchJson(`/api/videos/${encodeURIComponent(seriesId)}/${encodeURIComponent(videoId)}/summary/markdown`);
  if (typeof payload.markdown !== "string") {
    throw new Error("summary markdown 不是有效文本。");
  }
  return payload.markdown;
}

export async function loadVideoTranscriptMarkdown(seriesId, videoId) {
  const payload = await fetchJson(`/api/videos/${encodeURIComponent(seriesId)}/${encodeURIComponent(videoId)}/transcript/markdown`);
  if (typeof payload.markdown !== "string") {
    throw new Error("transcript markdown 不是有效文本。");
  }
  return payload.markdown;
}

export async function updateVideoTranscript(seriesId, videoId, markdown) {
  return fetchJson(`/api/videos/${encodeURIComponent(seriesId)}/${encodeURIComponent(videoId)}/transcript`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ markdown }),
  });
}

export async function loadVideoTools(seriesId, videoId) {
  return toWorkspaceTools(await fetchJson(`/api/videos/${encodeURIComponent(seriesId)}/${encodeURIComponent(videoId)}/tools`));
}

export async function loadVideoMindmap(seriesId, videoId) {
  return toWorkspaceMindmap(await fetchJson(`/api/videos/${encodeURIComponent(seriesId)}/${encodeURIComponent(videoId)}/mindmap`));
}

export async function loadVideoCards(seriesId, videoId) {
  return toWorkspaceCards(await fetchJson(`/api/videos/${encodeURIComponent(seriesId)}/${encodeURIComponent(videoId)}/cards`));
}

export async function loadVideoKnowledgeCards(seriesId, videoId) {
  return toWorkspaceKnowledgeCards(
    await fetchJson(`/api/videos/${encodeURIComponent(seriesId)}/${encodeURIComponent(videoId)}/knowledge-cards`),
  );
}

export async function generateVideoKnowledgeCards(seriesId, videoId) {
  return toWorkspaceKnowledgeCards(
    await fetchJson(`/api/videos/${encodeURIComponent(seriesId)}/${encodeURIComponent(videoId)}/knowledge-cards/generate`, {
      method: "POST",
    }),
  );
}

export async function loadVideoNotes(seriesId, videoId) {
  return toWorkspaceNotes(await fetchJson(`/api/videos/${encodeURIComponent(seriesId)}/${encodeURIComponent(videoId)}/notes`));
}

export async function createVideoNote(seriesId, videoId, note) {
  return toWorkspaceNote(
    await fetchJson(`/api/videos/${encodeURIComponent(seriesId)}/${encodeURIComponent(videoId)}/notes`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        title: note.title,
        content: note.content,
        source: note.source,
      }),
    }),
  );
}

export async function updateVideoNote(seriesId, videoId, noteId, note) {
  return toWorkspaceNote(
    await fetchJson(`/api/videos/${encodeURIComponent(seriesId)}/${encodeURIComponent(videoId)}/notes/${encodeURIComponent(noteId)}`, {
      method: "PUT",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        title: note.title,
        content: note.content,
      }),
    }),
  );
}

export async function deleteVideoNote(seriesId, videoId, noteId) {
  return fetchJson(`/api/videos/${encodeURIComponent(seriesId)}/${encodeURIComponent(videoId)}/notes/${encodeURIComponent(noteId)}`, {
    method: "DELETE",
  });
}

export async function generateVideoSummary(seriesId, videoId, options = {}) {
  return toWorkspaceSummary(
    await fetchJson(`/api/videos/${encodeURIComponent(seriesId)}/${encodeURIComponent(videoId)}/generate`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        transcript_enhancement_enabled:
          typeof options.transcriptEnhancementEnabled === "boolean"
            ? options.transcriptEnhancementEnabled
            : undefined,
      }),
    }),
  );
}

export async function cancelVideoSummary(seriesId, videoId) {
  return fetchJson(`/api/videos/${encodeURIComponent(seriesId)}/${encodeURIComponent(videoId)}/generate/cancel`, {
    method: "POST",
  });
}

export async function loadVideoGenerationStatus(seriesId, videoId) {
  const payload = await fetchJson(`/api/videos/${encodeURIComponent(seriesId)}/${encodeURIComponent(videoId)}/generate/status`);
  return {
    taskId: typeof payload.task_id === "string" ? payload.task_id : `${seriesId}/${videoId}`,
    snapshot: toProgressSnapshot(payload.snapshot ?? {}),
  };
}

export async function generateSeriesSummaries(seriesId, options = {}) {
  return fetchJson(`/api/series/${encodeURIComponent(seriesId)}/generate`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      transcript_enhancement_enabled:
        typeof options.transcriptEnhancementEnabled === "boolean"
          ? options.transcriptEnhancementEnabled
          : undefined,
      run_id: typeof options.runId === "string" ? options.runId : undefined,
    }),
  });
}

export async function cancelSeriesSummaries(seriesId, options = {}) {
  return fetchJson(`/api/series/${encodeURIComponent(seriesId)}/generate/cancel`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      run_id: typeof options.runId === "string" ? options.runId : undefined,
    }),
  });
}

export async function loadSeriesGenerationStatus(seriesId) {
  const payload = await fetchJson(`/api/series/${encodeURIComponent(seriesId)}/generate/status`);
  return {
    taskId: typeof payload.task_id === "string" ? payload.task_id : `series/${seriesId}`,
    snapshot: toProgressSnapshot(payload.snapshot ?? {}),
  };
}

export async function generateVideoMindmap(seriesId, videoId) {
  return toWorkspaceMindmap(
    await fetchJson(`/api/videos/${encodeURIComponent(seriesId)}/${encodeURIComponent(videoId)}/mindmap/generate`, {
      method: "POST",
    }),
  );
}

export async function sendAgentChat(sessionId, message, context) {
  return fetchJson("/api/agent/chat", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      session_id: sessionId,
      message,
      context: context ?? null,
    }),
  });
}

export async function loadAgentContextUsage(sessionId, context) {
  return toWorkspaceContextUsage(
    await fetchJson("/api/agent/context/usage", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        session_id: sessionId,
        context: context ?? null,
      }),
    }),
  );
}

export async function loadAgentMemoryStatus() {
  return toProgressSnapshot(await fetchJson("/api/agent/memory/status"));
}

export async function loadAgentSessionRecovery(sessionId, context) {
  const payload = await fetchJson("/api/agent/session/recover", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      session_id: sessionId,
      context: context ?? null,
    }),
  });
  return {
    sessionId: payload.session_id,
    restored: Boolean(payload.restored),
    memoryKey: typeof payload.memory_key === "string" ? payload.memory_key : null,
    updatedAt: typeof payload.updated_at === "string" ? payload.updated_at : null,
    messageCount: typeof payload.message_count === "number" ? payload.message_count : 0,
    messages: Array.isArray(payload.messages)
      ? payload.messages.map((message, index) => ({
        id: `recovered-${payload.session_id}-${index}`,
        role: typeof message.role === "string" ? message.role : "assistant",
        content: typeof message.content === "string" ? message.content : "",
        citations: Array.isArray(message.citations) ? message.citations : null,
        meta: buildRecoveredMeta(
          typeof message.role === "string" ? message.role : "assistant",
          typeof message.created_at === "string" ? message.created_at : "",
        ),
      }))
      : [],
  };
}

export async function clearAgentSession(sessionId, context) {
  return fetchJson("/api/agent/session/clear", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      session_id: sessionId,
      context: context ?? null,
    }),
  });
}

export async function streamAgentChat(sessionId, message, context, listener, { signal } = {}) {
  const response = await fetch("/api/agent/chat/stream", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      session_id: sessionId,
      message,
      context: context ?? null,
    }),
    signal,
  });
  if (!response.ok) {
    let detail = "";
    try {
      const payload = await response.json();
      detail = typeof payload.detail === "string" ? payload.detail : "";
    } catch {
      detail = "";
    }
    throw new Error(detail ? `${response.status} ${detail}` : "AI 对话失败");
  }
  if (response.body == null) {
    throw new Error("AI 对话流未返回内容。");
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder("utf-8");
  let buffer = "";

  try {
    while (true) {
      const { done, value } = await reader.read();
      buffer += decoder.decode(value ?? new Uint8Array(), { stream: !done });

      let boundary = buffer.indexOf("\n\n");
      while (boundary !== -1) {
        const rawEvent = buffer.slice(0, boundary);
        buffer = buffer.slice(boundary + 2);
        const event = parseSseEvent(rawEvent);
        if (event != null) {
          if (event.type === "error") {
            listener(event);
            const error = new Error(typeof event.payload?.message === "string" ? event.payload.message : "AI 对话失败");
            error.streamErrorDispatched = true;
            throw error;
          }
          listener(event);
        }
        boundary = buffer.indexOf("\n\n");
      }

      if (done) {
        break;
      }
    }
  } finally {
    reader.releaseLock();
  }
}

export async function uploadSrtAndGenerateVideoSummary(seriesId, videoId, file) {
  const formData = new FormData();
  formData.append("file", file);
  return toWorkspaceSummary(
    await fetchJson(`/api/videos/${encodeURIComponent(seriesId)}/${encodeURIComponent(videoId)}/transcript/srt-and-generate`, {
      method: "POST",
      body: formData,
    }),
  );
}

export async function restoreAutomaticTranscriptAndGenerateVideoSummary(seriesId, videoId) {
  return toWorkspaceSummary(
    await fetchJson(`/api/videos/${encodeURIComponent(seriesId)}/${encodeURIComponent(videoId)}/transcript/restore-auto-and-generate`, {
      method: "POST",
    }),
  );
}

export function subscribeVideoGenerationProgress(seriesId, videoId, listener) {
  const eventSource = new EventSource(
    `/api/videos/${encodeURIComponent(seriesId)}/${encodeURIComponent(videoId)}/generate/progress`,
  );
  let terminal = false;

  eventSource.onmessage = (event) => {
    const snapshot = parseProgressMessage(event.data);
    listener(snapshot);
    if (snapshot.status === "completed" || snapshot.status === "failed" || snapshot.status === "cancelled") {
      terminal = true;
      eventSource.close();
    }
  };

  eventSource.onerror = () => {
    if (terminal) {
      return;
    }
    listener({
      status: "failed",
      stage: "failed",
      progress: null,
      detail: null,
      error: "生成进度连接已中断",
    });
    eventSource.close();
  };

  return () => {
    terminal = true;
    eventSource.close();
  };
}

export function subscribeSeriesGenerationProgress(seriesId, listener) {
  const eventSource = new EventSource(
    `/api/series/${encodeURIComponent(seriesId)}/generate/progress`,
  );
  let terminal = false;

  eventSource.onmessage = (event) => {
    const snapshot = parseProgressMessage(event.data);
    listener(snapshot);
    if (snapshot.status === "completed" || snapshot.status === "failed" || snapshot.status === "cancelled") {
      terminal = true;
      eventSource.close();
    }
  };

  eventSource.onerror = () => {
    if (terminal) {
      return;
    }
    listener({
      status: "failed",
      stage: "failed",
      progress: null,
      detail: null,
      error: "系列生成进度连接已中断",
    });
    eventSource.close();
  };

  return () => {
    terminal = true;
    eventSource.close();
  };
}

export function getVideoPreviewUrl(seriesId, videoId) {
  return `/api/videos/${encodeURIComponent(seriesId)}/${encodeURIComponent(videoId)}/preview`;
}

async function fetchJson(path, init, options = {}) {
  const response = await fetch(path, init);
  if (response.status === 404 && Object.prototype.hasOwnProperty.call(options, "notFoundValue")) {
    return options.notFoundValue;
  }
  if (!response.ok) {
    let detail = null;
    try {
      const payload = await response.json();
      detail = extractErrorMessage(payload);
    } catch {
      detail = null;
    }
    throw new Error(detail ? `${response.status} ${detail}` : `${response.status} 请求失败：${path}`);
  }
  return response.json();
}

function extractErrorMessage(payload) {
  if (!payload || typeof payload !== "object") {
    return null;
  }
  for (const key of ["detail", "message", "error"]) {
    const value = payload[key];
    if (typeof value === "string" && value.trim()) {
      return value.trim();
    }
  }
  if (Array.isArray(payload.detail) && payload.detail.length > 0) {
    return payload.detail
      .map((item) => {
        if (typeof item === "string") {
          return item;
        }
        if (item && typeof item === "object") {
          const location = Array.isArray(item.loc) ? item.loc.join(".") : "";
          const message = typeof item.msg === "string" ? item.msg : JSON.stringify(item);
          return location ? `${location}: ${message}` : message;
        }
        return String(item);
      })
      .join("; ");
  }
  return null;
}

function parseProgressMessage(rawValue) {
  return toProgressSnapshot(JSON.parse(rawValue));
}

function toProviderUsage(payload) {
  const record = payload && typeof payload === "object" ? payload : {};
  return {
    range: typeof record.range === "string" ? record.range : "7d",
    total: toTokenTotals(record.total),
    byCategory: Array.isArray(record.by_category)
      ? record.by_category.map(toUsageCategory)
      : [],
    byProvider: Array.isArray(record.by_provider)
      ? record.by_provider.map(toUsageProvider)
      : [],
    recent: Array.isArray(record.recent)
      ? record.recent.map(toUsageRecord)
      : [],
    timelineGranularity: typeof record.timeline_granularity === "string" ? record.timeline_granularity : "day",
    timeline: Array.isArray(record.timeline)
      ? record.timeline.map(toUsageTimelineBucket)
      : [],
  };
}

function toUsageCategory(item) {
  const record = item && typeof item === "object" ? item : {};
  return {
    category: typeof record.category === "string" ? record.category : "",
    ...toTokenTotals(record),
  };
}

function toUsageProvider(item) {
  const record = item && typeof item === "object" ? item : {};
  return {
    provider: typeof record.provider === "string" ? record.provider : "",
    baseUrl: typeof record.base_url === "string" ? record.base_url : "",
    model: typeof record.model === "string" ? record.model : "",
    ...toTokenTotals(record),
  };
}

function toUsageRecord(item) {
  const record = item && typeof item === "object" ? item : {};
  return {
    createdAt: typeof record.created_at === "string" ? record.created_at : "",
    category: typeof record.category === "string" ? record.category : "",
    provider: typeof record.provider === "string" ? record.provider : "",
    baseUrl: typeof record.base_url === "string" ? record.base_url : "",
    model: typeof record.model === "string" ? record.model : "",
    ...toTokenTotals(record),
  };
}

function toUsageTimelineBucket(item) {
  const record = item && typeof item === "object" ? item : {};
  return {
    startedAt: typeof record.started_at === "string" ? record.started_at : "",
    generationTokens: typeof record.generation_tokens === "number" ? record.generation_tokens : 0,
    chatTokens: typeof record.chat_tokens === "number" ? record.chat_tokens : 0,
    totalTokens: typeof record.total_tokens === "number" ? record.total_tokens : 0,
  };
}

function toTokenTotals(record) {
  const source = record && typeof record === "object" ? record : {};
  return {
    promptTokens: typeof source.prompt_tokens === "number" ? source.prompt_tokens : 0,
    completionTokens: typeof source.completion_tokens === "number" ? source.completion_tokens : 0,
    totalTokens: typeof source.total_tokens === "number" ? source.total_tokens : 0,
  };
}

function toProgressSnapshot(payload) {
  return {
    status: typeof payload.status === "string" ? payload.status : "idle",
    stage: typeof payload.stage === "string" ? payload.stage : null,
    progress: typeof payload.progress === "number" ? payload.progress : null,
    detail: typeof payload.detail === "string" ? payload.detail : null,
    error: typeof payload.error === "string" ? payload.error : null,
    startedAt: typeof payload.started_at === "number" ? payload.started_at : null,
    stageStartedAt: typeof payload.stage_started_at === "number" ? payload.stage_started_at : null,
    elapsedSeconds: typeof payload.elapsed_seconds === "number" ? payload.elapsed_seconds : null,
    stageElapsedSeconds:
      typeof payload.stage_elapsed_seconds === "number" ? payload.stage_elapsed_seconds : null,
    estimatedTotalSeconds:
      typeof payload.estimated_total_seconds === "number" ? payload.estimated_total_seconds : null,
    remainingSeconds: typeof payload.remaining_seconds === "number" ? payload.remaining_seconds : null,
    updatedAt: typeof payload.updated_at === "number" ? payload.updated_at : null,
  };
}

function parseSseEvent(rawValue) {
  const lines = rawValue
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean);
  if (!lines.length) {
    return null;
  }

  let type = "message";
  const dataLines = [];
  for (const line of lines) {
    if (line.startsWith("event:")) {
      type = line.slice("event:".length).trim() || "message";
      continue;
    }
    if (line.startsWith("data:")) {
      dataLines.push(line.slice("data:".length).trim());
    }
  }

  const rawData = dataLines.join("\n");
  return {
    type,
    payload: rawData ? JSON.parse(rawData) : {},
  };
}

function buildRecoveredMeta(role, createdAt) {
  const actor = role === "user" ? "You" : "Notebook Assistant";
  const suffix = createdAt ? "已恢复" : "恢复记录";
  return `${actor} • ${suffix}`;
}

export async function selectLocalMedia() {
  const payload = await fetchJson("/api/import/local/select", {
    method: "POST",
  });
  const sourcePaths = Array.isArray(payload.source_paths)
    ? payload.source_paths.filter((path) => typeof path === "string" && path)
    : [];
  return {
    sourcePaths,
    hardlinkAvailable: payload.hardlink_available !== false,
  };
}

export async function importLocalSeries(seriesTitle, sourcePaths, storageMode) {
  return fetchJson("/api/import/local/series/from-paths", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      series_title: seriesTitle,
      source_paths: sourcePaths,
      storage_mode: storageMode,
    }),
  });
}

export async function uploadLocalSeries(seriesTitle, files) {
  const formData = new FormData();
  formData.append("series_title", seriesTitle);
  appendMediaFiles(formData, files);
  return fetchJson("/api/import/local/series", {
    method: "POST",
    body: formData,
  });
}

export async function resolveBilibiliSeries(url) {
  return fetchJson("/api/linked/bilibili/resolve/series", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ url }),
  });
}

export async function resolveBilibiliVideo(url, targetSeriesId = null) {
  return fetchJson("/api/linked/bilibili/resolve/video", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ url, target_series_id: targetSeriesId }),
  });
}

export async function initBilibiliCookie(options = {}) {
  const payload = await fetchJson("/api/linked/bilibili/cookie/init", {
    method: "POST",
    signal: options.signal,
  });
  return {
    configured: payload.configured === true,
  };
}
export async function loadChaoxingStatus() {
  const payload = await fetchJson("/api/linked/chaoxing/status");
  return {
    initialized: payload.initialized === true,
  };
}

export async function initChaoxing(options = {}) {
  const payload = await fetchJson("/api/linked/chaoxing/init", {
    method: "POST",
    signal: options.signal,
  });
  return {
    initialized: payload.initialized === true,
  };
}

export async function cancelChaoxingInit() {
  return fetchJson("/api/linked/chaoxing/init/cancel", {
    method: "POST",
  });
}

export async function loadChaoxingCourses() {
  const payload = await fetchJson("/api/linked/chaoxing/courses");
  return Array.isArray(payload)
    ? payload.map((course) => ({
      courseKey: typeof course.course_key === "string" ? course.course_key : "",
      title: typeof course.title === "string" ? course.title : "",
      teacher: typeof course.teacher === "string" ? course.teacher : "",
      openTime: typeof course.open_time === "string" ? course.open_time : "",
    })).filter((course) => course.courseKey && course.title)
    : [];
}

export async function importChaoxingCourse(courseKey) {
  const payload = await fetchJson("/api/linked/chaoxing/import/course", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ course_key: courseKey }),
  });
  return {
    taskId: typeof payload.task_id === "string" ? payload.task_id : "",
    seriesId: typeof payload.series_id === "string" ? payload.series_id : "",
  };
}

export async function cancelChaoxingImport(taskId) {
  return fetchJson(`/api/linked/chaoxing/import/course/${encodeURIComponent(taskId)}/cancel`, {
    method: "POST",
  });
}

export function subscribeChaoxingImportProgress(taskId, listener) {
  return subscribeProgress(
    `/api/linked/chaoxing/import/course/${encodeURIComponent(taskId)}/progress`,
    listener,
    "超星课程导入进度连接已中断",
  );
}

export async function importLocalPlaygroundVideos(sourcePaths) {
  return fetchJson("/api/import/local/playground/from-paths", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ source_paths: sourcePaths }),
  });
}

export async function uploadLocalPlaygroundVideos(files) {
  const formData = new FormData();
  appendMediaFiles(formData, files);
  return fetchJson("/api/import/local/playground", {
    method: "POST",
    body: formData,
  });
}

export async function importLocalSeriesVideos(seriesId, sourcePaths) {
  return fetchJson(`/api/import/local/series/${encodeURIComponent(seriesId)}/from-paths`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ source_paths: sourcePaths }),
  });
}

export async function uploadLocalSeriesVideos(seriesId, files) {
  const formData = new FormData();
  appendMediaFiles(formData, files);
  return fetchJson(`/api/import/local/series/${encodeURIComponent(seriesId)}`, {
    method: "POST",
    body: formData,
  });
}

function appendMediaFiles(formData, files) {
  for (const file of files) {
    formData.append("files", file, file.name);
  }
}

export async function deleteSeries(seriesId) {
  return fetchJson(`/api/series/${encodeURIComponent(seriesId)}`, {
    method: "DELETE",
  });
}

export async function renameSeries(seriesId, title) {
  return fetchJson(`/api/series/${encodeURIComponent(seriesId)}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title }),
  });
}

export async function deleteVideoSource(seriesId, videoId) {
  return fetchJson(`/api/videos/${encodeURIComponent(seriesId)}/${encodeURIComponent(videoId)}`, {
    method: "DELETE",
  });
}

export async function renameVideoSource(seriesId, videoId, title) {
  return fetchJson(`/api/videos/${encodeURIComponent(seriesId)}/${encodeURIComponent(videoId)}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title }),
  });
}

export async function startVideoDownload(seriesId, videoId) {
  return fetchJson(`/api/videos/${encodeURIComponent(seriesId)}/${encodeURIComponent(videoId)}/download`, {
    method: "POST",
  });
}

export async function cancelVideoDownload(seriesId, videoId) {
  return fetchJson(`/api/videos/${encodeURIComponent(seriesId)}/${encodeURIComponent(videoId)}/download/cancel`, {
    method: "POST",
  });
}

export function subscribeVideoDownloadProgress(seriesId, videoId, listener) {
  return subscribeProgress(
    `/api/videos/${encodeURIComponent(seriesId)}/${encodeURIComponent(videoId)}/download/progress`,
    listener,
    "视频下载进度连接已中断",
  );
}

export async function loadSeriesMindmap(seriesId) {
  const payload = await fetchJson(
    `/api/series/${encodeURIComponent(seriesId)}/mindmap`,
    undefined,
    { notFoundValue: null },
  );
  if (payload == null) {
    return null;
  }
  return toWorkspaceMindmap(payload);
}

export async function generateSeriesMindmap(seriesId) {
  const payload = await fetchJson(`/api/series/${encodeURIComponent(seriesId)}/mindmap/generate`, {
    method: "POST",
  });
  return toWorkspaceMindmap(payload);
}

export function subscribeMindmapGenerationProgress(seriesId, videoId, listener) {
  const eventSource = new EventSource(
    `/api/videos/${encodeURIComponent(seriesId)}/${encodeURIComponent(videoId)}/mindmap/generate/progress`
  );
  let terminal = false;

  eventSource.onmessage = (event) => {
    const snapshot = JSON.parse(event.data);
    listener(snapshot);
    if (snapshot.status === "completed" || snapshot.status === "failed" || snapshot.status === "cancelled") {
      terminal = true;
      eventSource.close();
    }
  };

  eventSource.onerror = () => {
    if (terminal) return;
    listener({ status: "failed", stage: "failed", progress: null, detail: "进度连接已中断", error: "进度连接已中断" });
    eventSource.close();
  };

  return () => {
    terminal = true;
    eventSource.close();
  };
}

export function subscribeSeriesMindmapGenerationProgress(seriesId, listener) {
  const eventSource = new EventSource(
    `/api/series/${encodeURIComponent(seriesId)}/mindmap/generate/progress`
  );
  let terminal = false;

  eventSource.onmessage = (event) => {
    const snapshot = JSON.parse(event.data);
    listener(snapshot);
    if (snapshot.status === "completed" || snapshot.status === "failed" || snapshot.status === "cancelled") {
      terminal = true;
      eventSource.close();
    }
  };

  eventSource.onerror = () => {
    if (terminal) return;
    listener({ status: "failed", stage: "failed", progress: null, detail: "进度连接已中断", error: "进度连接已中断" });
    eventSource.close();
  };

  return () => {
    terminal = true;
    eventSource.close();
  };
}
