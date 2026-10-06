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
import { advanceGenerationSteps } from "./generationSteps";
export function createWorkspaceApi(transport){

async function loadWorkspaceLibrary() {
  return toWorkspaceLibrary(await fetchJson("/api/videos"));
}

async function loadProviderUsage(range = "7d") {
  return toProviderUsage(await fetchJson(`/api/provider-settings/usage?range=${encodeURIComponent(range)}`));
}

const loadUserPreferences=()=>fetchJson('/api/preferences');
const updateUserPreferences=values=>fetchJson('/api/preferences',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify(values)});
const loadJobs=({status,operation,offset=0,limit=50}={})=>{
  const query=new URLSearchParams({offset:String(offset),limit:String(limit)});
  if(status)query.set('status',status);
  if(operation)query.set('operation',operation);
  return fetchJson(`/api/jobs?${query.toString()}`);
};
const loadJobStatistics=()=>fetchJson('/api/jobs/stats');
const loadJob=jobId=>fetchJson(`/api/jobs/${encodeURIComponent(jobId)}`);
const cancelChatRequest=requestId=>fetchJson(`/api/chat-requests/${encodeURIComponent(requestId)}/cancel`,{method:'POST'});

async function checkBackendHealth() {
  const response = await transport.fetch("/api/health");
  if (!response.ok) {
    throw new Error(`health check failed: ${response.status}`);
  }
  return response.json();
}

async function loadVideoSummary(seriesId, videoId) {
  return toWorkspaceSummary(await fetchJson(`/api/videos/${encodeURIComponent(seriesId)}/${encodeURIComponent(videoId)}/summary`));
}

async function updateVideoSummary(seriesId, videoId, summary) {
  return toWorkspaceSummary(
    await fetchJson(`/api/videos/${encodeURIComponent(seriesId)}/${encodeURIComponent(videoId)}/summary`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ markdown: summary }),
    }),
  );
}

async function loadVideoSummaryMarkdown(seriesId, videoId) {
  const payload = await fetchJson(`/api/videos/${encodeURIComponent(seriesId)}/${encodeURIComponent(videoId)}/summary/markdown`);
  if (typeof payload.markdown !== "string") {
    throw new Error("summary markdown 不是有效文本。");
  }
  return payload.markdown;
}

async function loadVideoTranscriptMarkdown(seriesId, videoId) {
  const payload = await fetchJson(`/api/videos/${encodeURIComponent(seriesId)}/${encodeURIComponent(videoId)}/transcript/markdown`);
  if (typeof payload.markdown !== "string") {
    throw new Error("transcript markdown 不是有效文本。");
  }
  return payload.markdown;
}

async function updateVideoTranscript(seriesId, videoId, markdown) {
  return fetchJson(`/api/videos/${encodeURIComponent(seriesId)}/${encodeURIComponent(videoId)}/transcript`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ markdown }),
  });
}

async function loadVideoTools(seriesId, videoId) {
  return toWorkspaceTools(await fetchJson(`/api/videos/${encodeURIComponent(seriesId)}/${encodeURIComponent(videoId)}/tools`));
}

async function loadVideoMindmap(seriesId, videoId) {
  return toWorkspaceMindmap(await fetchJson(`/api/videos/${encodeURIComponent(seriesId)}/${encodeURIComponent(videoId)}/mindmap`));
}

async function loadVideoKnowledgeCards(seriesId, videoId) {
  return toWorkspaceKnowledgeCards(
    await fetchJson(`/api/videos/${encodeURIComponent(seriesId)}/${encodeURIComponent(videoId)}/knowledge-cards`),
  );
}

async function generateVideoKnowledgeCards(seriesId, videoId) {
  const payload = await fetchJson(`/api/videos/${encodeURIComponent(seriesId)}/${encodeURIComponent(videoId)}/knowledge-cards/generate`, {
    method: "POST",
  });
  if (typeof payload.job_id !== "string" || !payload.job_id) {
    throw new Error("知识卡片任务未返回 job_id。");
  }
  return { jobId: payload.job_id, status: typeof payload.status === "string" ? payload.status : "queued" };
}

