import {
  cancelSeriesSummaries,
  cancelVideoSummary,
  createVideoNote,
  deleteSeries,
  deleteVideoNote,
  deleteVideoSource,
  generateVideoKnowledgeCards,
  generateVideoMindmap,
  generateSeriesSummaries,
  generateVideoSummary,
  importLocalPlaygroundVideos,
  importLocalSeries,
  importLocalSeriesVideos,
  loadWorkspaceLibrary,
  resolveBilibiliSeries,
  resolveBilibiliVideo,
  startVideoDownload,
  subscribeVideoDownloadProgress,
  updateVideoNote,
} from "./workspaceApi";
import { PLAYGROUND_SERIES_ID } from "./workspaceControllerConstants";
import { buildVideoKey } from "./workspaceControllerUtils";
import { buildSeriesGenerationTaskKey, buildVideoGenerationTaskKey, getGenerationTaskForSelection } from "./workspaceState";

export function getPendingVideosForSeriesGeneration(library, seriesId) {
  const series = library?.series?.find((item) => item.id === seriesId);
  return series?.videos?.filter((video) => !video.processed && video.status !== "linked" && !video.isLinked) ?? [];
}

function isGenerationCancelledError(error) {
  if (!(error instanceof Error)) {
    return false;
  }
  return error.message.includes("generation cancelled");
}

export function createWorkspaceContentActions({ state, dispatch, selectedVideo }) {
  async function reloadWorkspaceLibrary() {
    const library = await loadWorkspaceLibrary();
    dispatch({ type: "workspace_loaded", library });
    return library;
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

    dispatch({ type: "series_generation_queue_started", seriesId, total: pendingVideos.length });
    dispatch({ type: "series_generation_started", seriesId });
    try {
      await generateSeriesSummaries(seriesId, {
        transcriptEnhancementEnabled: state.ui.transcriptEnhancementEnabled,
      });
      const library = await reloadWorkspaceLibrary();
      dispatch({
        type: "series_generation_succeeded",
        taskKey: buildSeriesGenerationTaskKey(seriesId),
        seriesId,
        library,
      });
      dispatch({
        type: "series_generation_queue_finished",
        seriesId,
        status: "completed",
      });
    } catch (error) {
      const message = error instanceof Error ? error.message : "生成失败";
      dispatch({ type: "load_failed", message });
      dispatch({
        type: "generation_status_loaded",
        taskKey: buildSeriesGenerationTaskKey(seriesId),
        mode: "series",
        seriesId,
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
      dispatch({ type: "series_generation_queue_finished", seriesId, status: "failed" });
    }
  }

  async function onCancelGeneration() {
    try {
      if (
        state.seriesGenerationQueue?.seriesId === state.selectedSeriesId &&
        (state.seriesGenerationQueue.status === "running" || state.seriesGenerationQueue.status === "cancelling") &&
        state.selectedSeriesId
      ) {
        dispatch({ type: "series_generation_queue_cancelling", seriesId: state.selectedSeriesId });
        await cancelSeriesSummaries(state.selectedSeriesId);
        return;
      }
      if (
        state.selectedContextType === "series" &&
        state.selectedSeriesId
      ) {
        dispatch({ type: "series_generation_queue_cancelling", seriesId: state.selectedSeriesId });
        await cancelSeriesSummaries(state.selectedSeriesId);
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

  async function onDownloadVideo(video) {
    if (!state.selectedSeriesId || !video?.id) {
      return;
    }
    const seriesId = state.selectedSeriesId;
    const videoId = video.id;
    dispatch({ type: "video_download_started", seriesId, videoId });
    try {
      await startVideoDownload(seriesId, videoId);
      const unsubscribe = subscribeVideoDownloadProgress(seriesId, videoId, async (snapshot) => {
        if (snapshot.status === "running" || snapshot.status === "completed") {
          dispatch({ type: "video_download_progress_updated", seriesId, videoId, progress: snapshot.progress });
        }
        if (snapshot.status === "completed") {
          unsubscribe();
          const library = await reloadWorkspaceLibrary();
          dispatch({ type: "video_download_completed", seriesId, videoId, library });
        }
        if (snapshot.status === "failed" || snapshot.status === "cancelled") {
          unsubscribe();
          dispatch({ type: "video_download_failed", seriesId, videoId });
          if (snapshot.status === "failed") {
            dispatch({ type: "load_failed", message: snapshot.error ?? "视频下载失败" });
          }
        }
      });
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
      dispatch({ type: "load_failed", message: error instanceof Error ? error.message : "导入 Playground 视频失败" });
      throw error;
    }
  }

  async function onImportSeriesVideos(seriesId, files) {
    try {
      const rawVideos = await importLocalSeriesVideos(seriesId, files);
      await reloadWorkspaceLibrary();
      return rawVideos;
    } catch (error) {
      dispatch({ type: "load_failed", message: error instanceof Error ? error.message : "向系列导入视频失败" });
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
    onGenerateSeries,
    onCancelGeneration,
    onCreateNote,
    onUpdateNote,
    onDeleteNote,
    onResolveLinkedSeries,
    onResolvePlaygroundVideo,
    onResolveSeriesVideo,
    onImportLocalSeries,
    onImportLocalPlaygroundVideos,
    onImportSeriesVideos,
    onDeleteSeries,
    onDeleteCurrentVideo,
    onDownloadVideo,
  };
}
