import { ArrowLeft, LoaderCircle, Sparkles, FileVideo, CheckCircle2, CircleDashed, FolderKanban } from "lucide-react";
import { motion } from "framer-motion";

const slideTransition = { type: "spring", stiffness: 350, damping: 25, mass: 0.8 };

export function WorkspaceLibraryPanel({
  activeSeries,
  selectedContextType,
  selectedVideo,
  isGeneratingSelectedVideo,
  onEnterLibraryHome,
  onSelectSeriesContext,
  onSelectVideo,
  onGenerateVideo,
}) {
  return (
    <section className="flex flex-col h-full w-full bg-transparent relative">

      {/* Sidebar Header */}
      <div className="p-5 pb-4 border-b border-stone-200/80 dark:border-stone-800 flex-shrink-0">
        <div className="flex justify-between items-start mb-4">
          <div>
            <p className="text-[10px] font-bold text-stone-600 dark:text-zinc-400 tracking-wider uppercase mb-1">Sources</p>
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

        {/* Quick Stats */}
        <div className="flex gap-2 text-xs">
          <div className="workspace-muted-panel flex-1 rounded-xl p-2 border">
            <span className="block text-stone-400 dark:text-stone-500 mb-0.5">总视频数</span>
            <strong className="text-stone-700 dark:text-stone-200">{activeSeries?.videos?.length ?? 0} 个视频</strong>
          </div>
          <div className="flex-1 rounded-xl p-2 border border-sky-200/80 dark:border-sky-900/70 bg-sky-50/80 dark:bg-sky-950/25">
            <span className="block text-sky-700/80 dark:text-sky-300/80 mb-0.5">已处理</span>
            <strong className="text-sky-900 dark:text-sky-100">{activeSeries?.videos?.filter((video) => video.processed).length ?? 0} 个视频</strong>
          </div>
        </div>
      </div>

      {/* Video / Source List */}
      <div className="flex-1 overflow-y-auto p-4 flex flex-col gap-3" aria-label="视频列表">
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

        {(activeSeries?.videos ?? []).map((video, index) => {
          const isActive = video.id === selectedVideo?.id && selectedContextType !== "series";
          return (
            <button
              key={video.id}
              type="button"
              className={`motion-stagger text-left flex flex-col gap-2 p-4 rounded-[1.5rem] border transition-all duration-200 outline-none cursor-pointer relative z-10
                ${isActive
                  ? "border-transparent"
                  : "workspace-elevated-panel border-stone-200 dark:border-stone-800 hover:border-stone-300 dark:hover:border-stone-700 hover:bg-white dark:hover:bg-[#1f1f1f] hover:-translate-y-0.5 hover:shadow-[0_8px_20px_rgba(15,23,42,0.06)] dark:hover:shadow-[0_8px_20px_rgba(0,0,0,0.22)]"
                }`}
              style={{ "--stagger-index": index }}
              onClick={() => onSelectVideo(activeSeries.id, video.id)}
            >
              {isActive && (
                <motion.div
                  layoutId="library-bg"
                  className="absolute inset-0 bg-sky-50/80 dark:bg-sky-950/25 border border-sky-300 dark:border-sky-700 shadow-sm rounded-[1.5rem] -z-10"
                  transition={slideTransition}
                />
              )}
              <div className="flex justify-between items-start w-full gap-2">
                <span className={`inline-flex items-center gap-1 text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-md ${video.processed ? "bg-stone-100 dark:bg-[#111111] text-stone-700 dark:text-[#ededed] border border-stone-200 dark:border-white/10" : "bg-stone-100 dark:bg-stone-800 text-stone-500 dark:text-stone-400 border border-transparent"}`}>
                  {video.processed ? <CheckCircle2 size={12} /> : <CircleDashed size={12} />}
                  {video.processed ? "已生成概况" : "未处理"}
                </span>
                <FileVideo size={16} className={isActive ? "text-[#0b6bff]" : "text-stone-400 dark:text-stone-500"} />
              </div>
              <div className="flex flex-col gap-0.5 mt-1">
                <strong className={`text-sm font-semibold line-clamp-2 ${isActive ? "text-sky-900 dark:text-sky-100" : "text-stone-800 dark:text-stone-100"}`}>
                  {video.title}
                </strong>
                <span className="text-xs text-stone-500 dark:text-stone-400 truncate">{video.sourceName}</span>
              </div>
            </button>
          );
        })}
      </div>

      {/* Footer Generate Action */}
      {selectedContextType === "series" ? (
        <div className="workspace-toolbar-surface p-4 pr-6 border-t border-stone-200/80 dark:border-stone-800 flex-shrink-0">
          <div className="mb-1">
            <p className="text-[10px] font-bold text-stone-500 dark:text-stone-400 tracking-wider uppercase mb-1 drop-shadow-sm">当前上下文</p>
            <h3 className="text-sm font-bold text-stone-800 dark:text-stone-100">整个系列</h3>
          </div>
          <p className="text-xs leading-relaxed text-stone-500 dark:text-stone-400">
            右侧会显示系列级工具，AI 也会默认理解你现在关注的是整个 {activeSeries?.title}。
          </p>
        </div>
      ) : selectedVideo ? (
        <div className="workspace-toolbar-surface p-4 pr-6 border-t border-stone-200/80 dark:border-stone-800 flex-shrink-0">
          <div className="mb-3">
            <p className="text-[10px] font-bold text-stone-500 dark:text-stone-400 tracking-wider uppercase mb-1 drop-shadow-sm">当前视频</p>
            <h3 className="text-sm font-bold text-stone-800 dark:text-stone-100 truncate" title={selectedVideo.title}>{selectedVideo.title}</h3>
          </div>
          <button
            type="button"
            className={`w-full inline-flex items-center justify-center gap-2 px-4 py-2.5 rounded-2xl font-semibold text-sm transition-all duration-200
              ${isGeneratingSelectedVideo
                ? "motion-busy-button bg-stone-200 dark:bg-stone-800 text-stone-500 dark:text-stone-400 cursor-not-allowed"
                : "bg-[#0070f3] text-white hover:bg-[#0064db] shadow-sm active:scale-[0.98]"
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
        </div>
      ) : (
        <div className="workspace-toolbar-surface p-4 pr-6 border-t border-stone-200/80 dark:border-stone-800 flex justify-center items-center h-[98px]">
          <p className="text-xs text-stone-400 dark:text-stone-500 font-medium">可选择整个系列，或点某个视频进入视频工具</p>
        </div>
      )}
    </section>
  );
}