async function loadVideoNotes(seriesId, videoId) {
  return toWorkspaceNotes(await fetchJson(`/api/videos/${encodeURIComponent(seriesId)}/${encodeURIComponent(videoId)}/notes`));
}

async function createVideoNote(seriesId, videoId, note) {
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

async function loadVideoAiSummary(seriesId, videoId) {
  return toWorkspaceAiSummary(
    await fetchJson(`/api/videos/${encodeURIComponent(seriesId)}/${encodeURIComponent(videoId)}/ai-summary`),
  );
}

async function generateVideoAiSummary(seriesId, videoId, template = "general") {
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

async function updateVideoAiSummary(seriesId, videoId, summary) {
  return toWorkspaceAiSummary(
    await fetchJson(`/api/videos/${encodeURIComponent(seriesId)}/${encodeURIComponent(videoId)}/ai-summary`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title: summary.title, content: summary.content }),
    }),
  );
}

async function updateVideoNote(seriesId, videoId, noteId, note) {
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

async function deleteVideoNote(seriesId, videoId, noteId) {
  return fetchJson(`/api/videos/${encodeURIComponent(seriesId)}/${encodeURIComponent(videoId)}/notes/${encodeURIComponent(noteId)}`, {
    method: "DELETE",
  });
}

async function generateVideoSummary(seriesId, videoId, options = {}) {
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
        ai_summary_template: typeof options.aiSummaryTemplate === "string" ? options.aiSummaryTemplate : "general",
      }),
    }));
}

async function processAgentVideo(seriesId, videoId, options = {}) {
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
  const job = payload.jobs?.find((item) => item.resource?.type === "video" && item.resource.id === videoId);
  if (!job) {
    throw new Error("视频处理响应中没有当前视频的任务。");
  }
  return toVideoGenerationSubmission(job);
}

async function cancelVideoSummary(seriesId, videoId) {
  return fetchJson(`/api/videos/${encodeURIComponent(seriesId)}/${encodeURIComponent(videoId)}/generate/cancel`, {
    method: "POST",
  });
}

async function loadVideoGenerationStatus(seriesId, videoId) {
  const payload = await fetchJson(`/api/videos/${encodeURIComponent(seriesId)}/${encodeURIComponent(videoId)}/generate/status`);
  return {
    taskId: typeof payload.task_id === "string" ? payload.task_id : `${seriesId}/${videoId}`,
    jobId: typeof payload.job_id === "string" ? payload.job_id : null,
    snapshot: payload.job_id ? toDurableGenerationSnapshot(payload.snapshot ?? {}) : toProgressSnapshot(payload.snapshot ?? {}),
  };
}

