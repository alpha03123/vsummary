import { toWorkspaceLibrary, toWorkspaceMindmap, toWorkspaceSummary, toWorkspaceTools } from "./workspaceViewModel";

export async function loadWorkspaceLibrary() {
  return toWorkspaceLibrary(await fetchJson("/api/videos"));
}

export async function loadWorkspaceSettings() {
  const payload = await fetchJson("/api/settings");
  return {
    theme: payload.theme,
    showTakeaways: payload.show_takeaways,
    aiTranscriptEnhancement: payload.ai_transcript_enhancement,
    asrModelQuality: payload.asr_model_quality,
    transcriptionMode: payload.transcription_mode,
    llmProvider: payload.llm_provider,
    openaiBaseUrl: payload.openai_base_url,
    openaiModel: payload.openai_model,
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
      ai_transcript_enhancement: settings.aiTranscriptEnhancement,
      asr_model_quality: settings.asrModelQuality,
      transcription_mode: settings.transcriptionMode,
      llm_provider: settings.llmProvider,
      openai_base_url: settings.openaiBaseUrl,
      openai_model: settings.openaiModel,
    }),
  });
  return {
    theme: payload.theme,
    showTakeaways: payload.show_takeaways,
    aiTranscriptEnhancement: payload.ai_transcript_enhancement,
    asrModelQuality: payload.asr_model_quality,
    transcriptionMode: payload.transcription_mode,
    llmProvider: payload.llm_provider,
    openaiBaseUrl: payload.openai_base_url,
    openaiModel: payload.openai_model,
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
  };
}
