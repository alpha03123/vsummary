import {
  cancelSeriesSummaries,
  cancelChaoxingInit,
  cancelChaoxingImport,
  cancelVideoDownload,
  cancelVideoSummary,
  createVideoNote,
  deleteSeries,
  deleteVideoNote,
  deleteVideoSource,
  generateSeriesMindmap,
  generateVideoKnowledgeCards,
  generateVideoMindmap,
  generateSeriesSummaries,
  generateVideoSummary,
  importChaoxingCourse,
  importLocalPlaygroundVideos,
  importLocalSeries,
  importLocalSeriesVideos,
  loadWorkspaceLibrary,
  initChaoxing,
  loadChaoxingCourses,
  loadChaoxingStatus,
  resolveBilibiliSeries,
  resolveBilibiliVideo,
  subscribeChaoxingImportProgress,
  startVideoDownload,
  subscribeVideoDownloadProgress,
  updateVideoNote,
} from "./workspaceApi";
import { PLAYGROUND_SERIES_ID } from "./workspaceControllerConstants";
import { buildVideoKey } from "./workspaceControllerUtils";
import { buildSeriesGenerationTaskKey, buildVideoGenerationTaskKey, getGenerationTaskForSelection } from "./workspaceState";

const activeSeriesCancellationRef = { current: null };
let nextSeriesRunSequence = 0;

function createSeriesRunId(seriesId) {
  nextSeriesRunSequence += 1;
  return `${seriesId}:${nextSeriesRunSequence}`;
}

