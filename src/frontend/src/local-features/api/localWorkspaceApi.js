import { fetchJson, toProgressSnapshot, toProviderUsage } from "../../features/workspace/model/workspaceApi";

export async function loadApplicationUpdateStatus() {
  const payload = await fetchJson("/api/application-update");
  return {
    installationKind: payload.installation_kind,
    currentVersion: payload.current_version,
    variant: payload.variant,
    updateAvailable: Boolean(payload.update_available),
    canApply: Boolean(payload.can_apply),
    requiresFullPackage: Boolean(payload.requires_full_package),
    latestVersion: payload.latest_version,
    fullPackageUrl: payload.full_package_url,
    message: typeof payload.message === "string" ? payload.message : "",
  };
}

export async function scheduleApplicationUpdate() {
  const payload = await fetchJson("/api/application-update/apply", { method: "POST" });
  return { targetVersion: payload.target_version, restartAfterSeconds: payload.restart_after_seconds };
}

export async function loadWorkspaceSettings() {
  return toWorkspaceSettings(await fetchJson("/api/settings"));
}

export async function loadProviderSettings() {
  const payload = await fetchJson("/api/provider-settings");
  return toProviderSettings(payload);
}

export async function loadProviderUsage(range = "7d") {
  return toProviderUsage(await fetchJson(`/api/provider-settings/usage?range=${encodeURIComponent(range)}`));
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
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      theme: settings.theme,
      show_takeaways: settings.showTakeaways,
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
      chapter_visual_mode: settings.chapterVisualMode,
      max_visual_input_images: settings.maxVisualInputImages,
      note_visual_mode: settings.noteVisualMode,
      ai_summary_multimodal_enabled: settings.aiSummaryMultimodalEnabled,
      mindmap_visual_input: settings.mindmapVisualInput,
      cards_visual_input: settings.cardsVisualInput,
      note_max_images: settings.noteMaxImages,
      auto_generate_artifacts: settings.autoGenerateArtifacts,
      chaoxing_request_delay_seconds: settings.chaoxingRequestDelaySeconds,
      chaoxing_init_course_delay_seconds: settings.chaoxingInitCourseDelaySeconds,
    }),
  });
  return toWorkspaceSettings(payload);
}

export async function updateProviderSettings(settings) {
  const payload = await fetchJson("/api/provider-settings", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      llm_provider: settings.llmProvider,
      openai_base_url: settings.openaiBaseUrl,
      openai_model: settings.openaiModel,
      openai_api_key: settings.openaiApiKey.trim() ? settings.openaiApiKey : null,
      hf_endpoint: settings.hfEndpoint,
    }),
  });
  return toProviderSettings(payload);
}

export function testProviderSettings(settings) {
  return withTimeout(45000, (signal) => fetchJson("/api/provider-settings/test", {
    method: "POST", signal, headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ llm_provider: settings.llmProvider, openai_base_url: settings.openaiBaseUrl, openai_model: settings.openaiModel, openai_api_key: settings.openaiApiKey.trim() ? settings.openaiApiKey : null, hf_endpoint: settings.hfEndpoint }),
  }));
}

export function discoverProviderModels(settings) {
  return withTimeout(20000, async (signal) => {
    const payload = await fetchJson("/api/provider-settings/models", {
      method: "POST", signal, headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ llm_provider: settings.llmProvider, openai_base_url: settings.openaiBaseUrl, openai_api_key: settings.openaiApiKey.trim() ? settings.openaiApiKey : null }),
    });
    if (!Array.isArray(payload.models)) throw new Error("模型探测响应无效");
    return payload.models.filter((model) => typeof model === "string" && model.trim());
  });
}

export function testAsrSettings(settings) {
  return withTimeout(10000, (signal) => fetchJson("/api/settings/asr/test", {
    method: "POST", signal, headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ asr_provider: settings.asrProvider, asr_cloud_model: settings.asrCloudModel, asr_base_url: settings.asrBaseUrl, asr_api_key: settings.asrApiKey.trim() ? settings.asrApiKey : null }),
  }));
}

