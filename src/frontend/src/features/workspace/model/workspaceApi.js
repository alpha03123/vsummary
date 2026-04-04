import {
  toWorkspaceCards,
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

export async function loadWorkspaceSettings() {
  const payload = await fetchJson("/api/settings");
  return {
    theme: payload.theme,
    showTakeaways: payload.show_takeaways,
    transcriptEnhancementEnabled: payload.transcript_enhancement_enabled,
    asrModelQuality: payload.asr_model_quality,
    transcriptionMode: payload.transcription_mode,
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
    openaiApiKey: "",
  };
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
      transcript_enhancement_enabled: settings.transcriptEnhancementEnabled,
      asr_model_quality: settings.asrModelQuality,
      transcription_mode: settings.transcriptionMode,
    }),
  });
  return {
    theme: payload.theme,
    showTakeaways: payload.show_takeaways,
    transcriptEnhancementEnabled: payload.transcript_enhancement_enabled,
    asrModelQuality: payload.asr_model_quality,
    transcriptionMode: payload.transcription_mode,
  };
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
    }),
  });
  return {
    llmProvider: payload.llm_provider,
    openaiBaseUrl: payload.openai_base_url,
    openaiModel: payload.openai_model,
    hasOpenaiApiKey: payload.has_openai_api_key,
    openaiApiKeyMasked: payload.openai_api_key_masked,
    openaiApiKey: "",
  };
}

export async function loadFasterWhisperModels() {
  return fetchJson("/api/asr/faster-whisper/models");
}

export async function downloadFasterWhisperModel(modelId) {
  return fetchJson(`/api/asr/faster-whisper/models/${encodeURIComponent(modelId)}/download`, {
    method: "POST",
  });
}

export async function cancelFasterWhisperModelDownload(modelId) {
  return fetchJson(`/api/asr/faster-whisper/models/${encodeURIComponent(modelId)}/download/cancel`, {
    method: "POST",
  });
}

export function subscribeFasterWhisperModelDownloadProgress(modelId, listener) {
  const eventSource = new EventSource(
    `/api/asr/faster-whisper/models/${encodeURIComponent(modelId)}/download/progress`,
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
      error: "模型下载进度连接已中断",
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

export function subscribeVideoGenerationProgress(seriesId, videoId, listener) {
  const eventSource = new EventSource(
    `/api/videos/${encodeURIComponent(seriesId)}/${encodeURIComponent(videoId)}/generate/progress`,
  );
  let terminal = false;

  eventSource.onmessage = (event) => {
    const snapshot = parseProgressMessage(event.data);
    listener(snapshot);
    if (snapshot.status === "completed" || snapshot.status === "failed") {
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

export function getVideoPreviewUrl(seriesId, videoId) {
  return `/api/videos/${encodeURIComponent(seriesId)}/${encodeURIComponent(videoId)}/preview`;
}

async function fetchJson(path, init) {
  const response = await fetch(path, init);
  if (!response.ok) {
    let detail = "";
    try {
      const payload = await response.json();
      detail = typeof payload.detail === "string" ? payload.detail : "";
    } catch {
      detail = "";
    }
    throw new Error(detail ? `${response.status} ${detail}` : `加载失败：${path}`);
  }
  return response.json();
}

function parseProgressMessage(rawValue) {
  const payload = JSON.parse(rawValue);
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
  };
}