export function getPendingVideosForSeriesGeneration(library, seriesId) {
  const series = library?.series?.find((item) => item.id === seriesId);
  return series?.videos?.filter((video) => !video.processed) ?? [];
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
      const cards = await generateVideoKnowledgeCards(state.selectedSeriesId, state.selectedVideoId);
      dispatch({
        type: "knowledge_cards_loaded",
        cards,
        feedbackTone: "success",
        feedbackMessage:
          Array.isArray(cards?.cards) && cards.cards.length
            ? `已生成 ${cards.cards.length} 张知识卡片`
            : "知识卡片已生成，但这次没有抽取出稳定卡片",
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
    const videoKey = buildVideoKey(seriesId, videoId);
    dispatch({ type: "generation_started", videoKey, seriesId, videoId });

    try {
      const summaryResult = await generateVideoSummary(seriesId, videoId, {
        transcriptEnhancementEnabled: state.ui.transcriptEnhancementEnabled,
      });
      dispatch({
        type: "generation_succeeded",
        taskKey: buildVideoGenerationTaskKey(seriesId, videoId),
        seriesId,
        videoId,
        summary: summaryResult,
      });
    } catch (error) {
      if (isGenerationCancelledError(error)) {
        dispatch({
          type: "generation_cancelled",
          taskKey: buildVideoGenerationTaskKey(seriesId, videoId),
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
        taskKey: buildVideoGenerationTaskKey(seriesId, videoId),
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
    }
  }

  async function onGenerateSeries() {
    if (!state.selectedSeriesId) {
      return;
    }

    const seriesId = state.selectedSeriesId;
    const pendingVideos = getPendingVideosForSeriesGeneration(state.library, seriesId);
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
      const linkedVideos = pendingVideos.filter(isLinkedVideo);
      for (const [index, video] of linkedVideos.entries()) {
        dispatch({
          type: "series_generation_queue_download_started",
          seriesId,
          runId,
          videoId: video.id,
          videoTitle: video.title,
          detail: `正在下载未缓存视频 ${index + 1}/${linkedVideos.length}`,
        });
        await downloadLinkedVideo(seriesId, video.id, { cancelCheck: () => cancellation.requested });
        if (cancellation.requested) {
          throw new Error("任务已取消");
        }
        dispatch({ type: "series_generation_queue_download_finished", seriesId, runId, videoId: video.id });
      }
      if (linkedVideos.length) {
        await reloadWorkspaceLibrary();
      }
      dispatch({
        type: "series_generation_queue_detail_updated",
        seriesId,
        runId,
        detail: `已完成 0/${pendingVideos.length}`,
      });
      if (cancellation.requested) {
        throw new Error("任务已取消");
      }
      await generateSeriesSummaries(seriesId, {
        transcriptEnhancementEnabled: state.ui.transcriptEnhancementEnabled,
        runId,
      });
      const library = await reloadWorkspaceLibrary();
      dispatch({
        type: "series_generation_succeeded",
        taskKey: buildSeriesGenerationTaskKey(seriesId),
        seriesId,
        runId,
        library,
      });
      dispatch({
        type: "series_generation_queue_finished",
        seriesId,
        runId,
        status: "completed",
      });
    } catch (error) {
      if (isDownloadCancelledError(error)) {
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
        return;
      }
      const message = error instanceof Error ? error.message : "生成失败";
      await reloadWorkspaceLibraryAfterSeriesStop();
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
    } finally {
      if (activeSeriesCancellationRef.current === cancellation) {
        activeSeriesCancellationRef.current = null;
      }
    }
  }

  async function downloadLinkedVideo(seriesId, videoId, options = {}) {
    dispatch({ type: "video_download_started", seriesId, videoId });
    await startVideoDownload(seriesId, videoId);
    await new Promise((resolve, reject) => {
      const cancelTimer = options.cancelCheck
        ? window.setInterval(() => {
            if (options.cancelCheck()) {
              cleanup();
              dispatch({ type: "video_download_failed", seriesId, videoId });
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
      unsubscribe = subscribeVideoDownloadProgress(seriesId, videoId, async (snapshot) => {
        if (snapshot.status === "running" || snapshot.status === "completed") {
          dispatch({ type: "video_download_progress_updated", seriesId, videoId, progress: snapshot.progress });
        }
        if (snapshot.status === "completed") {
          cleanup();
          resolve();
        }
        if (snapshot.status === "failed" || snapshot.status === "cancelled") {
          cleanup();
          dispatch({ type: "video_download_failed", seriesId, videoId });
          reject(new Error(snapshot.error || snapshot.detail || "视频下载失败"));
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
        dispatch({ type: "video_generation_cancelling", seriesId: state.selectedSeriesId, videoId: state.selectedVideoId });
        await cancelVideoSummary(state.selectedSeriesId, state.selectedVideoId);
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
      getPendingVideosForSeriesGeneration(state.library, seriesId)
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

  async function onGenerateMindmap() {
    if (!state.selectedSeriesId || !state.selectedVideoId) {
      return;
    }

    const videoKey = buildVideoKey(state.selectedSeriesId, state.selectedVideoId);
    dispatch({ type: "mindmap_generation_started", videoKey });
    try {
      const mindmapResult = await generateVideoMindmap(state.selectedSeriesId, state.selectedVideoId);
      dispatch({
        type: "mindmap_generation_succeeded",
        mindmap: mindmapResult,
      });
    } catch (error) {
      dispatch({
        type: "load_failed",
        message: error instanceof Error ? error.message : "生成失败",
      });
    }
  }

  async function onGenerateSeriesMindmap() {
    if (!state.selectedSeriesId) return;

    dispatch({ type: "series_mindmap_generation_started" });
    try {
      const mindmapResult = await generateSeriesMindmap(state.selectedSeriesId);
      dispatch({ type: "series_mindmap_generation_succeeded", mindmap: mindmapResult });
    } catch (error) {
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

  async function onImportLocalSeries(seriesTitle, files) {
    try {
      const rawSeries = await importLocalSeries(seriesTitle, files);
      await reloadWorkspaceLibrary();
      return rawSeries;
    } catch (error) {
      dispatch({ type: "load_failed", message: error instanceof Error ? error.message : "导入本地系列失败" });
      throw error;
    }
  }

  async function onResolveLinkedSeries(url) {
    try {
      const rawSeries = await resolveBilibiliSeries(url);
      await reloadWorkspaceLibrary();
      return rawSeries;
    } catch (error) {
      dispatch({ type: "load_failed", message: error instanceof Error ? error.message : "解析 Bilibili 系列失败" });
      throw error;
    }
  }

  async function onResolvePlaygroundVideo(url) {
    try {
      const rawVideo = await resolveBilibiliVideo(url);
      await reloadWorkspaceLibrary();
      return rawVideo;
    } catch (error) {
      dispatch({ type: "load_failed", message: error instanceof Error ? error.message : "解析 Bilibili 视频失败" });
      throw error;
    }
  }

  async function onResolveSeriesVideo(url, seriesId) {
    try {
      const rawVideo = await resolveBilibiliVideo(url, seriesId);
      await reloadWorkspaceLibrary();
      return rawVideo;
    } catch (error) {
      dispatch({ type: "load_failed", message: error instanceof Error ? error.message : "向系列添加外链视频失败" });
      throw error;
    }
  }

  async function onLoadChaoxingStatus() {
    try {
      return await loadChaoxingStatus();
    } catch (error) {
      dispatch({ type: "load_failed", message: error instanceof Error ? error.message : "读取超星状态失败" });
      throw error;
    }
  }

  async function onInitChaoxing(options = {}) {
    try {
      return await initChaoxing(options);
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
      await cancelChaoxingInit();
    } catch {
      // 取消是清理动作，失败时不覆盖用户当前操作反馈。
    }
  }

  async function onLoadChaoxingCourses() {
    try {
      return await loadChaoxingCourses();
    } catch (error) {
      dispatch({ type: "load_failed", message: error instanceof Error ? error.message : "读取超星课程失败" });
      throw error;
    }
  }

  async function onImportChaoxingCourse(courseKey, onProgress = null, options = {}) {
    try {
      const task = await importChaoxingCourse(courseKey);
      if (!task.taskId) {
        throw new Error("超星导入任务未返回 task_id");
      }
      options.onTaskStarted?.(task);
      return await new Promise((resolve, reject) => {
        let unsubscribe = null;
        unsubscribe = subscribeChaoxingImportProgress(task.taskId, async (snapshot) => {
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

  async function onCancelChaoxingImport(taskId) {
    if (!taskId) {
      return;
    }
    try {
      await cancelChaoxingImport(taskId);
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
      try {
        await cancelVideoDownload(seriesId, videoId);
      } catch (error) {
        dispatch({ type: "load_failed", message: error instanceof Error ? error.message : "取消下载失败" });
      }
      return;
    }
    try {
      await downloadLinkedVideo(seriesId, videoId);
      const library = await reloadWorkspaceLibrary();
      dispatch({ type: "video_download_completed", seriesId, videoId, library });
    } catch (error) {
      dispatch({ type: "video_download_failed", seriesId, videoId });
      dispatch({ type: "load_failed", message: error instanceof Error ? error.message : "视频下载失败" });
    }
  }

  async function onImportLocalPlaygroundVideos(files) {
    try {
      const rawVideos = await importLocalPlaygroundVideos(files);
      await reloadWorkspaceLibrary();
      return rawVideos;
    } catch (error) {
      dispatch({ type: "load_failed", message: error instanceof Error ? error.message : "导入 Playground 媒体失败" });
      throw error;
    }
  }

  async function onImportSeriesVideos(seriesId, files) {
    try {
      const rawVideos = await importLocalSeriesVideos(seriesId, files);
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
      if (seriesId === PLAYGROUND_SERIES_ID) {
        const nextSeries = library?.series?.find((series) => series.id === PLAYGROUND_SERIES_ID) ?? null;
        const nextVideo = nextSeries?.videos?.[0] ?? null;
        if (nextVideo) {
          dispatch({ type: "video_selected", seriesId: PLAYGROUND_SERIES_ID, videoId: nextVideo.id });
        } else {
          dispatch({ type: "playground_selected" });
        }
        return;
      }
      dispatch({ type: "series_context_selected" });
    } catch (error) {
      dispatch({ type: "load_failed", message: error instanceof Error ? error.message : "删除视频失败" });
    }
  }

  return {
    onGenerateKnowledgeCards,
    onClearKnowledgeCardsFeedback,
    onGenerateVideo,
    onGenerateMindmap,
    onGenerateSeriesMindmap,
    onGenerateSeries,
    onCancelGeneration,
    onCreateNote,
    onUpdateNote,
    onDeleteNote,
    onResolveLinkedSeries,
    onResolvePlaygroundVideo,
    onResolveSeriesVideo,
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
    onDeleteCurrentVideo,
    onDownloadVideo,
  };
}