export const loadFasterWhisperModels = (provider = "faster_whisper") => fetchJson(`/api/asr/${encodeURIComponent(provider)}/models`);
export const loadRagModels = () => fetchJson("/api/rag/models");
export const downloadRagModel = async (modelKey) => toDurableModelJob(await fetchJson(`/api/rag/models/${encodeURIComponent(modelKey)}/download`, { method: "POST" }));
export const cancelRagModelDownload = (modelKey) => fetchJson(`/api/rag/models/${encodeURIComponent(modelKey)}/download/cancel`, { method: "POST" });
export const downloadFasterWhisperModel = async (provider, modelId) => toDurableModelJob(await fetchJson(`/api/asr/${encodeURIComponent(provider)}/models/${encodeURIComponent(modelId)}/download`, { method: "POST" }));
export const cancelFasterWhisperModelDownload = (provider, modelId) => fetchJson(`/api/asr/${encodeURIComponent(provider)}/models/${encodeURIComponent(modelId)}/download/cancel`, { method: "POST" });
export const subscribeRagModelDownloadProgress = (modelKey, listener) => subscribeProgress(`/api/rag/models/${encodeURIComponent(modelKey)}/download/progress`, listener, "RAG 模型下载进度连接已中断");
export const subscribeFasterWhisperModelDownloadProgress = (provider, modelId, listener) => subscribeProgress(`/api/asr/${encodeURIComponent(provider)}/models/${encodeURIComponent(modelId)}/download/progress`, listener, "模型下载进度连接已中断");

export async function selectLocalMedia() {
  const payload = await fetchJson("/api/import/local/select", { method: "POST" });
  return { sourcePaths: Array.isArray(payload.source_paths) ? payload.source_paths.filter((path) => typeof path === "string" && path) : [], hardlinkAvailable: payload.hardlink_available !== false };
}

export const relinkExternalVideo = (seriesId, videoId) => fetchJson(`/api/videos/${encodeURIComponent(seriesId)}/${encodeURIComponent(videoId)}/relink`, { method: "POST" });
export const importLocalSeries = (seriesTitle, sourcePaths, storageMode) => fetchJson("/api/import/local/series/from-paths", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ series_title: seriesTitle, source_paths: sourcePaths, storage_mode: storageMode }) });
export const importLocalPlaygroundVideos = (sourcePaths) => fetchJson("/api/import/local/playground/from-paths", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ source_paths: sourcePaths }) });
export const importLocalSeriesVideos = (seriesId, sourcePaths) => fetchJson(`/api/import/local/series/${encodeURIComponent(seriesId)}/from-paths`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ source_paths: sourcePaths }) });

export async function initExternalCookie(provider, options = {}) {
  const payload = await fetchJson(`/api/linked/${encodeURIComponent(provider)}/cookie/init`, { method: "POST", signal: options.signal });
  return { configured: payload.configured === true };
}

export async function loadChaoxingStatus() { return { initialized: (await fetchJson("/api/linked/chaoxing/status")).initialized === true }; }
export async function initChaoxing(options = {}) { return { initialized: (await fetchJson("/api/linked/chaoxing/init", { method: "POST", signal: options.signal })).initialized === true }; }
export const cancelChaoxingInit = () => fetchJson("/api/linked/chaoxing/init/cancel", { method: "POST" });
export async function loadChaoxingCourses() {
  const payload = await fetchJson("/api/linked/chaoxing/courses");
  return Array.isArray(payload) ? payload.map((course) => ({ courseKey: typeof course.course_key === "string" ? course.course_key : "", title: typeof course.title === "string" ? course.title : "", teacher: typeof course.teacher === "string" ? course.teacher : "", openTime: typeof course.open_time === "string" ? course.open_time : "" })).filter((course) => course.courseKey && course.title) : [];
}
export async function importChaoxingCourse(courseKey) {
  const payload = await fetchJson("/api/linked/chaoxing/import/course", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ course_key: courseKey }) });
  const jobId = typeof payload.job_id === "string" ? payload.job_id : "";
  if (!jobId) throw new Error("超星导入任务未返回 job_id。");
  return { jobId, seriesId: typeof payload.series_id === "string" ? payload.series_id : "" };
}
export const cancelChaoxingImport = (jobId) => fetchJson(`/api/linked/chaoxing/import/course/${encodeURIComponent(jobId)}/cancel`, { method: "POST" });

