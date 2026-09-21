import {
  toWorkspaceCards,
  toWorkspaceAiSummary,
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

export async function loadVideoKnowledgeCards(seriesId, videoId) {
  return toWorkspaceKnowledgeCards(
    await fetchJson(`/api/videos/${encodeURIComponent(seriesId)}/${encodeURIComponent(videoId)}/knowledge-cards`),
  );
}

export async function generateVideoKnowledgeCards(seriesId, videoId) {
  const payload = await fetchJson(`/api/videos/${encodeURIComponent(seriesId)}/${encodeURIComponent(videoId)}/knowledge-cards/generate`, {
    method: "POST",
  });
  if (typeof payload.job_id !== "string" || !payload.job_id) {
    throw new Error("知识卡片任务未返回 job_id。");
  }
  return { jobId: payload.job_id, status: typeof payload.status === "string" ? payload.status : "queued" };
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

export async function loadVideoAiSummary(seriesId, videoId) {
  return toWorkspaceAiSummary(
    await fetchJson(`/api/videos/${encodeURIComponent(seriesId)}/${encodeURIComponent(videoId)}/ai-summary`),
  );
}

export async function generateVideoAiSummary(seriesId, videoId, template = "general") {
  const payload = await fetchJson(`/api/videos/${encodeURIComponent(seriesId)}/${encodeURIComponent(videoId)}/ai-summary/generate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ template }),
  });
  if (typeof payload.job_id !== "string" || !payload.job_id) {
    throw new Error("AI 概括任务未返回 job_id。");
  }
  return { jobId: payload.job_id, status: typeof payload.status === "string" ? payload.status : "queued" };
}

export async function updateVideoAiSummary(seriesId, videoId, summary) {
  return toWorkspaceAiSummary(
    await fetchJson(`/api/videos/${encodeURIComponent(seriesId)}/${encodeURIComponent(videoId)}/ai-summary`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title: summary.title, content: summary.content }),
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
  return toVideoGenerationSubmission(await fetchJson(`/api/videos/${encodeURIComponent(seriesId)}/${encodeURIComponent(videoId)}/generate`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        transcript_enhancement_enabled:
          typeof options.transcriptEnhancementEnabled === "boolean"
            ? options.transcriptEnhancementEnabled
            : undefined,
        processing_mode: options.processingMode === "transcript" ? "transcript" : "summary",
      }),
    }));
}

export async function processAgentVideo(seriesId, videoId, options = {}) {
  const payload = await fetchJson(`/api/agent/series/${encodeURIComponent(seriesId)}/process`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      video_ids: [videoId],
      processing_mode: options.processingMode === "transcript" ? "transcript" : "summary",
    }),
  });
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
    jobId: typeof payload.job_id === "string" ? payload.job_id : null,
    snapshot: payload.job_id ? toDurableGenerationSnapshot(payload.snapshot ?? {}) : toProgressSnapshot(payload.snapshot ?? {}),
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
      processing_mode: options.processingMode === "transcript" ? "transcript" : "summary",
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

export async function generateVideoMindmap(seriesId, videoId, maxDepth = null) {
  const payload = await fetchJson(`/api/videos/${encodeURIComponent(seriesId)}/${encodeURIComponent(videoId)}/mindmap/generate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ max_depth: maxDepth }),
  });
  if (typeof payload.job_id !== "string" || !payload.job_id) {
    throw new Error("思维导图任务未返回 job_id。");
  }
  return { jobId: payload.job_id, status: typeof payload.status === "string" ? payload.status : "queued" };
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
  return toVideoGenerationSubmission(
    await fetchJson(`/api/videos/${encodeURIComponent(seriesId)}/${encodeURIComponent(videoId)}/transcript/srt-and-generate`, {
      method: "POST",
      body: formData,
    }),
  );
}

export async function restoreAutomaticTranscriptAndGenerateVideoSummary(seriesId, videoId) {
  return toVideoGenerationSubmission(
    await fetchJson(`/api/videos/${encodeURIComponent(seriesId)}/${encodeURIComponent(videoId)}/transcript/restore-auto-and-generate`, {
      method: "POST",
    }),
  );
}

