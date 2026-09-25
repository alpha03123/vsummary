import {
  cancelSeriesSummaries,
  cancelVideoDownload,
  cancelVideoSummary,
  createVideoNote,
  deleteSeries,
  deleteVideoNote,
  deleteVideoSource,
  renameSeries,
  renameVideoSource,
  generateSeriesMindmap,
  generateVideoKnowledgeCards,
  generateVideoAiSummary,
  generateVideoMindmap,
  generateSeriesSummaries,
  generateVideoSummary,
  processAgentVideo,
  restoreAutomaticTranscriptAndGenerateVideoSummary,
  loadWorkspaceLibrary,
  loadVideoSummary,
  loadVideoNotes,
  loadVideoKnowledgeCards,
  loadVideoMindmap,
  loadVideoTools,
  loadVideoSummaryMarkdown,
  loadVideoTranscriptMarkdown,
  resolveLinkedSeries,
  resolveLinkedVideo,
  resolveBilibiliInboxVideo,
  startVideoDownload,
  subscribeDurableJobProgress,
  updateVideoNote,
  updateVideoAiSummary,
  updateVideoSummary,
  updateVideoTranscript,
  uploadSrtAndGenerateVideoSummary,
} from "./workspaceApi";
import * as localWorkspaceApi from "../../../local-features/api/localWorkspaceApi";
import { isPlaygroundSeries } from "./workspaceControllerConstants";
import { buildVideoKey } from "./workspaceControllerUtils";
import { buildSeriesGenerationTaskKey, buildVideoGenerationTaskKey, getGenerationTaskForSelection } from "./workspaceState";

const activeSeriesCancellationRef = { current: null };
const activeVideoGenerationKeys = new Set();
let nextSeriesRunSequence = 0;

function createSeriesRunId(seriesId) {
  nextSeriesRunSequence += 1;
  return `${seriesId}:${nextSeriesRunSequence}`;
}

export function getPendingVideosForSeriesGeneration(library, seriesId, processingMode = "summary") {
  const series = library?.series?.find((item) => item.id === seriesId);
  return series?.videos?.filter((video) => (
    processingMode === "transcript" ? !video.hasTranscript : !video.processed
  ) && video.status !== "source_missing") ?? [];
}

function isLinkedVideo(video) {
  return video?.isLinked === true || video?.status === "linked";
}

function isGenerationCancelledError(error) {
  if (!(error instanceof Error)) {
    return false;
  }
  return error.message.includes("generation cancelled");
}

function isDownloadCancelledError(error) {
  if (!(error instanceof Error)) {
    return false;
  }
  return error.message.includes("下载已取消") || error.message.includes("任务已取消");
}

function errorMessage(error, fallback) {
  return error instanceof Error ? error.message : fallback;
}

function normalizeSkippedVideoError(item) {
  if (!item || typeof item !== "object") {
    return null;
  }
  const videoId = typeof item.video_id === "string" ? item.video_id : typeof item.videoId === "string" ? item.videoId : "";
  const title = typeof item.title === "string" ? item.title : "";
  const error = typeof item.error === "string" ? item.error : "";
  if (!videoId && !title && !error) {
    return null;
  }
  return { videoId, title, error };
}

function mergeSkippedVideoErrors(...groups) {
  const merged = new Map();
  for (const group of groups) {
    if (!Array.isArray(group)) {
      continue;
    }
    for (const item of group) {
      const normalized = normalizeSkippedVideoError(item);
      if (normalized == null) {
        continue;
      }
      const key = normalized.videoId || normalized.title || normalized.error;
      const existing = merged.get(key);
      if (existing == null) {
        merged.set(key, normalized);
        continue;
      }
      const errors = [existing.error, normalized.error].filter(Boolean);
      merged.set(key, {
        ...existing,
        ...normalized,
        error: Array.from(new Set(errors)).join("；"),
      });
    }
  }
  return Array.from(merged.values());
}

function buildSeriesCompletionDetail(result, skippedVideoErrors) {
  const completedCount = Array.isArray(result?.completed_videos) ? result.completed_videos.length : 0;
  const skippedCount = Math.max(
    Array.isArray(result?.skipped_videos) ? result.skipped_videos.length : 0,
    skippedVideoErrors.length,
  );
  if (skippedCount <= 0) {
    return `系列处理完成：成功 ${completedCount} 个，跳过 0 个。`;
  }
  const details = skippedVideoErrors
    .map((item, index) => {
      const title = item.title || item.videoId || `视频 ${index + 1}`;
      const reason = item.error || "未知错误";
      return `${index + 1}. ${title}：${reason}`;
    })
    .join("\n");
  return `系列处理完成：成功 ${completedCount} 个，跳过 ${skippedCount} 个。${details ? `\n跳过的视频：\n${details}` : ""}`;
}

