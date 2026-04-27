import {
  ArrowLeft,
  ArrowDown,
  LoaderCircle,
  Sparkles,
  FileVideo,
  CheckCircle2,
  CircleDashed,
  FolderKanban,
  Link2,
  ExternalLink,
  Trash2,
} from "lucide-react";
import { motion } from "framer-motion";

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

function PanelFooter({
  selectedContextType,
  selectedVideo,
  isGeneratingSelectedVideo,
  activeSeries,
  downloadProgress,
  onGenerateVideo,
  onDownloadVideo,
  onAddPlaygroundVideo,
  onRequestDeleteCurrentVideo,
}) {
  const isPlayground = activeSeries?.id === "__playground__";

  if (selectedContextType === "playground" || (isPlayground && !selectedVideo)) {
    return (
      <div className="workspace-toolbar-surface p-4 pr-6 border-t border-stone-200/80 dark:border-stone-800 flex-shrink-0">
        <div className="mb-1">

          <h3 className="text-sm font-bold text-stone-800 dark:text-stone-100">Playground Workspace</h3>
        </div>
        <p className="text-xs leading-relaxed text-stone-500 dark:text-stone-400">
          添加或选择一个视频，再进入 AI 概况、预览、笔记和知识工具。
        </p>
        {onAddPlaygroundVideo ? (
          <div className="mt-3 flex gap-2">
            <button
              type="button"
              onClick={onAddPlaygroundVideo}
              className="flex-1 inline-flex items-center justify-center gap-2 rounded-2xl bg-stone-900 px-4 py-2.5 text-sm font-semibold text-white shadow-sm transition-colors hover:bg-stone-800 dark:bg-white dark:text-stone-900 dark:hover:bg-stone-100"
            >
              <ArrowDown size={16} strokeWidth={2.5} />
              添加 Playground 视频
            </button>
            {selectedVideo ? (
              <button
                type="button"
                onClick={() => onRequestDeleteCurrentVideo?.()}
                className="inline-flex items-center justify-center w-11 h-11 rounded-2xl border border-red-200 bg-red-50 text-red-600 transition-colors hover:bg-red-100 dark:border-red-900/60 dark:bg-red-950/30 dark:text-red-300 dark:hover:bg-red-950/45"
                title="删除当前视频"
              >
                <Trash2 size={16} />
              </button>
            ) : null}
          </div>
        ) : null}
      </div>
    );
  }

  if (selectedContextType === "series") {
    return (
      <div className="workspace-toolbar-surface p-4 pr-6 border-t border-stone-200/80 dark:border-stone-800 flex-shrink-0">
        <div className="mb-1">
          <p className="text-[10px] font-bold text-stone-500 dark:text-stone-400 tracking-wider uppercase mb-1 drop-shadow-sm">Now Look At:</p>
          <h3 className="text-sm font-bold text-stone-800 dark:text-stone-100">Series scope</h3>
        </div>
        <p className="text-xs leading-relaxed text-stone-500 dark:text-stone-400">
          你可以在当前对话栏询问关于整个系列的问题 ： {activeSeries?.title}。
        </p>
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
            className="flex-1 inline-flex items-center justify-center gap-2 px-4 py-2.5 rounded-2xl font-semibold text-sm bg-stone-900 text-white hover:bg-stone-800 dark:bg-white dark:text-stone-900 dark:hover:bg-stone-100 shadow-sm active:scale-[0.98] transition-all"
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
              className="inline-flex items-center justify-center w-10 h-10 rounded-2xl bg-stone-100 dark:bg-neutral-800 border border-stone-200 dark:border-white/10 text-stone-500 dark:text-zinc-400 hover:text-accent hover:border-accent/30 transition-colors"
              title="在 Bilibili 中查看"
            >
              <ExternalLink size={15} />
            </a>
          ) : null}
          <button
            type="button"
            onClick={() => onRequestDeleteCurrentVideo?.()}
            className="inline-flex items-center justify-center w-10 h-10 rounded-2xl border border-red-200 bg-red-50 text-red-600 transition-colors hover:bg-red-100 dark:border-red-900/60 dark:bg-red-950/30 dark:text-red-300 dark:hover:bg-red-950/45"
            title="删除当前视频"
          >
            <Trash2 size={15} />
          </button>
        </div>
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
        <div className="w-full bg-stone-200 dark:bg-stone-700 rounded-full h-2.5 mb-1.5">
          <div
            className="bg-stone-900 dark:bg-stone-100 h-2.5 rounded-full transition-all duration-300"
            style={{ width: `${pct}%` }}
          />
        </div>
        <p className="text-xs text-stone-500 dark:text-zinc-400 font-medium">{pct.toFixed(0)}% 完成</p>
      </div>
    );
  }

  return (
    <div className="workspace-toolbar-surface p-4 pr-6 border-t border-stone-200/80 dark:border-stone-800 flex-shrink-0">
      <div className="mb-3">
        <p className="text-[10px] font-bold text-stone-500 dark:text-stone-400 tracking-wider uppercase mb-1 drop-shadow-sm">当前视频</p>
        <h3 className="text-sm font-bold text-stone-800 dark:text-stone-100 truncate" title={selectedVideo.title}>{selectedVideo.title}</h3>
      </div>
      <button
        type="button"
        className={`w-full inline-flex items-center justify-center gap-2 px-4 py-2.5 rounded-2xl font-semibold text-sm transition-all duration-200 ${isGeneratingSelectedVideo
          ? "motion-busy-button bg-stone-200 dark:bg-stone-800 text-stone-500 dark:text-stone-400 cursor-not-allowed"
          : "bg-accent text-white hover:bg-accent/90 shadow-sm active:scale-[0.98]"
          }`}
        onClick={onGenerateVideo}
        disabled={isGeneratingSelectedVideo}
      >
        {isGeneratingSelectedVideo ? (
          <>
            <LoaderCircle size={16} strokeWidth={2.5} className="animate-spin text-stone-500" />
            正在生成 AI 概况...
          </>
        ) : (
          <>
            <Sparkles size={16} strokeWidth={2.5} />
            {selectedVideo.processed ? "重新生成 AI 概况" : "生成 AI 概况"}
          </>
        )}
      </button>
      <button
        type="button"
        onClick={() => onRequestDeleteCurrentVideo?.()}
        className="mt-2 inline-flex w-full items-center justify-center gap-2 rounded-2xl border border-red-200 bg-red-50 px-4 py-2.5 text-sm font-semibold text-red-700 transition-colors hover:bg-red-100 dark:border-red-900/60 dark:bg-red-950/30 dark:text-red-300 dark:hover:bg-red-950/45"
      >
        <Trash2 size={15} />
        删除当前视频
      </button>
    </div>
  );
}
export function WorkspaceLibraryPanel({
  activeSeries,
  selectedContextType,
  selectedVideo,
  isGeneratingSelectedVideo,
  onEnterLibraryHome,
  onSelectSeriesContext,
  onSelectVideo,
  onGenerateVideo,
  onDownloadVideo,
  onAddPlaygroundVideo,
  onAddSeriesVideo,
  onDeleteSeries,
  onRequestDeleteCurrentVideo,
  onRequestDeleteSeries,
  downloadProgress,
}) {
  const videos = activeSeries?.videos ?? [];
  const isLinkedSeries = Boolean(activeSeries?.isLinked);
  const isPlayground = activeSeries?.id === "__playground__";

  return (
    <section className="flex flex-col h-full w-full bg-transparent relative">

      {/* Sidebar Header */}
      <div className="p-5 pb-4 border-b border-stone-200/80 dark:border-stone-800 flex-shrink-0">
        <div className="flex justify-between items-start mb-4">
          <div>
            <p className="text-[10px] font-bold text-stone-600 dark:text-zinc-400 tracking-wider uppercase mb-1">
              {isPlayground ? "Playground" : isLinkedSeries ? "🔗 Linked Series" : "Sources"}
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
              className="inline-flex items-center gap-2 rounded-2xl bg-stone-900 px-3 py-2 text-xs font-semibold text-white transition-colors hover:bg-stone-800 dark:bg-white dark:text-stone-900 dark:hover:bg-stone-100"
            >
              <ArrowDown size={14} />
              添加视频
            </button>
            <button
              type="button"
              onClick={() => onRequestDeleteSeries?.()}
              className="inline-flex items-center gap-2 rounded-2xl border border-red-200 bg-red-50 px-3 py-2 text-xs font-semibold text-red-700 transition-colors hover:bg-red-100 dark:border-red-900/60 dark:bg-red-950/30 dark:text-red-300 dark:hover:bg-red-950/45"
            >
              <Trash2 size={14} />
              删除整个系列
            </button>
          </div>
        ) : null}

        {/* Quick Stats */}
        <div className="flex gap-2 text-xs">
          <div className="workspace-muted-panel flex-1 rounded-xl p-2 border">
            <span className="block text-stone-400 dark:text-stone-500 mb-0.5">总视频数</span>
            <strong className="text-stone-700 dark:text-stone-200">{videos.length} 个视频</strong>
          </div>
          <div className="workspace-panel flex-1 rounded-xl p-2 border border-stone-200 dark:border-white/10 shadow-sm">
            <span className="block text-stone-500 dark:text-stone-400 font-medium mb-0.5">已处理</span>
            <strong className="text-stone-900 dark:text-stone-100">{videos.filter((video) => video.processed).length} 个视频</strong>
          </div>
        </div>
      </div>

      {/* Video / Source List */}
      <div className="flex-1 overflow-y-auto p-4 flex flex-col gap-3" aria-label="视频列表">
        {!isPlayground ? (
          <button
            type="button"
            onClick={onSelectSeriesContext}
            className={`text-left flex flex-col gap-2 p-4 rounded-[1.5rem] border transition-all duration-200 outline-none shadow-sm bg-stone-950 border-stone-900 text-white dark:bg-white dark:border-stone-200 dark:text-stone-950 z-10 relative
              ${selectedContextType === "series"
                ? "ring-[2px] ring-stone-950/20 dark:ring-white/30"
                : "hover:bg-black hover:border-black dark:hover:bg-stone-50 dark:hover:border-stone-300 hover:-translate-y-0.5 hover:shadow-[0_10px_24px_rgba(15,23,42,0.08)] dark:hover:shadow-[0_10px_24px_rgba(0,0,0,0.2)] cursor-pointer"
              }`}
          >
            <div className="flex justify-between items-start w-full gap-2">
              <span className="inline-flex items-center gap-1 text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-md bg-white/10 border border-white/10 text-white dark:bg-stone-100 dark:border-stone-200 dark:text-stone-700">
                <FolderKanban size={12} />
                当前系列
              </span>
            </div>
            <div className="flex flex-col gap-0.5 mt-1">
              <strong className="text-base font-semibold line-clamp-2 tracking-[-0.01em] text-white dark:text-stone-950">
                {activeSeries?.title}
              </strong>
              <span className="text-xs truncate text-stone-300 dark:text-stone-600">
                聚焦整个 series，供 AI 和工具使用系列级上下文
              </span>
            </div>
          </button>
        ) : null}

        {videos.map((video, index) => {
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
                <span className="text-xs text-stone-500 dark:text-stone-400 truncate">{video.isLinked || video.status === "linked" ? video.sourceUrl || video.sourceName : video.sourceName}</span>
              </div>
            </button>
          );
        })}
      </div>

      <PanelFooter
        selectedContextType={selectedContextType}
        selectedVideo={selectedVideo}
        isGeneratingSelectedVideo={isGeneratingSelectedVideo}
        activeSeries={activeSeries}
        downloadProgress={downloadProgress}
        onGenerateVideo={onGenerateVideo}
        onDownloadVideo={onDownloadVideo}
        onAddPlaygroundVideo={onAddPlaygroundVideo}
        onRequestDeleteCurrentVideo={onRequestDeleteCurrentVideo}
      />
    </section>
  );
}
