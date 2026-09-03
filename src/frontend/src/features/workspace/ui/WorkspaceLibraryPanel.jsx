import {
  ArrowLeft,
  ArrowDown,
  Search,
  LoaderCircle,
  Sparkles,
  FileVideo,
  CheckCircle2,
  AlertTriangle,
  CircleDashed,
  FolderKanban,
  Link2,
  ExternalLink,
  Trash2,
  Square,
  CheckSquare,
  X,
  MoreHorizontal,
  CheckCheck,
  Pencil,
} from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import { useEffect, useMemo, useRef, useState } from "react";
import { buildVideoKey } from "../model/workspaceControllerUtils";
import { useOutsidePointerUp } from "../../../shared/lib/useOutsidePointerUp";

const slideTransition = { type: "spring", stiffness: 350, damping: 25, mass: 0.8 };

function VideoBadge({ video }) {
  if (video.status === "source_missing") {
    return (
      <span
        className="inline-flex items-center gap-1 text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-md bg-amber-50 dark:bg-amber-950/40 text-amber-800 dark:text-amber-300 border border-amber-200 dark:border-amber-900/70"
        title="原始媒体文件当前不可访问，请重新链接媒体。"
      >
        <Link2 size={12} />
        链接丢失
      </span>
    );
  }
  if (video.isLinked || video.status === "linked") {
    return (
      <span className="inline-flex items-center gap-1 text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-md bg-stone-100 dark:bg-stone-800 text-stone-700 dark:text-stone-300 border border-stone-200 dark:border-stone-700">
        <Link2 size={11} />
        未下载
      </span>
    );
  }
  if (video.status === "downloading") {
    return (
      <span className="inline-flex items-center gap-1 text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-md bg-stone-100 dark:bg-stone-800 text-stone-700 dark:text-stone-300 border border-stone-200 dark:border-stone-700">
        <ArrowDown size={11} className="animate-bounce" />
        下载中
      </span>
    );
  }
  if (video.status === "untranscribable") {
    return (
      <span
        className="inline-flex items-center gap-1 text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-md bg-amber-50 dark:bg-amber-950/40 text-amber-800 dark:text-amber-300 border border-amber-200 dark:border-amber-900/70"
        title="没有可供转写使用的信息"
      >
        <AlertTriangle size={12} />
        无可转写信息
      </span>
    );
  }
  if (video.processed) {
    return (
      <span className="inline-flex items-center gap-1 text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-md bg-stone-100 dark:bg-neutral-900 text-stone-700 dark:text-neutral-200 border border-stone-200 dark:border-white/10">
        <CheckCircle2 size={12} />
        已生成概况
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1 text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-md bg-stone-100 dark:bg-stone-800 text-stone-600 dark:text-stone-400 border border-transparent">
      <CircleDashed size={12} />
      未处理
    </span>
  );
}

export function getVideoGenerationButtonState({
  isGeneratingSeries,
  isGeneratingSelectedVideo,
  modelNeedsDownload,
  processed,
  sourceMissing = false,
}) {
  if (isGeneratingSeries) {
    return {
      disabled: true,
      label: "正在处理整个系列",
      tone: "busy",
    };
  }
  if (isGeneratingSelectedVideo) {
    return {
      disabled: false,
      label: "取消当前视频生成",
      tone: "danger",
    };
  }
  if (sourceMissing) {
    return {
      disabled: false,
      label: "链接媒体",
      tone: "primary",
    };
  }
  if (modelNeedsDownload) {
    return {
      disabled: false,
      label: "下载语音模型",
      tone: "primary",
    };
  }
  return {
    disabled: false,
    label: processed ? "重新生成 AI 概况" : "生成 AI 概况",
    tone: "primary",
  };
}

export function getDeleteButtonState({ isGeneratingSeries, isGeneratingSelectedVideo }) {
  if (isGeneratingSeries || isGeneratingSelectedVideo) {
    return {
      disabled: true,
      label: "处理中",
    };
  }
  return {
    disabled: false,
    label: "删除当前视频",
  };
}

function PanelFooter({
  selectedContextType,
  selectedVideo,
  isGeneratingSelectedVideo,
  isGeneratingSeries,
  seriesGenerationQueue,
  downloadingVideoKey,
  activeSeries,
  currentAsrModel,
  ragModels,
  downloadProgress,
  onGenerateVideo,
  onRelinkVideo,
  onGenerateSeries,
  onCancelGeneration,
  onDownloadVideo,
  onAddPlaygroundVideo,
  onRequestRenameCurrentVideo,
  onRequestDeleteCurrentVideo,
  onOpenSettings,
}) {
  const isPlayground = activeSeries?.id === "__playground__";
  const modelNeedsDownload = currentAsrModel != null && !currentAsrModel.downloaded;
  const embeddingModel = ragModels?.find((model) => model.key === "embedding") ?? null;
  const embeddingNeedsDownload = embeddingModel != null && !embeddingModel.downloaded;
  const selectedVideoIsDownloading =
    activeSeries?.id && selectedVideo?.id && downloadingVideoKey === buildVideoKey(activeSeries.id, selectedVideo.id);
  const [footerOverflowOpen, setFooterOverflowOpen] = useState(false);
  const footerOverflowRef = useRef(null);

  useOutsidePointerUp(footerOverflowOpen, [footerOverflowRef], () => setFooterOverflowOpen(false));

  if (selectedContextType === "playground" || (isPlayground && !selectedVideo)) {
    return (
      <div className="workspace-toolbar-surface p-4 pr-6 border-t border-stone-200/80 dark:border-stone-800 flex-shrink-0">
        <div className="mb-1">

          <h3 className="text-sm font-bold text-stone-800 dark:text-stone-100">Playground Workspace</h3>
        </div>
        <p className="text-xs leading-relaxed text-stone-600 dark:text-stone-400">
          添加或选择一个视频
        </p>
      </div>
    );
  }

  if (selectedContextType === "series") {
    const queueIsActive =
      seriesGenerationQueue?.seriesId === activeSeries?.id &&
      (seriesGenerationQueue.status === "running" || seriesGenerationQueue.status === "cancelling");
    const queueLabel = queueIsActive
      ? `已完成 ${seriesGenerationQueue.completed}/${seriesGenerationQueue.total}`
      : null;
    return (
      <div className="workspace-toolbar-surface p-4 pr-6 border-t border-stone-200/80 dark:border-stone-800 flex-shrink-0">
        <div className="mb-1">
          <p className="text-[10px] font-bold text-stone-600 dark:text-stone-400 tracking-wider uppercase mb-1 drop-shadow-sm">Now Look At:</p>
          <h3 className="text-sm font-bold text-stone-800 dark:text-stone-100">Series scope</h3>
        </div>
        <p className="text-xs leading-relaxed text-stone-600 dark:text-stone-400">
          {embeddingNeedsDownload
            ? "当前向量检索模型尚未下载，下载后才能使用 series 问答。"
            : `你可以在当前对话栏询问关于整个系列的问题 ： ${activeSeries?.title}。`}
        </p>
        <div className="mt-3">
          {queueIsActive ? (
            <div className="mb-3 rounded-2xl border border-accent/20 bg-accent/8 px-3 py-2 text-xs text-stone-600 dark:text-stone-300">
              <div className="flex items-center justify-between gap-2 font-semibold text-accent">
                <span>{seriesGenerationQueue.status === "cancelling" ? "正在取消全部处理" : "正在处理全部视频"}</span>
                <span>{queueLabel}</span>
              </div>
            </div>
          ) : null}
          {embeddingNeedsDownload ? (
            <button
              type="button"
              onClick={onOpenSettings}
              className="mb-2 w-full inline-flex items-center justify-center gap-2 rounded-2xl border border-amber-200/80 bg-amber-50/80 px-4 py-2.5 text-sm font-semibold text-amber-800 transition-colors hover:bg-amber-100/80 dark:border-amber-900/60 dark:bg-amber-950/20 dark:text-amber-200 dark:hover:bg-amber-950/30"
            >
              <ArrowDown size={16} strokeWidth={2.5} />
              下载 RAG 向量模型
            </button>
          ) : null}
          <button
            type="button"
            onClick={isGeneratingSeries ? onCancelGeneration : onGenerateSeries}
            className={`w-full inline-flex items-center justify-center gap-2 rounded-2xl px-4 py-2.5 text-sm font-semibold transition-all ${isGeneratingSeries
              ? "btn-danger-ghost border border-red-200 text-red-600 dark:border-red-900/70 dark:text-red-300"
              : "border border-accent/40 bg-accent/8 text-accent hover:bg-accent/14 hover:border-accent/60"
              }`}
          >
            {isGeneratingSeries ? (
              <>
                <LoaderCircle size={16} className="animate-spin" />
                取消处理整个系列
              </>
            ) : (
              <>
                <Sparkles size={16} strokeWidth={2.5} />
                处理全部系列视频
              </>
            )}
          </button>
        </div>
      </div>
    );
  }

  if (!selectedVideo) {
    return (
      <div className="workspace-toolbar-surface p-4 pr-6 border-t border-stone-200/80 dark:border-stone-800 flex justify-center items-center h-[98px]">
        <p className="text-xs text-stone-500 dark:text-stone-500 font-medium">可选择整个系列，或点某个视频进入视频工具</p>
      </div>
    );
  }

  if (selectedVideo.status === "downloading") {
    const hasDownloadProgress = typeof downloadProgress === "number" && Number.isFinite(downloadProgress) && downloadProgress > 0;
    const pct = hasDownloadProgress ? Math.max(0, Math.min(100, downloadProgress)) : null;
    return (
      <div className="workspace-toolbar-surface p-4 pr-6 border-t border-stone-200/80 dark:border-stone-800 flex-shrink-0">
        <div className="mb-3">
          <p className="text-[10px] font-bold text-stone-600 dark:text-stone-400 tracking-wider uppercase mb-1 drop-shadow-sm">下载中</p>
          <h3 className="text-sm font-bold text-stone-800 dark:text-stone-100 truncate">{selectedVideo.title}</h3>
        </div>
        <div className="relative w-full overflow-hidden rounded-full bg-stone-200 h-2.5 mb-1.5 dark:bg-neutral-800">
          {hasDownloadProgress ? (
            <div
              className="bg-accent h-2.5 rounded-full transition-all duration-300"
              style={{ width: `${pct}%` }}
            />
          ) : (
            <motion.div
              className="absolute inset-y-0 left-0 w-1/3 rounded-full bg-accent"
              initial={{ x: "-120%" }}
              animate={{ x: "320%" }}
              transition={{ duration: 1.1, repeat: Infinity, ease: "easeInOut" }}
            />
          )}
        </div>
        <p className="text-xs text-stone-600 dark:text-zinc-400 font-medium">
          {hasDownloadProgress ? `${pct.toFixed(0)}% 完成` : "下载中"}
        </p>
        <button
          type="button"
          onClick={() => onDownloadVideo?.(selectedVideo)}
          className="btn-danger-ghost mt-3 inline-flex w-full items-center justify-center gap-2 rounded-2xl px-4 py-2.5 text-sm font-semibold"
        >
          <X size={15} />
          取消下载
        </button>
      </div>
    );
  }

  if (selectedVideo.isLinked || selectedVideo.status === "linked") {
    return (
      <div className="workspace-toolbar-surface p-4 pr-6 border-t border-stone-200/80 dark:border-stone-800 flex-shrink-0">
        <div className="mb-3">
          <p className="text-[10px] font-bold text-stone-600 dark:text-stone-400 tracking-wider uppercase mb-1 drop-shadow-sm">当前视频</p>
          <div className="flex items-center gap-1">
            <h3 className="min-w-0 flex-1 truncate text-sm font-bold text-stone-800 dark:text-stone-100" title={selectedVideo.title}>{selectedVideo.title}</h3>
            <button type="button" onClick={onRequestRenameCurrentVideo} className="inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-lg text-stone-500 transition-colors hover:bg-stone-100 hover:text-accent dark:text-stone-400 dark:hover:bg-stone-800" title="重命名视频" aria-label="重命名视频"><Pencil size={14} /></button>
            <div className="relative" ref={footerOverflowRef}>
              <button
                type="button"
                onClick={() => setFooterOverflowOpen(!footerOverflowOpen)}
                className="inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-lg text-stone-500 transition-colors hover:bg-stone-100 dark:text-stone-400 dark:hover:bg-stone-800"
                title="更多操作"
                aria-label="更多操作"
              >
                <MoreHorizontal size={16} />
              </button>
              {footerOverflowOpen ? (
                <div className="absolute right-0 top-full z-30 mt-1 min-w-[160px] rounded-xl border border-stone-200 bg-white py-1 shadow-lg dark:border-stone-700 dark:bg-neutral-900">
                  {selectedVideo.sourceUrl && selectedVideo.provider !== "chaoxing" ? (
                    <a
                      href={selectedVideo.sourceUrl}
                      target="_blank"
                      rel="noopener noreferrer"
                      onClick={() => setFooterOverflowOpen(false)}
                      className="flex w-full items-center gap-2 px-4 py-2.5 text-xs font-medium text-stone-700 hover:bg-stone-50 dark:text-stone-200 dark:hover:bg-neutral-800"
                      title="在 Bilibili 中查看"
                    >
                      <ExternalLink size={14} />
                      在 Bilibili 中查看
                    </a>
                  ) : null}
                  <button
                    type="button"
                    onClick={() => {
                      setFooterOverflowOpen(false);
                      onRequestDeleteCurrentVideo?.();
                    }}
                    className="flex w-full items-center gap-2 px-4 py-2.5 text-xs font-medium text-red-600 hover:bg-red-50 dark:text-red-400 dark:hover:bg-red-950/30"
                  >
                    <Trash2 size={14} />
                    删除当前视频
                  </button>
                </div>
              ) : null}
            </div>
          </div>
        </div>
        <button
          type="button"
          className={`w-full inline-flex items-center justify-center gap-2 rounded-2xl px-4 py-2.5 text-sm font-semibold transition-colors ${selectedVideoIsDownloading
              ? "btn-danger-ghost border border-red-200 text-red-600 dark:border-red-900/70 dark:text-red-300"
              : "border border-accent/40 bg-accent/8 text-accent hover:bg-accent/14 hover:border-accent/60"
            }`}
          onClick={() => onDownloadVideo?.(selectedVideo)}
        >
          {selectedVideoIsDownloading ? <X size={16} strokeWidth={2.5} /> : <ArrowDown size={16} strokeWidth={2.5} />}
          {selectedVideoIsDownloading ? "取消下载" : "下载视频"}
        </button>
      </div>
    );
  }

  const videoGenerationButton = getVideoGenerationButtonState({
    isGeneratingSeries,
    isGeneratingSelectedVideo,
    modelNeedsDownload,
    processed: selectedVideo.processed,
    sourceMissing: selectedVideo.status === "source_missing",
  });
  const deleteButton = getDeleteButtonState({
    isGeneratingSeries,
    isGeneratingSelectedVideo,
  });

  return (
    <div className="workspace-toolbar-surface p-4 pr-6 border-t border-stone-200/80 dark:border-stone-800 flex-shrink-0">
      <div className="mb-3">
        <p className="text-[10px] font-bold text-stone-600 dark:text-stone-400 tracking-wider uppercase mb-1 drop-shadow-sm">当前视频</p>
        <div className="flex items-center gap-1">
          <h3 className="min-w-0 flex-1 truncate text-sm font-bold text-stone-800 dark:text-stone-100" title={selectedVideo.title}>{selectedVideo.title}</h3>
          <button type="button" onClick={onRequestRenameCurrentVideo} className="inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-lg text-stone-500 transition-colors hover:bg-stone-100 hover:text-accent dark:text-stone-400 dark:hover:bg-stone-800" title="重命名视频" aria-label="重命名视频"><Pencil size={14} /></button>
          <div className="relative" ref={footerOverflowRef}>
            <button
              type="button"
              onClick={() => setFooterOverflowOpen(!footerOverflowOpen)}
              className="inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-lg text-stone-500 transition-colors hover:bg-stone-100 dark:text-stone-400 dark:hover:bg-stone-800"
              title="更多操作"
              aria-label="更多操作"
            >
              <MoreHorizontal size={16} />
            </button>
            {footerOverflowOpen ? (
              <div className="absolute right-0 top-full z-30 mt-1 min-w-[160px] rounded-xl border border-stone-200 bg-white py-1 shadow-lg dark:border-stone-700 dark:bg-neutral-900">
                {selectedVideo.sourceUrl && selectedVideo.provider !== "chaoxing" ? (
                  <a
                    href={selectedVideo.sourceUrl}
                    target="_blank"
                    rel="noopener noreferrer"
                    onClick={() => setFooterOverflowOpen(false)}
                    className="flex w-full items-center gap-2 px-4 py-2.5 text-xs font-medium text-stone-700 hover:bg-stone-50 dark:text-stone-200 dark:hover:bg-neutral-800"
                    title="在 Bilibili 中查看"
                  >
                    <ExternalLink size={14} />
                    在 Bilibili 中查看
                  </a>
                ) : null}
                <button
                  type="button"
                  disabled={deleteButton.disabled}
                  onClick={() => {
                    setFooterOverflowOpen(false);
                    onRequestDeleteCurrentVideo?.();
                  }}
                  className="flex w-full items-center gap-2 px-4 py-2.5 text-xs font-medium text-red-600 hover:bg-red-50 disabled:cursor-not-allowed disabled:opacity-50 dark:text-red-400 dark:hover:bg-red-950/30"
                >
                  <Trash2 size={14} />
                  {deleteButton.disabled ? deleteButton.label : "删除当前视频"}
                </button>
              </div>
            ) : null}
          </div>
        </div>
      </div>
      {modelNeedsDownload ? (
        <div className="mb-3 rounded-2xl border border-amber-200/80 bg-amber-50/80 px-4 py-3 text-xs leading-6 text-amber-800 dark:border-amber-900/60 dark:bg-amber-950/20 dark:text-amber-200">
          当前语音模型 `{currentAsrModel.label}` 尚未下载，请先到设置中下载后再生成 AI 概况。
        </div>
      ) : null}
      <button
        type="button"
        className={`w-full inline-flex items-center justify-center gap-2 px-4 py-2.5 rounded-2xl font-semibold text-sm transition-all duration-200 ${videoGenerationButton.tone === "danger"
          ? "btn-danger-ghost border border-red-200 text-red-600 dark:border-red-900/70 dark:text-red-300"
          : videoGenerationButton.tone === "busy"
            ? "motion-busy-button bg-stone-200 dark:bg-stone-800 text-stone-600 dark:text-stone-400 cursor-not-allowed"
            : "border border-accent/40 bg-accent/8 text-accent hover:bg-accent/14 hover:border-accent/60 shadow-none active:scale-[0.98]"
          }`}
        onClick={
          videoGenerationButton.tone === "danger"
            ? onCancelGeneration
            : modelNeedsDownload
              ? onOpenSettings
              : selectedVideo.status === "source_missing"
                ? onRelinkVideo
                : onGenerateVideo
        }
        disabled={videoGenerationButton.disabled}
      >
        {videoGenerationButton.tone === "danger" || videoGenerationButton.tone === "busy" ? (
          <>
            <LoaderCircle size={16} strokeWidth={2.5} className="animate-spin" />
            {videoGenerationButton.label}
          </>
        ) : modelNeedsDownload ? (
          <>
            <ArrowDown size={16} strokeWidth={2.5} />
            {videoGenerationButton.label}
          </>
        ) : (
          <>
            {selectedVideo.status === "source_missing" ? <Link2 size={16} strokeWidth={2.5} /> : <Sparkles size={16} strokeWidth={2.5} />}
            {videoGenerationButton.label}
          </>
        )}
      </button>
      <p className="mt-1.5 text-[11px] text-stone-500 dark:text-stone-400">概况、知识卡与导图可在工具页单独重新生成</p>
    </div>
  );
}
export function WorkspaceLibraryPanel({
  activeSeries,
  selectedContextType,
  selectedVideo,
  isGeneratingSelectedVideo,
  isGeneratingSeries,
  seriesGenerationQueue,
  downloadingVideoKey,
  currentAsrModel,
  ragModels,
  onEnterLibraryHome,
  onSelectSeriesContext,
  onSelectVideo,
  onGenerateVideo,
  onGenerateSeries,
  onCancelGeneration,
  onDownloadVideo,
  onAddPlaygroundVideo,
  onAddSeriesVideo,
  onDeleteSeries,
  onRequestRenameSeries,
  onRequestRenameCurrentVideo,
  onRequestDeleteCurrentVideo,
  onRequestDeleteSeries,
  onRequestBulkDelete,
  seriesHasActiveWork = false,
  activeWorkSummary = "",
  bulkDeleteResult = null,
  downloadProgress,
  onOpenSettings,
}) {
  const videos = activeSeries?.videos ?? [];
  const isPlayground = activeSeries?.id === "__playground__";
  const isLinkedSeries = Boolean(activeSeries?.isLinked);
  const [filterText, setFilterText] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");
  const [selectedVideoIds, setSelectedVideoIds] = useState([]);
  const [overflowOpen, setOverflowOpen] = useState(false);
  const overflowRef = useRef(null);
  useOutsidePointerUp(overflowOpen, [overflowRef], () => setOverflowOpen(false));
  useEffect(() => {
    const existingIds = new Set(videos.map((video) => video.id));
    setSelectedVideoIds((current) => current.filter((videoId) => existingIds.has(videoId)));
  }, [videos]);
  const normalizedFilter = filterText.trim().toLowerCase();
  const generatedCount = useMemo(() => videos.filter((v) => v.processed).length, [videos]);
  const pendingCount = useMemo(() => videos.filter((v) => !v.processed).length, [videos]);
  const filteredVideos = useMemo(() => {
    return videos.filter((video) => {
      if (statusFilter === "generated" && !video.processed) {
        return false;
      }
      if (statusFilter === "pending" && video.processed) {
        return false;
      }
      if (!normalizedFilter) {
        return true;
      }
      const haystacks = [video.title, video.sourceName, video.sourceUrl, video.coreProblem]
        .filter((value) => typeof value === "string")
        .map((value) => value.toLowerCase());
      return haystacks.some((value) => value.includes(normalizedFilter));
    });
  }, [normalizedFilter, statusFilter, videos]);
  const selectedVideoSet = useMemo(() => new Set(selectedVideoIds), [selectedVideoIds]);
  const selectedCount = selectedVideoIds.length;
  const toggleVideoSelection = (videoId) => {
    setSelectedVideoIds((current) => current.includes(videoId)
      ? current.filter((id) => id !== videoId)
      : [...current, videoId]);
  };
  const selectFilteredVideos = () => {
    setSelectedVideoIds(filteredVideos.map((video) => video.id));
  };
  const seriesDeleteButton = getDeleteButtonState({
    isGeneratingSeries,
    isGeneratingSelectedVideo: false,
  });

  return (
    <section className="flex flex-col h-full w-full bg-transparent relative">

      {/* Sidebar Header */}
      <div className="p-5 pb-4 border-b border-stone-200/80 dark:border-stone-800 flex-shrink-0">
        <div className="flex justify-between items-start mb-4">
          <div>
            <p className="text-[10px] font-bold text-stone-600 dark:text-zinc-400 tracking-wider uppercase mb-1">
              {isPlayground ? "Playground" : isLinkedSeries ? "Linked Series" : "Sources"}
            </p>
            <h2 className="text-lg font-bold text-stone-800 dark:text-stone-100 leading-tight">{activeSeries?.title ?? "未选择 series"}</h2>
          </div>
          <button
            type="button"
            className="inline-flex items-center justify-center w-8 h-8 rounded-full text-stone-600 dark:text-stone-400 hover:bg-stone-100 dark:hover:bg-stone-800 transition-colors"
            onClick={onEnterLibraryHome}
            title="返回分类列表"
          >
            <ArrowLeft size={18} />
          </button>
        </div>
        {!isPlayground ? (
          <div className="mb-4 flex items-center gap-2">
            <button
              type="button"
              onClick={() => onAddSeriesVideo?.()}
              className="flex-1 inline-flex items-center justify-center gap-2 rounded-2xl border border-accent/40 bg-accent/8 px-3 py-2 text-xs font-semibold text-accent transition-colors hover:bg-accent/14 hover:border-accent/60"
            >
              <ArrowDown size={14} />
              添加视频
            </button>
            <div className="relative" ref={overflowRef}>
              <button
                type="button"
                onClick={() => setOverflowOpen(!overflowOpen)}
                className="inline-flex h-9 w-9 items-center justify-center rounded-xl text-stone-500 transition-colors hover:bg-stone-100 dark:text-stone-400 dark:hover:bg-stone-800"
                title="更多操作"
                aria-label="更多操作"
              >
                <MoreHorizontal size={18} />
              </button>
              {overflowOpen && (
                <div className="absolute right-0 top-full mt-1 z-30 min-w-[140px] rounded-xl border border-stone-200 bg-white py-1 shadow-lg dark:border-stone-700 dark:bg-neutral-900">
                  <button
                    type="button"
                    onClick={() => {
                      setOverflowOpen(false);
                      onRequestRenameSeries?.();
                    }}
                    className="flex w-full items-center gap-2 px-4 py-2.5 text-xs font-medium text-stone-700 hover:bg-stone-50 dark:text-stone-200 dark:hover:bg-neutral-800"
                  >
                    <Pencil size={14} />
                    重命名系列
                  </button>
                  <button
                    type="button"
                    disabled={seriesDeleteButton.disabled}
                    onClick={() => {
                      setOverflowOpen(false);
                      onRequestDeleteSeries?.();
                    }}
                    className="flex w-full items-center gap-2 px-4 py-2.5 text-xs font-medium text-red-600 hover:bg-red-50 disabled:cursor-not-allowed disabled:opacity-50 dark:text-red-400 dark:hover:bg-red-950/30"
                  >
                    <Trash2 size={14} />
                    {seriesDeleteButton.disabled ? seriesDeleteButton.label : "删除整个系列"}
                  </button>
                </div>
              )}
            </div>
          </div>
        ) : onAddPlaygroundVideo ? (
          <div className="mb-4">
            <button
              type="button"
              onClick={onAddPlaygroundVideo}
              className="w-full inline-flex items-center justify-center gap-2 rounded-2xl border border-accent/40 bg-accent/8 px-4 py-3 text-sm font-semibold text-accent shadow-none transition-colors hover:bg-accent/14 hover:border-accent/60"
            >
              <ArrowDown size={16} strokeWidth={2.5} />
              添加 Playground 媒体
            </button>
          </div>
        ) : null}

        {!isPlayground ? (
          <div className="flex flex-col gap-4">
            <div className="relative">
              <Search size={14} className="pointer-events-none absolute left-4 top-1/2 -translate-y-1/2 text-stone-500 dark:text-stone-500" />
              <input
                type="text"
                value={filterText}
                onChange={(event) => setFilterText(event.target.value)}
                placeholder="搜索视频"
                className="w-full rounded-2xl border border-stone-200/80 bg-white px-10 py-2.5 pr-10 text-sm text-stone-700 outline-none transition-colors placeholder:text-stone-400 focus:border-accent/40 dark:border-stone-800 dark:bg-stone-900 dark:text-stone-100 dark:placeholder:text-stone-500"
              />
              {filterText ? (
                <button
                  type="button"
                  onClick={() => setFilterText("")}
                  className="absolute right-3 top-1/2 inline-flex h-7 w-7 -translate-y-1/2 items-center justify-center rounded-full text-stone-500 transition-colors hover:bg-stone-100 hover:text-stone-700 dark:text-stone-500 dark:hover:bg-stone-800 dark:hover:text-stone-200"
                  aria-label="清空搜索"
                  title="清空搜索"
                >
                  <X size={14} />
                </button>
              ) : null}
            </div>
            <div className="flex rounded-xl bg-stone-100 p-1 dark:bg-stone-800/80" role="group" aria-label="视频状态筛选">
              {[
                ["all", "全部", videos.length],
                ["generated", "已生成", generatedCount],
                ["pending", "未处理", pendingCount],
              ].map(([value, label, count]) => (
                <button
                  key={value}
                  type="button"
                  onClick={() => setStatusFilter(value)}
                  aria-pressed={statusFilter === value}
                  className={`relative flex-1 rounded-lg px-2 py-1.5 text-xs font-semibold transition-all duration-200 ${statusFilter === value
                      ? "bg-white text-stone-900 shadow-sm dark:bg-stone-700 dark:text-stone-100"
                      : "text-stone-500 hover:text-stone-700 dark:text-stone-400 dark:hover:text-stone-200"
                    }`}
                >
                  {label}
                  <span className={`ml-1 inline-flex min-w-[1.1rem] items-center justify-center rounded-full px-1 py-px text-[10px] font-bold leading-none ${statusFilter === value
                      ? "bg-accent/10 text-accent"
                      : "bg-stone-200/80 text-stone-500 dark:bg-stone-700 dark:text-stone-400"
                    }`}>{count}</span>
                </button>
              ))}
            </div>
            {bulkDeleteResult ? (
              <div className="rounded-xl border border-stone-200 bg-stone-50 px-3 py-2 text-xs leading-relaxed text-stone-700 dark:border-stone-700 dark:bg-stone-800/60 dark:text-stone-300">
                已删除 {bulkDeleteResult.deleted.length} 项{bulkDeleteResult.failed.length ? `，${bulkDeleteResult.failed.length} 项未删除。` : "。"}
                {bulkDeleteResult.failed.length ? (
                  <ul className="mt-1 list-disc pl-4">
                    {bulkDeleteResult.failed.map((item) => <li key={item.videoId}>{item.title}：{item.error}</li>)}
                  </ul>
                ) : null}
              </div>
            ) : null}
          </div>
        ) : null}

      </div>

      {/* Video / Source List */}
      <div className="relative flex-1 overflow-y-auto" aria-label="视频列表">
        <div className={`p-4 flex flex-col gap-3 ${selectedCount > 0 ? "pb-20" : ""}`}>
          {!isPlayground ? (
            <button
              type="button"
              onClick={onSelectSeriesContext}
              className={`text-left flex flex-col gap-2 p-4 rounded-[1.5rem] border transition-all duration-200 outline-none shadow-sm bg-accent/10 border-accent/30 text-stone-900 dark:text-stone-100 z-10 relative
              ${selectedContextType === "series"
                  ? "ring-[2px] ring-accent/20"
                  : "hover:bg-accent/15 hover:border-accent/40 hover:-translate-y-0.5 hover:shadow-[0_10px_24px_rgba(15,23,42,0.08)] cursor-pointer"
                }`}
            >
              <div className="flex justify-between items-start w-full gap-2">
                <span className="inline-flex items-center gap-1 text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-md bg-accent/10 border border-accent/20 text-accent">
                  <FolderKanban size={12} />
                  当前系列
                </span>
              </div>
              <div className="flex flex-col gap-0.5 mt-1">
                <strong className="text-base font-semibold line-clamp-2 tracking-[-0.01em] text-stone-900 dark:text-stone-100">
                  {activeSeries?.title}
                </strong>
                <span className="text-xs truncate text-stone-600 dark:text-stone-400">
                  聚焦整个系列，使用系列级上下文进行分析
                </span>
              </div>
            </button>
          ) : null}

          {filteredVideos.map((video, index) => {
            const isActive = video.id === selectedVideo?.id && selectedContextType !== "series";
            return (
              <div
                key={video.id}
                role="button"
                tabIndex={0}
                className={`motion-stagger text-left flex flex-col gap-2 p-4 rounded-[1.5rem] border transition-all duration-200 outline-none cursor-pointer relative z-10
                ${isActive
                    ? "border-transparent"
                    : "workspace-elevated-panel border-stone-200 dark:border-stone-800 hover:border-stone-300 dark:hover:border-stone-700 hover:bg-white dark:hover:bg-neutral-800 hover:-translate-y-0.5 hover:shadow-[0_8px_20px_rgba(15,23,42,0.06)] dark:hover:shadow-[0_8px_20px_rgba(0,0,0,0.22)]"
                  }`}
                style={{ "--stagger-index": index }}
                onClick={() => onSelectVideo(activeSeries.id, video.id)}
                onKeyDown={(event) => {
                  if (event.key === "Enter" || event.key === " ") {
                    event.preventDefault();
                    onSelectVideo(activeSeries.id, video.id);
                  }
                }}
              >
                {isActive && (
                  <motion.div
                    layoutId="library-bg"
                    className="absolute inset-0 bg-stone-100/80 dark:bg-stone-800/80 border border-stone-300 dark:border-stone-700 shadow-sm rounded-[1.5rem] -z-10"
                    transition={slideTransition}
                  />
                )}
                <div className="flex justify-between items-start w-full gap-2">
                  <VideoBadge video={video} />
                  <div className="flex items-center gap-2">
                    {!isPlayground ? (
                      <button
                        type="button"
                        disabled={seriesHasActiveWork}
                        onClick={(event) => {
                          event.stopPropagation();
                          toggleVideoSelection(video.id);
                        }}
                        className={`inline-flex h-7 w-7 items-center justify-center rounded-lg transition-colors disabled:cursor-not-allowed disabled:opacity-50 ${selectedVideoSet.has(video.id)
                            ? "bg-accent/10 text-accent"
                            : "text-stone-400 hover:bg-stone-100 hover:text-stone-600 dark:text-stone-500 dark:hover:bg-stone-700 dark:hover:text-stone-300"
                          }`}
                        aria-label={selectedVideoSet.has(video.id) ? `取消选择 ${video.title}` : `选择 ${video.title}`}
                      >
                        {selectedVideoSet.has(video.id) ? <CheckSquare size={16} /> : <Square size={16} />}
                      </button>
                    ) : null}
                    <FileVideo size={16} className={isActive ? "text-accent" : "text-stone-500 dark:text-stone-500"} />
                  </div>
                </div>
                <div className="flex flex-col gap-0.5 mt-1">
                  <strong className={`text-sm font-semibold line-clamp-2 ${isActive ? "text-stone-900 dark:text-stone-100" : "text-stone-800 dark:text-stone-100"}`}>
                    {video.title}
                  </strong>
                  {video.coreProblem ? (
                    <span
                      className="text-xs text-stone-600 dark:text-stone-300 line-clamp-2 leading-snug whitespace-pre-line"
                      title={video.coreProblem}
                    >
                      {video.coreProblem}
                    </span>
                  ) : null}
                  <span className="text-xs text-stone-600 dark:text-stone-400 truncate">
                    {video.isLinked || video.status === "linked" ? video.sourceUrl || video.sourceName : video.sourceName}
                  </span>
                </div>
              </div>
            );
          })}
          {!isPlayground && filteredVideos.length === 0 ? (
            <div className="workspace-elevated-panel rounded-[1.5rem] border border-dashed border-stone-200/80 px-4 py-8 text-center text-sm text-stone-600 dark:border-stone-800 dark:text-stone-400">
              当前筛选条件下没有匹配的视频。
            </div>
          ) : null}
        </div>

        {/* Floating Bulk Action Bar */}
        <AnimatePresence>
          {!isPlayground && selectedCount > 0 && (
            <motion.div
              initial={{ y: 16, opacity: 0 }}
              animate={{ y: 0, opacity: 1 }}
              exit={{ y: 16, opacity: 0 }}
              transition={{ type: "spring", stiffness: 400, damping: 28 }}
              className="sticky bottom-0 z-20 mx-3 mb-3"
            >
              <div className="flex items-center justify-between gap-2 rounded-2xl border border-stone-200/80 bg-white/95 px-4 py-2.5 shadow-lg backdrop-blur-sm dark:border-stone-700 dark:bg-neutral-900/95">
                <span className="text-xs font-semibold text-stone-700 dark:text-stone-200">
                  已选 {selectedCount} 项
                </span>
                <div className="flex items-center gap-1.5">
                  <button
                    type="button"
                    disabled={seriesHasActiveWork || filteredVideos.length === 0}
                    onClick={selectFilteredVideos}
                    className="inline-flex items-center gap-1.5 rounded-xl px-2.5 py-1.5 text-xs font-medium text-stone-600 transition-colors hover:bg-stone-100 disabled:cursor-not-allowed disabled:opacity-50 dark:text-stone-300 dark:hover:bg-stone-800"
                  >
                    <CheckCheck size={14} />
                    全选
                  </button>
                  <button
                    type="button"
                    onClick={() => setSelectedVideoIds([])}
                    className="inline-flex items-center gap-1.5 rounded-xl px-2.5 py-1.5 text-xs font-medium text-stone-500 transition-colors hover:bg-stone-100 dark:text-stone-400 dark:hover:bg-stone-800"
                  >
                    取消
                  </button>
                  <button
                    type="button"
                    disabled={seriesHasActiveWork}
                    onClick={() => onRequestBulkDelete?.(selectedVideoIds)}
                    className="inline-flex items-center gap-1.5 rounded-xl bg-red-50 px-3 py-1.5 text-xs font-semibold text-red-600 transition-colors hover:bg-red-100 disabled:cursor-not-allowed disabled:opacity-50 dark:bg-red-950/30 dark:text-red-400 dark:hover:bg-red-950/50"
                    title={seriesHasActiveWork ? activeWorkSummary || "系列中有任务正在处理，暂不能批量删除" : "删除所选视频"}
                  >
                    <Trash2 size={14} />
                    删除
                  </button>
                </div>
              </div>
              {seriesHasActiveWork ? (
                <p className="mt-1.5 px-2 text-[11px] leading-relaxed text-amber-600 dark:text-amber-400">{activeWorkSummary || "系列中有任务正在处理，暂不能批量删除。"}</p>
              ) : null}
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      <PanelFooter
        selectedContextType={selectedContextType}
        selectedVideo={selectedVideo}
        isGeneratingSelectedVideo={isGeneratingSelectedVideo}
        isGeneratingSeries={isGeneratingSeries}
        seriesGenerationQueue={seriesGenerationQueue}
        downloadingVideoKey={downloadingVideoKey}
        activeSeries={activeSeries}
        currentAsrModel={currentAsrModel}
        ragModels={ragModels}
        downloadProgress={downloadProgress}
        onGenerateVideo={onGenerateVideo}
        onGenerateSeries={onGenerateSeries}
        onCancelGeneration={onCancelGeneration}
        onDownloadVideo={onDownloadVideo}
        onAddPlaygroundVideo={onAddPlaygroundVideo}
        onRequestRenameCurrentVideo={onRequestRenameCurrentVideo}
        onRequestDeleteCurrentVideo={onRequestDeleteCurrentVideo}
        onOpenSettings={onOpenSettings}
      />
    </section>
  );
}