function toVideoGenerationSubmission(payload) {
  const jobId = typeof payload?.job_id === "string" ? payload.job_id.trim() : "";
  const status = typeof payload?.status === "string" ? payload.status.trim() : "";
  if (!jobId || !status) {
    throw new Error("生成任务提交响应缺少 job_id 或 status。");
  }
  return { jobId, status };
}

function toDurableGenerationSnapshot(payload) {
  const status = payload?.status === "succeeded" ? "completed" : payload?.status;
  const detail = typeof payload?.detail === "string" ? payload.detail : null;
  const error = typeof payload?.error === "string" ? payload.error : status === "failed" ? detail : null;
  return {
    status: typeof status === "string" ? status : "failed",
    stage: typeof payload?.stage === "string" ? payload.stage : null,
    progress: typeof payload?.progress === "number" ? payload.progress : null,
    detail,
    error,
  };
}

export function subscribeDurableJobProgress(jobId, listener) {
  const eventSource = new EventSource(`/api/jobs/${encodeURIComponent(jobId)}/events`);
  let terminal = false;

  eventSource.addEventListener("progress", (event) => {
    let payload;
    try {
      payload = JSON.parse(event.data);
    } catch {
      listener({ status: "failed", stage: "failed", progress: null, detail: null, error: "生成进度数据格式错误" });
      terminal = true;
      eventSource.close();
      return;
    }
    const snapshot = toDurableGenerationSnapshot(payload);
    listener(snapshot);
    if (snapshot.status === "completed" || snapshot.status === "failed" || snapshot.status === "cancelled") {
      terminal = true;
      eventSource.close();
    }
  });

  eventSource.onerror = () => {
    if (!terminal) {
      listener({ status: "running", stage: "reconnecting", progress: null, detail: "正在同步生成进度...", error: null });
    }
    eventSource.close();
  };

  return () => {
    terminal = true;
    eventSource.close();
  };
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

export async function fetchJson(path, init, options = {}) {
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

export function toProviderUsage(payload) {
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

export function toProgressSnapshot(payload) {
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

export async function resolveLinkedSeries(provider, url) {
  return fetchJson(`/api/linked/${encodeURIComponent(provider)}/resolve/series`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ url }),
  });
  const job = Array.isArray(payload?.jobs)
    ? payload.jobs.find((item) => item?.resource?.id === videoId)
    : null;
  const jobId = typeof job?.job_id === "string" ? job.job_id.trim() : "";
  if (!jobId) {
    throw new Error("Agent 视频处理任务未返回 job_id。");
  }
  return { jobId, status: typeof job.status === "string" ? job.status : "queued" };
}

export async function resolveLinkedVideo(provider, url, targetSeriesId = null) {
  return fetchJson(`/api/linked/${encodeURIComponent(provider)}/resolve/video`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ url, target_series_id: targetSeriesId }),
  });
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
  const payload = await fetchJson(`/api/videos/${encodeURIComponent(seriesId)}/${encodeURIComponent(videoId)}/download`, {
    method: "POST",
  });
  const jobId = typeof payload?.job_id === "string" ? payload.job_id.trim() : "";
  if (!jobId) {
    throw new Error("视频下载任务未返回 job_id。");
  }
  return { jobId, status: typeof payload.status === "string" ? payload.status : "queued" };
}

export async function cancelVideoDownload(seriesId, videoId) {
  return fetchJson(`/api/videos/${encodeURIComponent(seriesId)}/${encodeURIComponent(videoId)}/download/cancel`, {
    method: "POST",
  });
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

export async function generateSeriesMindmap(seriesId, maxDepth = null) {
  const payload = await fetchJson(`/api/series/${encodeURIComponent(seriesId)}/mindmap/generate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ max_depth: maxDepth }),
  });
  if (typeof payload.job_id !== "string" || !payload.job_id) {
    throw new Error("系列思维导图任务未返回 job_id。");
  }
  return { jobId: payload.job_id, status: typeof payload.status === "string" ? payload.status : "queued" };
}