function toWorkspaceSettings(payload) {
  return { theme: payload.theme, showTakeaways: payload.show_takeaways, transcriptEnhancementEnabled: payload.transcript_enhancement_enabled, asrProvider: payload.asr_provider, asrModelQuality: payload.asr_model_quality, transcriptionMode: payload.transcription_mode, asrCloudModel: payload.asr_cloud_model, asrBaseUrl: payload.asr_base_url, hasAsrApiKey: payload.has_asr_api_key, asrApiKeyMasked: payload.asr_api_key_masked, asrApiKey: "", ragEmbeddingDevice: payload.rag_embedding_device, ragMaxHits: payload.rag_max_hits, ragRerankEnabled: payload.rag_rerank_enabled, webSearchEnabled: payload.web_search_enabled, windowTokens: payload.window_tokens, answerDetailLevel: payload.answer_detail_level, reasoningEffort: payload.reasoning_effort, talkCustomPrompt: payload.talk_custom_prompt, videoGenerationConcurrency: payload.video_generation_concurrency, chapterVisualMode: payload.chapter_visual_mode, maxVisualInputImages: payload.max_visual_input_images, noteVisualMode: payload.note_visual_mode, aiSummaryMultimodalEnabled: payload.ai_summary_multimodal_enabled === true, mindmapVisualInput: payload.mindmap_visual_input, cardsVisualInput: payload.cards_visual_input, noteMaxImages: payload.note_max_images, autoGenerateArtifacts: Array.isArray(payload.auto_generate_artifacts) ? payload.auto_generate_artifacts : [], chaoxingRequestDelaySeconds: payload.chaoxing_request_delay_seconds, chaoxingInitCourseDelaySeconds: payload.chaoxing_init_course_delay_seconds, runtimeCapabilities: payload.runtime_capabilities };
}

function toDurableModelJob(payload) {
  const jobId = typeof payload?.job_id === "string" ? payload.job_id.trim() : "";
  if (!jobId) throw new Error("模型准备任务未返回 job_id。");
  return { jobId, status: typeof payload.status === "string" ? payload.status : "queued" };
}

function toProviderSettings(payload) { return { llmProvider: payload.llm_provider, openaiBaseUrl: payload.openai_base_url, openaiModel: payload.openai_model, hasOpenaiApiKey: payload.has_openai_api_key, openaiApiKeyMasked: payload.openai_api_key_masked, hfEndpoint: payload.hf_endpoint, openaiApiKey: "" }; }
function subscribeProgress(path, listener, connectionErrorMessage) {
  const eventSource = new EventSource(path); let terminal = false;
  eventSource.onmessage = (event) => { const snapshot = toProgressSnapshot(JSON.parse(event.data)); listener(snapshot); if (["completed", "failed", "cancelled"].includes(snapshot.status)) { terminal = true; eventSource.close(); } };
  eventSource.onerror = () => { if (!terminal) listener({ status: "failed", stage: "failed", progress: null, detail: null, error: connectionErrorMessage }); eventSource.close(); };
  return () => { terminal = true; eventSource.close(); };
}
async function withTimeout(milliseconds, operation) { const controller = new AbortController(); const timeoutId = window.setTimeout(() => controller.abort(), milliseconds); try { return await operation(controller.signal); } finally { window.clearTimeout(timeoutId); } }
