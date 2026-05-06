import { ArrowRight, FolderKanban, PlayCircle, Sparkles, LayoutGrid, CheckCircle2, Link2 } from "lucide-react";
import { motion } from "framer-motion";
import { staggerContainer, blurVariant } from "../../../lib/animations";

function getProcessedCount(series) {
  return series.videos.filter((video) => video.processed).length;
}

export function WorkspaceSeriesGrid({ library, onOpenSeries, onAddSeries, compact = false }) {
  const allSeries = library?.series ?? [];
  const series = allSeries.filter((item) => item.id !== "__playground__");

  if (!series.length) {
    return (
      <section className="flex flex-col items-center justify-center min-h-[60vh] max-w-2xl mx-auto text-center p-12 workspace-panel rounded-[2rem] border m-6">
        <div className="w-16 h-16 workspace-muted-panel rounded-2xl border flex items-center justify-center text-stone-400 mb-6 shadow-sm">
          <FolderKanban size={32} />
        </div>
        <p className="text-[11px] font-bold text-stone-500 dark:text-zinc-500 tracking-widest uppercase mb-4">Videos Library</p>
        <h2 className="text-3xl font-bold text-stone-900 dark:text-stone-100 mb-4 tracking-tight">还没有分类 (Series)</h2>
        <p className="text-stone-500 dark:text-zinc-400 leading-relaxed text-lg font-medium">
          你可以直接使用导入入口创建系列，也可以手动把视频放进
          <code className="bg-stone-100 dark:bg-neutral-900 px-2 py-1 rounded-md text-stone-700 dark:text-zinc-300 font-mono text-sm mx-1 border border-stone-200 dark:border-white/5">videos/&lt;series&gt;/</code>
          目录。
        </p>
        {onAddSeries ? (
          <button
            type="button"
            onClick={onAddSeries}
            className="mt-6 inline-flex items-center gap-2 rounded-2xl bg-accent px-5 py-3 text-sm font-bold text-white shadow-sm transition-colors hover:bg-accent/90"
          >
            <Link2 size={15} /> 添加系列
          </button>
        ) : null}
      </section>
    );
  }

  const totalVideos = series.reduce((count, item) => count + item.videos.length, 0);
  const totalProcessed = series.reduce(
    (count, item) => count + item.videos.filter((video) => video.processed).length,
    0,
  );

  if (compact) {
    return (
      <section className="flex h-full flex-col bg-transparent">
        <div className="border-b border-stone-200/80 dark:border-white/5 px-6 pb-5 pt-6 bg-stone-50/50 dark:bg-transparent">
          <p className="text-[11px] font-bold uppercase tracking-widest text-stone-500 dark:text-zinc-500 mb-1.5 flex items-center gap-2">
            Series Shelf
          </p>
          <h2 className="text-2xl font-extrabold text-stone-900 dark:text-stone-100 tracking-tight">All Shelves</h2>
          <p className="mt-2 text-[13px] font-medium leading-relaxed text-stone-500 dark:text-zinc-400">
            点击下方任一系列来进入工作区
          </p>

          {onAddSeries ? (
            <button
              type="button"
              onClick={onAddSeries}
              className="mt-4 inline-flex w-full items-center justify-center gap-2 rounded-2xl bg-accent px-4 py-3 text-sm font-bold text-white shadow-sm transition-colors hover:bg-accent/90"
            >
              <Link2 size={15} /> 添加系列
            </button>
          ) : null}
        </div>

        <div className="flex-1 overflow-y-auto p-5" aria-label="series 列表">
          <motion.div className="flex flex-col gap-4" variants={staggerContainer} initial="initial" animate="animate">
            {series.map((seriesItem) => {
              const processedCount = getProcessedCount(seriesItem);
              const latestVideo = seriesItem.videos.at(-1);

              return (
                <motion.button
                  key={seriesItem.id}
                  type="button"
                  variants={blurVariant}
                  whileHover="hover"
                  whileTap="tap"
                  className="workspace-panel group flex flex-col rounded-[1.5rem] border p-5 text-left hover:border-stone-300 dark:hover:border-white/10 hover:bg-white dark:hover:bg-neutral-800/80 hover:shadow-md transition-all cursor-pointer relative overflow-hidden"
                  onClick={() => onOpenSeries(seriesItem.id)}
                >
                  <div className="mb-4 flex items-start justify-between gap-3 relative z-10">
                    <span className="inline-flex items-center rounded-full bg-stone-100 dark:bg-neutral-900 border border-stone-200/50 dark:border-white/5 px-3 py-1 text-[11px] font-bold tracking-wide text-stone-600 dark:text-zinc-400 shadow-sm">
                      {seriesItem.videos.length} videos
                    </span>
                    <span className="motion-arrow-shift flex h-8 w-8 items-center justify-center rounded-full bg-stone-50 dark:bg-neutral-900 border border-stone-200/50 dark:border-white/5 text-stone-400 dark:text-zinc-500 transition-colors group-hover:bg-accent group-hover:border-accent group-hover:text-white shadow-sm">
                      <ArrowRight size={15} strokeWidth={2.5} />
                    </span>
                  </div>
                  <strong className="text-lg font-extrabold tracking-tight leading-tight text-stone-900 dark:text-stone-100 relative z-10 group-hover:text-accent transition-colors">{seriesItem.title}</strong>
                  <p className="mt-1 truncate font-mono text-[11px] font-medium text-stone-400 dark:text-zinc-500 relative z-10">videos/{seriesItem.id}/</p>

                  <div className="mt-5 border-t border-stone-200/60 dark:border-white/5 pt-4 text-xs relative z-10">
                    <span className="inline-flex items-center gap-2 font-bold text-stone-600 dark:text-zinc-300">
                      <PlayCircle size={14} className="text-accent" />
                      {processedCount} / {seriesItem.videos.length} 已处理
                    </span>
                    <span className="mt-2.5 inline-flex items-start gap-2 font-medium text-stone-500 dark:text-zinc-500 w-full">
                      <Sparkles size={13} className="mt-0.5 shrink-0 text-stone-400 dark:text-zinc-600" />
                      <span className="truncate">最近：{latestVideo?.title ?? "无"}</span>
                    </span>
                  </div>
                </motion.button>
              );
            })}
          </motion.div>
        </div>
      </section>
    );
  }

  // Non-compact (Full page view)
  return (
    <section className="p-8 xl:p-12 w-full max-w-7xl mx-auto flex flex-col h-full overflow-y-auto">
      {/* Header Container */}
      <div className="flex flex-col md:flex-row md:items-start justify-between gap-6 mb-12">
        <div className="max-w-2xl">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-stone-100 dark:bg-neutral-900 border border-stone-200 dark:border-white/5 w-fit shadow-sm mb-5">
            <span className="text-[10px] font-bold uppercase tracking-widest text-stone-600 dark:text-zinc-400">Videos Library</span>
          </div>
          <h2 className="text-4xl lg:text-5xl font-extrabold text-stone-900 dark:text-stone-100 mb-4 tracking-tight">All Shelves <span className="text-stone-400 dark:text-zinc-600 font-medium">(Series)</span></h2>
          <p className="text-stone-600 dark:text-zinc-400 text-[15px] font-medium leading-relaxed">
            首页总览所有的视频分类。点击进入某个分类后，可以查看具体视频、生成 AI 总结，并在右侧阅读核心要点。
          </p>
        </div>

        {/* Top Right Quick Stat */}
        <div className="flex-shrink-0">
          <span className="inline-flex items-center gap-2.5 px-5 py-2.5 rounded-2xl workspace-panel border shadow-sm font-bold text-stone-800 dark:text-stone-200">
            <LayoutGrid size={18} className="text-accent" />
            {series.length} 个分类
          </span>
        </div>
      </div>

      {/* Overview Stats Row */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-5 mb-12">
        <article className="flex flex-col p-8 rounded-[2rem] workspace-panel border shadow-sm relative overflow-hidden group">
          <span className="text-[11px] font-bold text-stone-500 dark:text-zinc-500 uppercase tracking-widest mb-3 relative z-10">系列总数</span>
          <strong className="text-5xl font-black tracking-tighter text-stone-900 dark:text-stone-100 relative z-10 transition-transform group-hover:scale-105 origin-left">{series.length}</strong>
        </article>
        <article className="flex flex-col p-8 rounded-[2rem] workspace-panel border shadow-sm relative overflow-hidden group">
          <span className="text-[11px] font-bold text-stone-500 dark:text-zinc-500 uppercase tracking-widest mb-3 relative z-10">视频总数</span>
          <strong className="text-5xl font-black tracking-tighter text-stone-900 dark:text-stone-100 relative z-10 transition-transform group-hover:scale-105 origin-left">{totalVideos}</strong>
        </article>
        <article className="workspace-panel border-accent/30 bg-accent/5 dark:bg-accent/10 flex flex-col p-8 rounded-[2rem] shadow-sm relative overflow-hidden group">
          <span className="text-[11px] font-bold text-accent/80 dark:text-accent/90 uppercase tracking-widest mb-3 relative z-10">已处理视频</span>
          <div className="flex items-center gap-4 relative z-10">
            <strong className="text-5xl font-black tracking-tighter text-accent transition-transform group-hover:scale-105 origin-left">{totalProcessed}</strong>
            <CheckCircle2 size={32} strokeWidth={2.5} className="text-accent ml-auto opacity-50" />
          </div>
        </article>
      </div>

      {/* Series Grid */}
      <motion.div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6" aria-label="series 列表" variants={staggerContainer} initial="initial" animate="animate">
        {series.map((seriesItem) => {
          const processedCount = getProcessedCount(seriesItem);
          const latestVideo = seriesItem.videos.at(-1);

          return (
            <motion.button
              key={seriesItem.id}
              type="button"
              variants={blurVariant}
              whileHover="hover"
              whileTap="tap"
              className="text-left group flex flex-col p-7 rounded-[2rem] workspace-panel border hover:border-accent/30 hover:bg-white dark:hover:bg-neutral-800/80 hover:shadow-lg transition-all outline-none focus:ring-4 focus:ring-accent/20 cursor-pointer"
              onClick={() => onOpenSeries(seriesItem.id)}
            >
              {/* Card Header */}
              <div className="flex justify-between items-start w-full mb-5">
                <span className="inline-flex items-center px-3 py-1 rounded-full bg-stone-100 dark:bg-neutral-900 border border-stone-200/50 dark:border-white/5 text-stone-600 dark:text-zinc-400 text-[11px] font-bold tracking-wide shadow-sm">
                  {seriesItem.videos.length} videos
                </span>
                <span className="motion-arrow-shift w-9 h-9 rounded-full bg-stone-50 dark:bg-neutral-900 border border-stone-200/50 dark:border-white/5 flex items-center justify-center text-stone-400 dark:text-zinc-500 group-hover:bg-accent group-hover:border-accent group-hover:text-white transition-colors shadow-sm">
                  <ArrowRight size={16} strokeWidth={2.5} />
                </span>
              </div>

              {/* Card Body */}
              <div className="flex flex-col gap-2 mb-8">
                <strong className="text-2xl font-extrabold tracking-tight text-stone-900 dark:text-stone-100 leading-tight group-hover:text-accent transition-colors">
                  {seriesItem.title}
                </strong>
                <p className="text-[12px] font-medium font-mono text-stone-400 dark:text-zinc-500 truncate">
                  videos/{seriesItem.id}/
                </p>
              </div>

              {/* Card Footer (Stats) */}
              <div className="flex flex-col gap-2.5 mt-auto pt-5 border-t border-stone-200/60 dark:border-white/5 w-full">
                <span className="inline-flex items-center gap-2.5 text-[13px] font-bold text-stone-600 dark:text-zinc-300">
                  <PlayCircle size={15} className="text-accent" />
                  {processedCount} / {seriesItem.videos.length} 已处理
                </span>
                <span className="inline-flex items-start gap-2.5 text-xs font-medium text-stone-500 dark:text-zinc-500">
                  <Sparkles size={14} className="text-stone-400 dark:text-zinc-600 shrink-0 mt-0.5" />
                  <span className="truncate">最近：{latestVideo?.title ?? "无"}</span>
                </span>
              </div>
            </motion.button>
          );
        })}
      </motion.div>
    </section>
  );
}
