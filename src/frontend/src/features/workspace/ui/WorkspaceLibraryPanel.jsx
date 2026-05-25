import {
  ArrowLeft,
  ArrowDown,
  Search,
  LoaderCircle,
  Sparkles,
  FileVideo,
  CheckCircle2,
  CircleDashed,
  FolderKanban,
  Link2,
  ExternalLink,
  Trash2,
  X,
} from "lucide-react";
import { motion } from "framer-motion";
import { useMemo, useState } from "react";

const slideTransition = { type: "spring", stiffness: 350, damping: 25, mass: 0.8 };

function VideoBadge({ video }) {
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
  if (video.processed) {
    return (
      <span className="inline-flex items-center gap-1 text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-md bg-stone-100 dark:bg-neutral-900 text-stone-700 dark:text-neutral-200 border border-stone-200 dark:border-white/10">
        <CheckCircle2 size={12} />
        已生成概况
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1 text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-md bg-stone-100 dark:bg-stone-800 text-stone-500 dark:text-stone-400 border border-transparent">
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
  if (modelNeedsDownload) {
    return {
      disabled: false,
      label: "先下载语音模型",
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
  activeSeries,
  currentAsrModel,
  ragModels,
  downloadProgress,
  onGenerateVideo,
  onGenerateSeries,
  onCancelGeneration,
  onDownloadVideo,
  onAddPlaygroundVideo,
  onRequestDeleteCurrentVideo,
  onOpenSettings,
}) {
  const isPlayground = activeSeries?.id === "__playground__";
  const modelNeedsDownload = currentAsrModel != null && !currentAsrModel.downloaded;
  const embeddingModel = ragModels?.find((model) => model.key === "embedding") ?? null;
  const embeddingNeedsDownload = embeddingModel != null && !embeddingModel.downloaded;

  if (selectedContextType === "playground" || (isPlayground && !selectedVideo)) {
    return (
      <div className="workspace-toolbar-surface p-4 pr-6 border-t border-stone-200/80 dark:border-stone-800 flex-shrink-0">
        <div className="mb-1">

          <h3 className="text-sm font-bold text-stone-800 dark:text-stone-100">Playground Workspace</h3>
        </div>
        <p className="text-xs leading-relaxed text-stone-500 dark:text-stone-400">
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
      ? `已结束 ${seriesGenerationQueue.completed}/${seriesGenerationQueue.total}`
      : null;
    const currentLabel = queueIsActive ? seriesGenerationQueue.detail : null;
    return (
      <div className="workspace-toolbar-surface p-4 pr-6 border-t border-stone-200/80 dark:border-stone-800 flex-shrink-0">
        <div className="mb-1">
          <p className="text-[10px] font-bold text-stone-500 dark:text-stone-400 tracking-wider uppercase mb-1 drop-shadow-sm">Now Look At:</p>
          <h3 className="text-sm font-bold text-stone-800 dark:text-stone-100">Series scope</h3>
        </div>
        <p className="text-xs leading-relaxed text-stone-500 dark:text-stone-400">
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
              {currentLabel ? (
                <p className="mt-1 truncate text-stone-500 dark:text-stone-400">{currentLabel}</p>
              ) : null}
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
        <p className="text-xs text-stone-400 dark:text-stone-500 font-medium">可选择整个系列，或点某个视频进入视频工具</p>
      </div>
    );
  }

  if (selectedVideo.status === "downloading") {
    const pct = downloadProgress ?? 0;
    return (
      <div className="workspace-toolbar-surface p-4 pr-6 border-t border-stone-200/80 dark:border-stone-800 flex-shrink-0">
        <div className="mb-3">
          <p className="text-[10px] font-bold text-stone-500 dark:text-stone-400 tracking-wider uppercase mb-1 drop-shadow-sm">下载中</p>
          <h3 className="text-sm font-bold text-stone-800 dark:text-stone-100 truncate">{selectedVideo.title}</h3>
        </div>
        <div className="w-full bg-stone-200 dark:bg-neutral-800 rounded-full h-2.5 mb-1.5">
          <div
            className="bg-accent h-2.5 rounded-full transition-all duration-300"
            style={{ width: `${pct}%` }}
          />
        </div>
        <p className="text-xs text-stone-500 dark:text-zinc-400 font-medium">{pct.toFixed(0)}% 完成</p>
      </div>
    );
  }

  if (selectedVideo.isLinked || selectedVideo.status === "linked") {
    return (
      <div className="workspace-toolbar-surface p-4 pr-6 border-t border-stone-200/80 dark:border-stone-800 flex-shrink-0">
        <div className="mb-3">
          <p className="text-[10px] font-bold text-stone-500 dark:text-stone-400 tracking-wider uppercase mb-1 drop-shadow-sm">当前视频</p>
          <h3 className="text-sm font-bold text-stone-800 dark:text-stone-100 truncate" title={selectedVideo.title}>{selectedVideo.title}</h3>
        </div>
        <div className="flex gap-2">
          <button
            type="button"
            className="flex-1 inline-flex items-center justify-center gap-2 rounded-2xl border border-accent/40 bg-accent/8 px-4 py-2.5 text-sm font-semibold text-accent transition-colors hover:bg-accent/14 hover:border-accent/60"
            onClick={() => onDownloadVideo?.(selectedVideo)}
          >
            <ArrowDown size={16} strokeWidth={2.5} />
            下载视频
          </button>
          {selectedVideo.sourceUrl ? (
            <a
              href={selectedVideo.sourceUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex h-10 w-10 items-center justify-center rounded-2xl border border-stone-200 bg-stone-100 text-stone-500 transition-colors hover:border-accent/30 hover:text-accent dark:border-white/10 dark:bg-neutral-800 dark:text-zinc-400"
              title="在 Bilibili 中查看"
            >
              <ExternalLink size={15} />
            </a>
          ) : null}
          <button
            type="button"
            onClick={() => onRequestDeleteCurrentVideo?.()}
            className="btn-danger-ghost inline-flex h-10 w-10 items-center justify-center rounded-2xl"
            title="删除当前视频"
          >
            <Trash2 size={15} />
          </button>
        </div>
      </div>
    );
  }

  const videoGenerationButton = getVideoGenerationButtonState({
    isGeneratingSeries,
    isGeneratingSelectedVideo,
    modelNeedsDownload,
    processed: selectedVideo.processed,
  });
  const deleteButton = getDeleteButtonState({
    isGeneratingSeries,
    isGeneratingSelectedVideo,
  });

  return (
    <div className="workspace-toolbar-surface p-4 pr-6 border-t border-stone-200/80 dark:border-stone-800 flex-shrink-0">
      <div className="mb-3">
        <p className="text-[10px] font-bold text-stone-500 dark:text-stone-400 tracking-wider uppercase mb-1 drop-shadow-sm">当前视频</p>
        <h3 className="text-sm font-bold text-stone-800 dark:text-stone-100 truncate" title={selectedVideo.title}>{selectedVideo.title}</h3>
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
            ? "motion-busy-button bg-stone-200 dark:bg-stone-800 text-stone-500 dark:text-stone-400 cursor-not-allowed"
            : "border border-accent/40 bg-accent/8 text-accent hover:bg-accent/14 hover:border-accent/60 shadow-none active:scale-[0.98]"
          }`}
        onClick={
          videoGenerationButton.tone === "danger"
            ? onCancelGeneration
            : modelNeedsDownload
              ? onOpenSettings
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
            <Sparkles size={16} strokeWidth={2.5} />
            {videoGenerationButton.label}
          </>
        )}
      </button>
      <button
        type="button"
        onClick={() => onRequestDeleteCurrentVideo?.()}
        disabled={deleteButton.disabled}
        className="btn-danger-ghost mt-2 inline-flex w-full items-center justify-center gap-2 rounded-2xl px-4 py-2.5 text-sm font-semibold disabled:cursor-not-allowed disabled:opacity-50"
      >
        <Trash2 size={15} />
        {deleteButton.label}
      </button>
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
  onRequestDeleteCurrentVideo,
  onRequestDeleteSeries,
  downloadProgress,
  onOpenSettings,
}) {
  const videos = activeSeries?.videos ?? [];
  const isPlayground = activeSeries?.id === "__playground__";
  const isLinkedSeries = Boolean(activeSeries?.isLinked);
  const [filterText, setFilterText] = useState("");
  const normalizedFilter = filterText.trim().toLowerCase();
  const filteredVideos = useMemo(() => {
    if (!normalizedFilter) {
      return videos;
    }
    return videos.filter((video) => {
      const haystacks = [video.title, video.sourceName, video.sourceUrl]
        .filter((value) => typeof value === "string")
        .map((value) => value.toLowerCase());
      return haystacks.some((value) => value.includes(normalizedFilter));
    });
  }, [normalizedFilter, videos]);
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
            className="inline-flex items-center justify-center w-8 h-8 rounded-full text-stone-500 dark:text-stone-400 hover:bg-stone-100 dark:hover:bg-stone-800 transition-colors"
            onClick={onEnterLibraryHome}
            title="返回分类列表"
          >
            <ArrowLeft size={18} />
          </button>
        </div>
        {!isPlayground ? (
          <div className="mb-4 flex gap-2">
            <button
              type="button"
              onClick={() => onAddSeriesVideo?.()}
              className="inline-flex items-center gap-2 rounded-2xl border border-accent/40 bg-accent/8 px-3 py-2 text-xs font-semibold text-accent transition-colors hover:bg-accent/14 hover:border-accent/60"
            >
              <ArrowDown size={14} />
              添加视频
            </button>
            <button
              type="button"
              onClick={() => onRequestDeleteSeries?.()}
              disabled={seriesDeleteButton.disabled}
              className="btn-danger-ghost inline-flex items-center gap-2 rounded-2xl px-3 py-2 text-xs font-semibold disabled:cursor-not-allowed disabled:opacity-50"
            >
              <Trash2 size={14} />
              {seriesDeleteButton.disabled ? seriesDeleteButton.label : "删除整个系列"}
            </button>
          </div>
        ) : onAddPlaygroundVideo ? (
          <div className="mb-4">
            <button
              type="button"
              onClick={onAddPlaygroundVideo}
              className="w-full inline-flex items-center justify-center gap-2 rounded-2xl border border-accent/40 bg-accent/8 px-4 py-3 text-sm font-semibold text-accent shadow-none transition-colors hover:bg-accent/14 hover:border-accent/60"
            >
              <ArrowDown size={16} strokeWidth={2.5} />
              添加 Playground 视频
            </button>
          </div>
        ) : null}

        {!isPlayground ? (
          <div className="relative">
            <Search size={14} className="pointer-events-none absolute left-4 top-1/2 -translate-y-1/2 text-stone-400 dark:text-stone-500" />
            <input
              type="text"
              value={filterText}
              onChange={(event) => setFilterText(event.target.value)}
              placeholder="筛选当前系列内容"
              className="w-full rounded-2xl border border-stone-200/80 bg-white px-10 py-2.5 pr-10 text-sm text-stone-700 outline-none transition-colors placeholder:text-stone-400 focus:border-accent/40 dark:border-stone-800 dark:bg-stone-900 dark:text-stone-100 dark:placeholder:text-stone-500"
            />
            {filterText ? (
              <button
                type="button"
                onClick={() => setFilterText("")}
                className="absolute right-3 top-1/2 inline-flex h-7 w-7 -translate-y-1/2 items-center justify-center rounded-full text-stone-400 transition-colors hover:bg-stone-100 hover:text-stone-700 dark:text-stone-500 dark:hover:bg-stone-800 dark:hover:text-stone-200"
                aria-label="清空筛选条件"
                title="清空筛选条件"
              >
                <X size={14} />
              </button>
            ) : null}
          </div>
        ) : null}

      </div>

      {/* Video / Source List */}
      <div className="flex-1 overflow-y-auto p-4 flex flex-col gap-3" aria-label="视频列表">
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
              <span className="text-xs truncate text-stone-500 dark:text-stone-400">
                聚焦整个 series，供 AI 和工具使用系列级上下文
              </span>
            </div>
          </button>
        ) : null}

        {filteredVideos.map((video, index) => {
          const isActive = video.id === selectedVideo?.id && selectedContextType !== "series";
          return (
            <button
              key={video.id}
              type="button"
              className={`motion-stagger text-left flex flex-col gap-2 p-4 rounded-[1.5rem] border transition-all duration-200 outline-none cursor-pointer relative z-10
                ${isActive
                  ? "border-transparent"
                  : "workspace-elevated-panel border-stone-200 dark:border-stone-800 hover:border-stone-300 dark:hover:border-stone-700 hover:bg-white dark:hover:bg-neutral-800 hover:-translate-y-0.5 hover:shadow-[0_8px_20px_rgba(15,23,42,0.06)] dark:hover:shadow-[0_8px_20px_rgba(0,0,0,0.22)]"
                }`}
              style={{ "--stagger-index": index }}
              onClick={() => onSelectVideo(activeSeries.id, video.id)}
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
                <FileVideo size={16} className={isActive ? "text-accent" : "text-stone-400 dark:text-stone-500"} />
              </div>
              <div className="flex flex-col gap-0.5 mt-1">
                <strong className={`text-sm font-semibold line-clamp-2 ${isActive ? "text-stone-900 dark:text-stone-100" : "text-stone-800 dark:text-stone-100"}`}>
                  {video.title}
                </strong>
                <span className="text-xs text-stone-500 dark:text-stone-400 truncate">
                  {video.isLinked || video.status === "linked" ? video.sourceUrl || video.sourceName : video.sourceName}
                </span>
              </div>
            </button>
          );
        })}
        {!isPlayground && filteredVideos.length === 0 ? (
          <div className="workspace-elevated-panel rounded-[1.5rem] border border-dashed border-stone-200/80 px-4 py-8 text-center text-sm text-stone-500 dark:border-stone-800 dark:text-stone-400">
            当前筛选条件下没有匹配的视频。
          </div>
        ) : null}
      </div>

      <PanelFooter
        selectedContextType={selectedContextType}
        selectedVideo={selectedVideo}
        isGeneratingSelectedVideo={isGeneratingSelectedVideo}
        isGeneratingSeries={isGeneratingSeries}
        seriesGenerationQueue={seriesGenerationQueue}
        activeSeries={activeSeries}
        currentAsrModel={currentAsrModel}
        ragModels={ragModels}
        downloadProgress={downloadProgress}
        onGenerateVideo={onGenerateVideo}
        onGenerateSeries={onGenerateSeries}
        onCancelGeneration={onCancelGeneration}
        onDownloadVideo={onDownloadVideo}
        onAddPlaygroundVideo={onAddPlaygroundVideo}
        onRequestDeleteCurrentVideo={onRequestDeleteCurrentVideo}
        onOpenSettings={onOpenSettings}
      />
    </section>
  );
}