export function createWorkspaceContentActions({ state, dispatch, selectedVideo }) {
  async function reloadWorkspaceLibrary() {
    const library = await loadWorkspaceLibrary();
    dispatch({ type: "workspace_loaded", library });
    return library;
  }

  async function reloadWorkspaceLibraryAfterSeriesStop() {
    try {
      return await reloadWorkspaceLibrary();
    } catch (error) {
      dispatch({
        type: "load_failed",
        message: error instanceof Error ? error.message : "刷新系列状态失败",
      });
      return null;
    }
  }

  async function onGenerateKnowledgeCards() {
    if (!state.selectedSeriesId || !state.selectedVideoId) {
      return;
    }

    dispatch({ type: "knowledge_cards_generation_started" });
    try {
      const seriesId = state.selectedSeriesId;
      const videoId = state.selectedVideoId;
      const submitted = await generateVideoKnowledgeCards(seriesId, videoId);
      const unsubscribe = subscribeDurableJobProgress(submitted.jobId, async (snapshot) => {
        if (snapshot.status === "completed") {
          unsubscribe();
          const cards = await loadVideoKnowledgeCards(seriesId, videoId);
          dispatch({
            type: "knowledge_cards_loaded",
            cards,
            feedbackTone: "success",
            feedbackMessage: Array.isArray(cards?.cards) && cards.cards.length
              ? `已生成 ${cards.cards.length} 张知识卡片`
              : "知识卡片已生成，但这次没有抽取出稳定卡片",
          });
        }
        if (snapshot.status === "failed" || snapshot.status === "cancelled") {
          unsubscribe();
          dispatch({ type: "load_failed", message: snapshot.error || snapshot.detail || "知识卡片生成失败" });
        }
      });
    } catch (error) {
      dispatch({
        type: "load_failed",
        message: error instanceof Error ? error.message : "知识卡片生成失败",
      });
    }
  }

  function onClearKnowledgeCardsFeedback() {
    dispatch({ type: "knowledge_cards_feedback_cleared" });
  }

  async function onGenerateVideo() {
    if (!state.selectedSeriesId || !state.selectedVideoId) {
      return;
    }

    const seriesId = state.selectedSeriesId;
    const videoId = state.selectedVideoId;
    const processingMode = state.processingMode;
    const videoKey = buildVideoKey(seriesId, videoId);
    const taskKey = buildVideoGenerationTaskKey(seriesId, videoId);
    if (activeVideoGenerationKeys.has(taskKey)) {
      return;
    }
    activeVideoGenerationKeys.add(taskKey);
    dispatch({ type: "generation_started", videoKey, seriesId, videoId });

    try {
      const submission = await generateVideoSummary(seriesId, videoId, {
        transcriptEnhancementEnabled: state.ui.transcriptEnhancementEnabled,
        processingMode,
      });
      dispatch({
        type: "generation_status_loaded",
        taskKey,
        mode: "video",
        seriesId,
        videoId,
        jobId: submission.jobId,
        snapshot: {
          status: submission.status,
          stage: "queued",
          progress: 0,
          detail: "任务已进入队列",
          error: null,
        },
        subscriptionActive: true,
      });
    } catch (error) {
      if (isGenerationCancelledError(error)) {
        dispatch({
          type: "generation_cancelled",
          taskKey,
          mode: "video",
          seriesId,
          videoId,
          snapshot: {
            status: "cancelled",
            stage: "cancelled",
            progress: null,
            detail: "任务已取消",
            error: null,
          },
        });
        return;
      }
      const message = error instanceof Error ? error.message : "生成失败";
      dispatch({ type: "load_failed", message });
      dispatch({
        type: "generation_status_loaded",
        taskKey,
        mode: "video",
        seriesId,
        videoId,
        snapshot: {
          status: "failed",
          stage: "failed",
          progress: null,
          detail: null,
          error: message,
        },
        subscriptionActive: false,
      });
    } finally {
      activeVideoGenerationKeys.delete(taskKey);
    }
  }

  async function onProcessLinkedVideo() {
    if (!state.selectedSeriesId || !state.selectedVideoId || !selectedVideo) {
      return;
    }
    if (!selectedVideo.isLinked && selectedVideo.status !== "linked") {
      await onGenerateVideo();
      return;
    }

    const seriesId = state.selectedSeriesId;
    const videoId = state.selectedVideoId;
    const processingMode = state.processingMode;
    try {
      const submitted = await processAgentVideo(seriesId, videoId, { processingMode });
      dispatch({
        type: "generation_status_loaded",
        taskKey: buildVideoGenerationTaskKey(seriesId, videoId),
        mode: "video",
        seriesId,
        videoId,
        snapshot: {
          status: "queued",
          stage: "queued",
          progress: 0,
          detail: "任务已进入队列，等待开始处理",
          error: null,
        },
        subscriptionActive: true,
      });
      const unsubscribe = subscribeDurableJobProgress(submitted.jobId, async (snapshot) => {
        dispatch({
          type: "generation_status_loaded",
          taskKey: buildVideoGenerationTaskKey(seriesId, videoId),
          mode: "video",
          seriesId,
          videoId,
          jobId: submitted.jobId,
          snapshot,
          subscriptionActive: snapshot.status === "running" || snapshot.status === "queued",
        });
        if (snapshot.status === "completed") {
          unsubscribe();
          await reloadWorkspaceLibrary();
        }
        if (snapshot.status === "failed" || snapshot.status === "cancelled") {
          unsubscribe();
        }
      });
    } catch (error) {
      dispatch({ type: "load_failed", message: error instanceof Error ? error.message : "提交视频处理失败" });
    }
  }

  async function onGenerateSeries() {
    if (!state.selectedSeriesId) {
      return;
    }

    const seriesId = state.selectedSeriesId;
    const processingMode = state.processingMode;
    const pendingVideos = getPendingVideosForSeriesGeneration(state.library, seriesId, processingMode);
    if (!pendingVideos.length) {
      return;
    }
    const currentTask = getGenerationTaskForSelection(state);
    if (currentTask?.mode === "series" && currentTask.snapshot?.status === "running") {
      return;
    }

    const runId = createSeriesRunId(seriesId);
    dispatch({ type: "series_generation_queue_started", seriesId, runId, total: pendingVideos.length });
    dispatch({ type: "series_generation_started", seriesId, runId });
    const cancellation = { requested: false, runId };
    activeSeriesCancellationRef.current = cancellation;
    try {
      const submitted = await generateSeriesSummaries(seriesId, {
        transcriptEnhancementEnabled: state.ui.transcriptEnhancementEnabled,
        runId,
        processingMode,
      });
      dispatch({
        taskKey: buildSeriesGenerationTaskKey(seriesId),
        type: "generation_status_loaded",
        mode: "series",
        seriesId,
        runId,
        videoId: null,
        snapshot: {
          status: submitted.status,
          stage: "queued",
          progress: 0,
          detail: "系列任务已进入队列，正在创建视频子任务",
          error: null,
        },
        subscriptionActive: true,
      });
      const unsubscribe = subscribeDurableJobProgress(submitted.jobId, async (snapshot) => {
        dispatch({
          type: "generation_status_loaded",
          taskKey: buildSeriesGenerationTaskKey(seriesId),
          mode: "series",
          seriesId,
          runId,
          videoId: null,
          snapshot,
          subscriptionActive: snapshot.status === "queued" || snapshot.status === "running",
        });
        if (snapshot.status === "completed") {
          unsubscribe();
          const library = await reloadWorkspaceLibrary();
          dispatch({ type: "series_generation_succeeded", taskKey: buildSeriesGenerationTaskKey(seriesId), seriesId, runId, library });
          dispatch({ type: "series_generation_queue_finished", seriesId, runId, status: "completed", detail: "视频子任务已进入队列" });
          if (activeSeriesCancellationRef.current === cancellation) activeSeriesCancellationRef.current = null;
        }
        if (snapshot.status === "failed" || snapshot.status === "cancelled") {
          unsubscribe();
          dispatch({ type: "series_generation_queue_finished", seriesId, runId, status: snapshot.status });
          if (activeSeriesCancellationRef.current === cancellation) activeSeriesCancellationRef.current = null;
        }
      });
    } catch (error) {
      const message = error instanceof Error ? error.message : "生成失败";
      dispatch({ type: "load_failed", message });
      dispatch({
        type: "generation_status_loaded",
        taskKey: buildSeriesGenerationTaskKey(seriesId),
        mode: "series",
        seriesId,
        runId,
        videoId: null,
        snapshot: {
          status: "failed",
          stage: "failed",
          progress: null,
          detail: null,
          error: message,
        },
        subscriptionActive: false,
      });
      dispatch({ type: "series_generation_queue_finished", seriesId, runId, status: "failed" });
      if (activeSeriesCancellationRef.current === cancellation) {
        activeSeriesCancellationRef.current = null;
      }
    }
  }

  async function downloadLinkedVideo(seriesId, videoId, options = {}) {
    dispatch({ type: "video_download_started", seriesId, videoId });
    const submitted = await startVideoDownload(seriesId, videoId);
    await new Promise((resolve, reject) => {
      const cancelTimer = options.cancelCheck
        ? window.setInterval(() => {
            if (options.cancelCheck()) {
              cleanup();
              dispatch({ type: "video_download_cancelled", seriesId, videoId });
              reject(new Error("任务已取消"));
            }
          }, 250)
        : null;
      let unsubscribe = null;
      function cleanup() {
        unsubscribe?.();
        if (cancelTimer != null) {
          window.clearInterval(cancelTimer);
        }
      }
      unsubscribe = subscribeDurableJobProgress(submitted.jobId, async (snapshot) => {
        if (snapshot.status === "running" || snapshot.status === "completed") {
          dispatch({ type: "video_download_progress_updated", seriesId, videoId, progress: snapshot.progress });
        }
        if (snapshot.status === "completed") {
          cleanup();
          resolve();
        }
        if (snapshot.status === "cancelled") {
          cleanup();
          dispatch({ type: "video_download_cancelled", seriesId, videoId });
          reject(new Error("任务已取消"));
        }
        if (snapshot.status === "failed") {
          cleanup();
          const message = snapshot.error || snapshot.detail || "视频下载失败";
          dispatch({ type: "video_download_failed", seriesId, videoId, error: message });
          reject(new Error(message));
        }
      });
    });
  }

  async function onCancelGeneration() {
    try {
      if (
        state.seriesGenerationQueue?.seriesId === state.selectedSeriesId &&
        (state.seriesGenerationQueue.status === "running" || state.seriesGenerationQueue.status === "cancelling") &&
        state.selectedSeriesId
      ) {
        if (activeSeriesCancellationRef.current != null) {
          activeSeriesCancellationRef.current.requested = true;
        }
        dispatch({
          type: "series_generation_queue_cancelling",
          seriesId: state.selectedSeriesId,
          runId: state.seriesGenerationQueue.runId,
        });
        await cancelSeriesWork({
          seriesId: state.selectedSeriesId,
          runId: state.seriesGenerationQueue.runId,
        });
        return;
      }
      if (
        state.selectedContextType === "series" &&
        state.selectedSeriesId
      ) {
        if (activeSeriesCancellationRef.current != null) {
          activeSeriesCancellationRef.current.requested = true;
        }
        dispatch({
          type: "series_generation_queue_cancelling",
          seriesId: state.selectedSeriesId,
          runId: state.seriesGenerationQueue?.runId,
        });
        await cancelSeriesWork({
          seriesId: state.selectedSeriesId,
          runId: state.seriesGenerationQueue?.runId,
        });
        return;
      }
      const currentTask = getGenerationTaskForSelection(state);
      if (currentTask?.mode === "video" && state.selectedSeriesId && state.selectedVideoId) {
        const seriesId = state.selectedSeriesId;
        const videoId = state.selectedVideoId;
        const taskKey = buildVideoGenerationTaskKey(seriesId, videoId);
        dispatch({ type: "video_generation_cancelling", seriesId, videoId });
        await cancelVideoSummary(seriesId, videoId);
        dispatch({
          type: "generation_cancelled",
          taskKey,
          mode: "video",
          seriesId,
          videoId,
          snapshot: {
            ...(currentTask.snapshot ?? {}),
            status: "cancelled",
            stage: "cancelled",
            progress: null,
            detail: "任务已取消",
            error: null,
          },
        });
      }
    } catch (error) {
      dispatch({
        type: "load_failed",
        message: error instanceof Error ? error.message : "取消生成失败",
      });
    }
  }

  async function cancelSeriesWork({ seriesId, runId }) {
    await cancelSeriesSummaries(seriesId, { runId });
    const linkedVideoIds = new Set(
      getPendingVideosForSeriesGeneration(state.library, seriesId, state.processingMode)
        .filter(isLinkedVideo)
        .map((video) => video.id),
    );
    if (state.seriesGenerationQueue?.seriesId === seriesId && state.seriesGenerationQueue.downloadVideoId) {
      linkedVideoIds.add(state.seriesGenerationQueue.downloadVideoId);
    }
    await Promise.allSettled(Array.from(linkedVideoIds, (videoId) => cancelVideoDownload(seriesId, videoId)));
    await reloadWorkspaceLibraryAfterSeriesStop();
    dispatch({
      type: "generation_status_loaded",
      taskKey: buildSeriesGenerationTaskKey(seriesId),
      mode: "series",
      seriesId,
      runId,
      videoId: null,
      snapshot: {
        status: "cancelled",
        stage: "cancelled",
        progress: null,
        detail: "任务已取消",
        error: null,
      },
      subscriptionActive: false,
    });
    dispatch({ type: "series_generation_queue_finished", seriesId, runId, status: "cancelled" });
  }

  async function onGenerateMindmap(maxDepth = null) {
    if (!state.selectedSeriesId || !state.selectedVideoId) {
      return;
    }

    const seriesId = state.selectedSeriesId;
    const videoId = state.selectedVideoId;
    const videoKey = buildVideoKey(seriesId, videoId);
    dispatch({ type: "mindmap_generation_started", videoKey });

    try {
      const submitted = await generateVideoMindmap(seriesId, videoId, maxDepth);
      const unsubscribe = subscribeDurableJobProgress(submitted.jobId, async (snapshot) => {
        dispatch({ type: "mindmap_generation_progress_updated", snapshot });
        if (snapshot.status === "completed") {
          unsubscribe();
          const mindmap = await loadVideoMindmap(seriesId, videoId);
          dispatch({ type: "mindmap_generation_progress_cleared" });
          dispatch({ type: "mindmap_generation_succeeded", mindmap });
        }
        if (snapshot.status === "failed" || snapshot.status === "cancelled") {
          unsubscribe();
          dispatch({ type: "mindmap_generation_progress_cleared" });
          dispatch({ type: "load_failed", message: snapshot.error || snapshot.detail || "生成失败" });
        }
      });
    } catch (error) {
      dispatch({ type: "mindmap_generation_progress_cleared" });
      dispatch({
        type: "load_failed",
        message: error instanceof Error ? error.message : "生成失败",
      });
    }
  }

  async function onGenerateSeriesMindmap(maxDepth = null) {
    if (!state.selectedSeriesId) return;

    const seriesId = state.selectedSeriesId;
    dispatch({ type: "series_mindmap_generation_started" });

    try {
      const submitted = await generateSeriesMindmap(seriesId, maxDepth);
      const unsubscribe = subscribeDurableJobProgress(submitted.jobId, async (snapshot) => {
        dispatch({ type: "mindmap_generation_progress_updated", snapshot });
        if (snapshot.status === "completed") {
          unsubscribe();
          const mindmap = await loadSeriesMindmap(seriesId);
          dispatch({ type: "mindmap_generation_progress_cleared" });
          dispatch({ type: "series_mindmap_generation_succeeded", mindmap });
        }
        if (snapshot.status === "failed" || snapshot.status === "cancelled") {
          unsubscribe();
          dispatch({ type: "mindmap_generation_progress_cleared" });
          dispatch({ type: "load_failed", message: snapshot.error || snapshot.detail || "系列导图生成失败" });
        }
      });
    } catch (error) {
      dispatch({ type: "mindmap_generation_progress_cleared" });
      dispatch({
        type: "load_failed",
        message: error instanceof Error ? error.message : "系列导图生成失败",
      });
    }
  }
  async function onCreateNote(note) {
    if (!state.selectedSeriesId || !state.selectedVideoId || !selectedVideo) {
      return;
    }

    dispatch({ type: "note_save_started" });
    try {
      const createdNote = await createVideoNote(state.selectedSeriesId, state.selectedVideoId, {
        title: note.title,
        content: note.content,
        source: note.source ?? "manual",
      });
      dispatch({
        type: "note_created",
        seriesId: state.selectedSeriesId,
        videoId: state.selectedVideoId,
        videoTitle: selectedVideo.title,
        note: createdNote,
      });
    } catch (error) {
      dispatch({
        type: "load_failed",
        message: error instanceof Error ? error.message : "笔记保存失败",
      });
    }
  }

  async function onGenerateAiSummary(template = "general") {
    if (!state.selectedSeriesId || !state.selectedVideoId) return;
    dispatch({ type: "ai_summary_generation_started" });
    try {
      const seriesId = state.selectedSeriesId;
      const videoId = state.selectedVideoId;
      const submitted = await generateVideoAiSummary(seriesId, videoId, template);
      const unsubscribe = subscribeDurableJobProgress(submitted.jobId, async (snapshot) => {
        if (snapshot.status === "completed") {
          unsubscribe();
          const [summary, tools] = await Promise.all([loadVideoAiSummary(seriesId, videoId), loadVideoTools(seriesId, videoId)]);
          dispatch({ type: "ai_summary_loaded", summary });
          dispatch({ type: "tools_loaded", tools });
        }
        if (snapshot.status === "failed" || snapshot.status === "cancelled") {
          unsubscribe();
          dispatch({ type: "ai_summary_generation_failed", message: snapshot.error || snapshot.detail || "AI 概括生成失败" });
        }
      });
    } catch (error) {
      dispatch({ type: "ai_summary_generation_failed", message: error instanceof Error ? error.message : "AI 概括生成失败" });
    }
  }

  async function onUpdateAiSummary(summary) {
    if (!state.selectedSeriesId || !state.selectedVideoId) return;
    dispatch({ type: "ai_summary_loading_started" });
    try {
      const updated = await updateVideoAiSummary(state.selectedSeriesId, state.selectedVideoId, summary);
      dispatch({ type: "ai_summary_loaded", summary: updated });
    } catch (error) {
      dispatch({ type: "ai_summary_generation_failed", message: error instanceof Error ? error.message : "AI 概括更新失败" });
    }
  }

  async function onUpdateNote(noteId, note) {
    if (!state.selectedSeriesId || !state.selectedVideoId) {
      return;
    }

    dispatch({ type: "note_save_started" });
    try {
      const updatedNote = await updateVideoNote(state.selectedSeriesId, state.selectedVideoId, noteId, {
        title: note.title,
        content: note.content,
      });
      dispatch({ type: "note_updated", note: updatedNote });
    } catch (error) {
      dispatch({
        type: "load_failed",
        message: error instanceof Error ? error.message : "笔记更新失败",
      });
    }
  }

  async function onDeleteNote(noteId) {
    if (!state.selectedSeriesId || !state.selectedVideoId) {
      return;
    }

    dispatch({ type: "note_save_started" });
    try {
      await deleteVideoNote(state.selectedSeriesId, state.selectedVideoId, noteId);
      dispatch({ type: "note_deleted", noteId });
    } catch (error) {
      dispatch({
        type: "load_failed",
        message: error instanceof Error ? error.message : "笔记删除失败",
      });
    }
  }

  async function onLoadTranscriptMarkdown() {
    if (!state.selectedSeriesId || !state.selectedVideoId) {
      throw new Error("请先选择视频。");
    }
    return loadVideoTranscriptMarkdown(state.selectedSeriesId, state.selectedVideoId);
  }

  async function onLoadSummaryMarkdown() {
    if (!state.selectedSeriesId || !state.selectedVideoId) {
      throw new Error("请先选择视频。");
    }
    return loadVideoSummaryMarkdown(state.selectedSeriesId, state.selectedVideoId);
  }

  async function onUpdateSummary(summary) {
    if (!state.selectedSeriesId || !state.selectedVideoId) {
      throw new Error("请先选择视频。");
    }
    const updated = await updateVideoSummary(state.selectedSeriesId, state.selectedVideoId, summary);
    await reloadWorkspaceLibrary();
    dispatch({ type: "summary_loaded", summary: updated });
    return updated;
  }

  async function onUpdateTranscript(markdown) {
    if (!state.selectedSeriesId || !state.selectedVideoId) {
      throw new Error("请先选择视频。");
    }
    await updateVideoTranscript(state.selectedSeriesId, state.selectedVideoId, markdown);
    const updatedSummary = await loadVideoSummary(state.selectedSeriesId, state.selectedVideoId);
    await reloadWorkspaceLibrary();
    dispatch({ type: "summary_loaded", summary: updatedSummary });
    return updatedSummary;
  }

  async function onSelectLocalMedia() {
    try {
      return await localWorkspaceApi.selectLocalMedia();
    } catch (error) {
      dispatch({ type: "load_failed", message: error instanceof Error ? error.message : "选择本机媒体失败" });
      throw error;
    }
  }

  async function onRelinkVideo() {
    if (!state.selectedSeriesId || !state.selectedVideoId) {
      return;
    }
    try {
      const result = await localWorkspaceApi.relinkExternalVideo(state.selectedSeriesId, state.selectedVideoId);
      if (result.relinked) {
        await reloadWorkspaceLibrary();
      }
    } catch (error) {
      dispatch({ type: "load_failed", message: error instanceof Error ? error.message : "重新链接媒体失败" });
    }
  }

  async function onImportLocalSeries(seriesTitle, sourcePaths, storageMode) {
    try {
      const rawSeries = await localWorkspaceApi.importLocalSeries(seriesTitle, sourcePaths, storageMode);
      await reloadWorkspaceLibrary();
      return rawSeries;
    } catch (error) {
      dispatch({ type: "load_failed", message: error instanceof Error ? error.message : "导入本地系列失败" });
      throw error;
    }
  }

  async function runTranscriptGeneration(startGeneration, fallbackMessage) {
    if (!state.selectedSeriesId || !state.selectedVideoId) {
      return;
    }
    const seriesId = state.selectedSeriesId;
    const videoId = state.selectedVideoId;
    const videoKey = buildVideoKey(seriesId, videoId);
    dispatch({ type: "generation_started", videoKey, seriesId, videoId });
    try {
      const submission = await startGeneration(seriesId, videoId);
      dispatch({
        type: "generation_status_loaded",
        taskKey: buildVideoGenerationTaskKey(seriesId, videoId),
        mode: "video",
        seriesId,
        videoId,
        jobId: submission.jobId,
        snapshot: {
          status: submission.status,
          stage: "queued",
          progress: 0,
          detail: "任务已进入队列",
          error: null,
        },
        subscriptionActive: true,
      });
    } catch (error) {
      if (isGenerationCancelledError(error)) {
        dispatch({
          type: "generation_cancelled",
          taskKey: buildVideoGenerationTaskKey(seriesId, videoId),
          mode: "video",
          seriesId,
          videoId,
          snapshot: { status: "cancelled", stage: "cancelled", progress: null, detail: "任务已取消，当前内容未改变", error: null },
        });
        return;
      }
      const message = errorMessage(error, fallbackMessage);
      dispatch({ type: "load_failed", message });
      dispatch({
        type: "generation_status_loaded",
        taskKey: buildVideoGenerationTaskKey(seriesId, videoId),
        mode: "video",
        seriesId,
        videoId,
        snapshot: { status: "failed", stage: "failed", progress: null, detail: null, error: message },
        subscriptionActive: false,
      });
    }
  }

  async function onUploadSrt(file) {
    if (!file || typeof file.name !== "string" || file.name.toLowerCase().endsWith(".srt") === false) {
      dispatch({ type: "load_failed", message: "请选择 .srt 字幕文件" });
      return;
    }
    await runTranscriptGeneration(
      (seriesId, videoId) => uploadSrtAndGenerateVideoSummary(seriesId, videoId, file),
      "导入 SRT 并生成概况失败",
    );
  }

  async function onRestoreAutomaticTranscript() {
    await runTranscriptGeneration(
      restoreAutomaticTranscriptAndGenerateVideoSummary,
      "改用自动转写并重新生成失败",
    );
  }

  async function onResolveLinkedSeries(provider, url) {
    try {
      const rawSeries = await resolveLinkedSeries(provider, url);
      await reloadWorkspaceLibrary();
      return rawSeries;
    } catch (error) {
      dispatch({ type: "load_failed", message: error instanceof Error ? error.message : "解析外部系列失败" });
      throw error;
    }
  }

  async function onResolvePlaygroundVideo(provider, url) {
    try {
      const rawVideo = await resolveLinkedVideo(provider, url);
      await reloadWorkspaceLibrary();
      return rawVideo;
    } catch (error) {
      dispatch({ type: "load_failed", message: error instanceof Error ? error.message : "解析外部视频失败" });
      throw error;
    }
  }

  async function onResolveSeriesVideo(provider, url, seriesId) {
    try {
      const rawVideo = await resolveLinkedVideo(provider, url, seriesId);
      await reloadWorkspaceLibrary();
      return rawVideo;
    } catch (error) {
      dispatch({ type: "load_failed", message: error instanceof Error ? error.message : "向系列添加外链视频失败" });
      throw error;
    }
  }

  async function onResolveBilibiliInboxVideo(url) {
    try {
      const rawVideo = await resolveBilibiliInboxVideo(url);
      await reloadWorkspaceLibrary();
      return rawVideo;
    } catch (error) {
      dispatch({ type: "load_failed", message: error instanceof Error ? error.message : "导入当前 Bilibili 视频失败" });
      throw error;
    }
  }

  async function onInitExternalCookie(provider, options = {}) {
    try {
      return await localWorkspaceApi.initExternalCookie(provider, options);
    } catch (error) {
      if (error instanceof DOMException && error.name === "AbortError") {
        throw error;
      }
      dispatch({ type: "load_failed", message: error instanceof Error ? error.message : "获取平台 Cookie 失败" });
      throw error;
    }
  }
  async function onLoadChaoxingStatus() {
    try {
      return await localWorkspaceApi.loadChaoxingStatus();
    } catch (error) {
      dispatch({ type: "load_failed", message: error instanceof Error ? error.message : "读取超星状态失败" });
      throw error;
    }
  }

  async function onInitChaoxing(options = {}) {
    try {
      return await localWorkspaceApi.initChaoxing(options);
    } catch (error) {
      if (error instanceof DOMException && error.name === "AbortError") {
        throw error;
      }
      dispatch({ type: "load_failed", message: error instanceof Error ? error.message : "超星初始化失败" });
      throw error;
    }
  }

  async function onCancelChaoxingInit() {
    try {
      await localWorkspaceApi.cancelChaoxingInit();
    } catch {
      // 取消是清理动作，失败时不覆盖用户当前操作反馈。
    }
  }

  async function onLoadChaoxingCourses() {
    try {
      return await localWorkspaceApi.loadChaoxingCourses();
    } catch (error) {
      dispatch({ type: "load_failed", message: error instanceof Error ? error.message : "读取超星课程失败" });
      throw error;
    }
  }

  async function onImportChaoxingCourse(courseKey, onProgress = null, options = {}) {
    try {
      const task = await localWorkspaceApi.importChaoxingCourse(courseKey);
      if (!task.jobId) {
        throw new Error("超星导入任务未返回 job_id");
      }
      options.onTaskStarted?.(task);
      return await new Promise((resolve, reject) => {
        let unsubscribe = null;
        unsubscribe = subscribeDurableJobProgress(task.jobId, async (snapshot) => {
          onProgress?.(snapshot);
          if (snapshot.status === "completed") {
            unsubscribe?.();
            const library = await reloadWorkspaceLibrary();
            const importedSeries = library?.series?.find((series) => series.id === task.seriesId);
            resolve(importedSeries ?? { title: "超星课程", videos: [] });
          }
          if (snapshot.status === "failed") {
            unsubscribe?.();
            reject(new Error(snapshot.error || "导入超星课程失败"));
          }
          if (snapshot.status === "cancelled") {
            unsubscribe?.();
            reject(new Error(snapshot.detail || "超星课程导入已取消"));
          }
        });
      });
    } catch (error) {
      dispatch({ type: "load_failed", message: error instanceof Error ? error.message : "导入超星课程失败" });
      throw error;
    }
  }

  async function onCancelChaoxingImport(jobId) {
    if (!jobId) {
      return;
    }
    try {
      await localWorkspaceApi.cancelChaoxingImport(jobId);
    } catch (error) {
      dispatch({ type: "load_failed", message: error instanceof Error ? error.message : "取消超星课程导入失败" });
      throw error;
    }
  }

  async function onDownloadVideo(video) {
    if (!state.selectedSeriesId || !video?.id) {
      return;
    }
    const seriesId = state.selectedSeriesId;
    const videoId = video.id;
    if (state.downloadingVideoKey === buildVideoKey(seriesId, videoId)) {
      dispatch({ type: "video_download_cancel_requested", seriesId, videoId });
      try {
        await cancelVideoDownload(seriesId, videoId);
      } catch (error) {
        dispatch({
          type: "video_download_failed",
          seriesId,
          videoId,
          error: error instanceof Error ? error.message : "取消下载失败",
        });
      }
      return;
    }
    try {
      await downloadLinkedVideo(seriesId, videoId);
      const library = await reloadWorkspaceLibrary();
      dispatch({ type: "video_download_completed", seriesId, videoId, library });
    } catch (error) {
      const message = error instanceof Error ? error.message : "视频下载失败";
      if (isDownloadCancelledError(error)) {
        return;
      }
      dispatch({ type: "video_download_failed", seriesId, videoId, error: message });
    }
  }

  async function onImportLocalPlaygroundVideos(sourcePaths) {
    try {
      const rawVideos = await localWorkspaceApi.importLocalPlaygroundVideos(sourcePaths);
      await reloadWorkspaceLibrary();
      return rawVideos;
    } catch (error) {
      dispatch({ type: "load_failed", message: error instanceof Error ? error.message : "导入 Playground 媒体失败" });
      throw error;
    }
  }

  async function onImportSeriesVideos(seriesId, sourcePaths) {
    try {
      const rawVideos = await localWorkspaceApi.importLocalSeriesVideos(seriesId, sourcePaths);
      await reloadWorkspaceLibrary();
      return rawVideos;
    } catch (error) {
      dispatch({ type: "load_failed", message: error instanceof Error ? error.message : "向系列导入媒体失败" });
      throw error;
    }
  }

  async function onDeleteSeries() {
    const seriesId = state.selectedSeriesId;
    if (!seriesId) {
      return;
    }
    try {
      await deleteSeries(seriesId);
      await reloadWorkspaceLibrary();
      dispatch({ type: "library_home_selected" });
    } catch (error) {
      dispatch({ type: "load_failed", message: error instanceof Error ? error.message : "删除系列失败" });
    }
  }

  async function onDeleteSeriesByIds(seriesIds) {
    const targets = Array.isArray(seriesIds) ? Array.from(new Set(seriesIds)) : [];
    if (targets.length === 0) {
      return { deleted: [], failed: [] };
    }
    const seriesById = new Map((state.library?.series ?? []).map((series) => [series.id, series]));
    const deleted = [];
    const failed = [];
    for (const seriesId of targets) {
      try {
        await deleteSeries(seriesId);
        deleted.push(seriesId);
      } catch (error) {
        failed.push({
          seriesId,
          title: seriesById.get(seriesId)?.title ?? seriesId,
          error: errorMessage(error, "删除失败"),
        });
      }
    }
    await reloadWorkspaceLibrary();
    return { deleted, failed };
  }

  async function onDeleteCurrentVideo() {
    const seriesId = state.selectedSeriesId;
    const videoId = state.selectedVideoId;
    if (!seriesId || !videoId) {
      return;
    }
    try {
      const library = await (async () => {
        await deleteVideoSource(seriesId, videoId);
        return reloadWorkspaceLibrary();
      })();
      const currentSeries = library?.series?.find((series) => series.id === seriesId) ?? null;
      if (isPlaygroundSeries(currentSeries)) {
        const nextSeries = currentSeries;
        const nextVideo = nextSeries?.videos?.[0] ?? null;
        if (nextVideo) {
          dispatch({ type: "video_selected", seriesId, videoId: nextVideo.id });
        } else {
          dispatch({ type: "playground_selected", seriesId });
        }
        return;
      }
      dispatch({ type: "series_context_selected" });
    } catch (error) {
      dispatch({ type: "load_failed", message: error instanceof Error ? error.message : "删除视频失败" });
    }
  }

  async function onRenameSeries(title) {
    const seriesId = state.selectedSeriesId;
    if (!seriesId) return;
    try {
      await renameSeries(seriesId, title);
      await reloadWorkspaceLibrary();
    } catch (error) {
      dispatch({ type: "load_failed", message: error instanceof Error ? error.message : "重命名系列失败" });
      throw error;
    }
  }

  async function onRenameCurrentVideo(title) {
    const seriesId = state.selectedSeriesId;
    const videoId = state.selectedVideoId;
    if (!seriesId || !videoId) return;
    try {
      await renameVideoSource(seriesId, videoId, title);
      await reloadWorkspaceLibrary();
    } catch (error) {
      dispatch({ type: "load_failed", message: error instanceof Error ? error.message : "重命名视频失败" });
      throw error;
    }
  }

  async function onDeleteVideos(videoIds) {
    const seriesId = state.selectedSeriesId;
    const targets = Array.isArray(videoIds) ? Array.from(new Set(videoIds)) : [];
    if (!seriesId || targets.length === 0) {
      return { deleted: [], failed: [] };
    }
    const videosById = new Map((state.library?.series?.find((series) => series.id === seriesId)?.videos ?? []).map((video) => [video.id, video]));
    const deleted = [];
    const failed = [];
    for (const videoId of targets) {
      try {
        await deleteVideoSource(seriesId, videoId);
        deleted.push(videoId);
      } catch (error) {
        failed.push({
          videoId,
          title: videosById.get(videoId)?.title ?? videoId,
          error: errorMessage(error, "删除失败"),
        });
      }
    }
    await reloadWorkspaceLibrary();
    dispatch({ type: "series_context_selected" });
    return { deleted, failed };
  }

  return {
    onChangeProcessingMode(mode) {
      dispatch({ type: "processing_mode_changed", mode });
    },
    onGenerateKnowledgeCards,
    onClearKnowledgeCardsFeedback,
    onGenerateVideo,
    onProcessLinkedVideo,
    onUploadSrt,
    onRestoreAutomaticTranscript,
    onGenerateMindmap,
    onGenerateSeriesMindmap,
    onGenerateSeries,
    onCancelGeneration,
    onCreateNote,
    onGenerateAiSummary,
    onUpdateAiSummary,
    onUpdateNote,
    onDeleteNote,
    onLoadTranscriptMarkdown,
    onLoadSummaryMarkdown,
    onUpdateSummary,
    onUpdateTranscript,
    onResolveLinkedSeries,
    onSelectLocalMedia,
    onRelinkVideo,
    onResolvePlaygroundVideo,
    onResolveSeriesVideo,
    onResolveBilibiliInboxVideo,
    onInitExternalCookie,
    onLoadChaoxingStatus,
    onInitChaoxing,
    onCancelChaoxingInit,
    onCancelChaoxingImport,
    onLoadChaoxingCourses,
    onImportChaoxingCourse,
    onImportLocalSeries,
    onImportLocalPlaygroundVideos,
    onImportSeriesVideos,
    onDeleteSeries,
    onDeleteSeriesByIds,
    onRenameSeries,
    onDeleteCurrentVideo,
    onRenameCurrentVideo,
    onDeleteVideos,
    onDownloadVideo,
  };
}