async function generateSeriesSummaries(seriesId, options = {}) {
  const payload = await fetchJson(`/api/series/${encodeURIComponent(seriesId)}/generate`, {
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
  return toVideoGenerationSubmission(payload);
}

async function cancelSeriesSummaries(seriesId, options = {}) {
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

async function loadSeriesGenerationStatus(seriesId) {
  const payload = await fetchJson(`/api/series/${encodeURIComponent(seriesId)}/generate/status`);
  return {
    taskId: typeof payload.task_id === "string" ? payload.task_id : `series/${seriesId}`,
    snapshot: toProgressSnapshot(payload.snapshot ?? {}),
  };
}

async function generateVideoMindmap(seriesId, videoId, maxDepth = null) {
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

async function loadAgentContextUsage(sessionId, context) {
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

async function loadAgentMemoryStatus() {
  return toProgressSnapshot(await fetchJson("/api/workspace/index/status"));
}

async function loadAgentSessionRecovery(sessionId, context) {
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

async function clearAgentSession(sessionId, context) {
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

async function streamAgentChat(sessionId, message, context, listener, { signal } = {}) {
  const response = await transport.fetch("/api/agent/chat/stream", {
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

async function uploadSrtAndGenerateVideoSummary(seriesId, videoId, file) {
  const formData = new FormData();
  formData.append("file", file);
  return toVideoGenerationSubmission(
    await fetchJson(`/api/videos/${encodeURIComponent(seriesId)}/${encodeURIComponent(videoId)}/transcript/srt-and-generate`, {
      method: "POST",
      body: formData,
    }),
  );
}

async function restoreAutomaticTranscriptAndGenerateVideoSummary(seriesId, videoId) {
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
  const startedAt = toEpochSeconds(payload?.started_at);
  const elapsedSeconds = typeof payload?.elapsed_seconds === "number"
    ? payload.elapsed_seconds
    : startedAt == null
      ? null
      : Math.max(0, Date.now() / 1000 - startedAt);
  const progress = typeof payload?.progress === "number" ? payload.progress : null;
  return {
    status: typeof status === "string" ? status : "failed",
    stage: typeof payload?.stage === "string" ? payload.stage : null,
    progress,
    detail,
    error,
    startedAt,
    elapsedSeconds,
    estimatedTotalSeconds: null,
    remainingSeconds: null,
    steps: restoreGenerationSteps(payload),
  };
}

function toEpochSeconds(value) {
  if (typeof value === "number" && Number.isFinite(value)) {
    return value;
  }
  if (typeof value !== "string") {
    return null;
  }
  const milliseconds = Date.parse(value);
  return Number.isNaN(milliseconds) ? null : milliseconds / 1000;
}

function subscribeDurableJobProgress(jobId, listener) {
  const eventSource = transport.subscribe(`/api/jobs/${encodeURIComponent(jobId)}/events`);
  let terminal = false;
  let steps = [];
  let progress = null;

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
    steps = advanceGenerationSteps(steps, snapshot);
    if (snapshot.progress != null) progress = Math.max(progress ?? 0, snapshot.progress);
    snapshot.steps = steps;
    snapshot.progress = progress;
    listener(snapshot);
    if (snapshot.status === "completed" || snapshot.status === "failed" || snapshot.status === "cancelled") {
      terminal = true;
      eventSource.close();
    }
  });

  eventSource.onerror = () => {
    if (terminal) return;
    if (eventSource.readyState === transport.CLOSED) {
      terminal = true;
      listener({ status: "failed", stage: "failed", progress: null, detail: null, error: "生成进度连接已关闭" });
      return;
    }
    listener({ status: "running", stage: "reconnecting", progress: null, detail: "正在同步生成进度...", error: null });
  };

  return () => {
    terminal = true;
    eventSource.close();
  };
}

function subscribeVideoGenerationProgress(seriesId, videoId, listener) {
  const eventSource = transport.subscribe(
    `/api/videos/${encodeURIComponent(seriesId)}/${encodeURIComponent(videoId)}/generate/progress`,
  );
  let terminal = false;

  eventSource.addEventListener("progress", (event) => {
    const snapshot = parseProgressMessage(event.data);
    listener(snapshot);
    if (snapshot.status === "completed" || snapshot.status === "failed" || snapshot.status === "cancelled") {
      terminal = true;
      eventSource.close();
    }
  });

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

function subscribeSeriesGenerationProgress(seriesId, listener) {
  const eventSource = transport.subscribe(
    `/api/series/${encodeURIComponent(seriesId)}/generate/progress`,
  );
  let terminal = false;

  eventSource.addEventListener("progress", (event) => {
    const snapshot = parseProgressMessage(event.data);
    listener(snapshot);
    if (snapshot.status === "completed" || snapshot.status === "failed" || snapshot.status === "cancelled") {
      terminal = true;
      eventSource.close();
    }
  });

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

function getVideoPreviewUrl(seriesId, videoId) {
  return transport.resourceUrl(`/api/videos/${encodeURIComponent(seriesId)}/${encodeURIComponent(videoId)}/preview`);
}

async function fetchJson(path, init, options = {}) {
  const response = await transport.fetch(path, init);
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

function restoreGenerationSteps(payload) {
  if (!Array.isArray(payload.events)) return undefined;
  return payload.events.reduce((steps, event) => advanceGenerationSteps(steps, {
    ...event, status: event.status === 'succeeded' ? 'completed' : event.status,
  }), []);
}

function toProgressSnapshot(payload) {
  return {
    status: payload.status === "succeeded" ? "completed" : typeof payload.status === "string" ? payload.status : "idle",
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
    steps: restoreGenerationSteps(payload),
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

async function resolveLinkedSeries(provider, url, selection = null) {
  if(selection)return fetchJson(`/api/import/linked/${encodeURIComponent(selection.token)}/commit`,{
    method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({selected_video_ids:selection.selectedVideoIds})});
  return fetchJson(`/api/linked/${encodeURIComponent(provider)}/resolve/series`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ url }),
  });

}

async function resolveLinkedVideo(provider, url, targetSeriesId = null) {
  return fetchJson(`/api/linked/${encodeURIComponent(provider)}/resolve/video`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ url, target_series_id: targetSeriesId }),
  });

}

async function resolveBilibiliInboxVideo(url) {
  return fetchJson("/api/linked/bilibili/inbox/resolve/video", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ url }),
  });
}

async function cancelDurableJob(jobId) {
  return fetchJson(`/api/jobs/${encodeURIComponent(jobId)}/cancel`, { method: "POST" });
}

async function deleteSeries(seriesId) {
  return fetchJson(`/api/series/${encodeURIComponent(seriesId)}`, {
    method: "DELETE",
  });
}

async function renameSeries(seriesId, title) {
  return fetchJson(`/api/series/${encodeURIComponent(seriesId)}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title }),
  });
}

async function deleteVideoSource(seriesId, videoId) {
  return fetchJson(`/api/videos/${encodeURIComponent(seriesId)}/${encodeURIComponent(videoId)}`, {
    method: "DELETE",
  });
}

async function renameVideoSource(seriesId, videoId, title) {
  return fetchJson(`/api/videos/${encodeURIComponent(seriesId)}/${encodeURIComponent(videoId)}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title }),
  });
}

async function startVideoDownload(seriesId, videoId) {
  const payload = await fetchJson(`/api/videos/${encodeURIComponent(seriesId)}/${encodeURIComponent(videoId)}/download`, {
    method: "POST",
  });
  const jobId = typeof payload?.job_id === "string" ? payload.job_id.trim() : "";
  if (!jobId) {
    throw new Error("视频下载任务未返回 job_id。");
  }
  return { jobId, status: typeof payload.status === "string" ? payload.status : "queued" };
}

async function cancelVideoDownload(seriesId, videoId) {
  return fetchJson(`/api/videos/${encodeURIComponent(seriesId)}/${encodeURIComponent(videoId)}/download/cancel`, {
    method: "POST",
  });
}

async function loadSeriesMindmap(seriesId) {
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

async function generateSeriesMindmap(seriesId, maxDepth = null) {
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
return {loadUserPreferences,updateUserPreferences,loadJobs,loadJobStatistics,loadJob,cancelChatRequest,loadWorkspaceLibrary,loadProviderUsage,checkBackendHealth,loadVideoSummary,updateVideoSummary,loadVideoSummaryMarkdown,loadVideoTranscriptMarkdown,updateVideoTranscript,loadVideoTools,loadVideoMindmap,loadVideoKnowledgeCards,generateVideoKnowledgeCards,loadVideoNotes,createVideoNote,loadVideoAiSummary,generateVideoAiSummary,updateVideoAiSummary,updateVideoNote,deleteVideoNote,generateVideoSummary,processAgentVideo,cancelVideoSummary,loadVideoGenerationStatus,generateSeriesSummaries,cancelSeriesSummaries,loadSeriesGenerationStatus,generateVideoMindmap,loadAgentContextUsage,loadAgentMemoryStatus,loadAgentSessionRecovery,clearAgentSession,streamAgentChat,uploadSrtAndGenerateVideoSummary,restoreAutomaticTranscriptAndGenerateVideoSummary,subscribeDurableJobProgress,subscribeVideoGenerationProgress,subscribeSeriesGenerationProgress,getVideoPreviewUrl,fetchJson,toProviderUsage,toProgressSnapshot,resolveLinkedSeries,resolveLinkedVideo,resolveBilibiliInboxVideo,cancelDurableJob,deleteSeries,renameSeries,deleteVideoSource,renameVideoSource,startVideoDownload,cancelVideoDownload,loadSeriesMindmap,generateSeriesMindmap, resourceUrl:transport.resourceUrl, dispose:transport.dispose};
}
