import { ArrowRight, FolderKanban, PlayCircle, Sparkles, LayoutGrid, CheckCircle2 } from "lucide-react";
import { motion } from "framer-motion";
import { staggerContainer, blurVariant } from "../../../lib/animations";

function getProcessedCount(series) {
  return series.videos.filter((video) => video.processed).length;
}

export function WorkspaceSeriesGrid({ library, onOpenSeries, compact = false }) {
  const series = library?.series ?? [];

  if (!series.length) {
    return (
      <section className="flex flex-col items-center justify-center min-h-[60vh] max-w-2xl mx-auto text-center p-12 bg-white rounded-3xl border border-stone-200 border-dashed m-6">
        <div className="w-16 h-16 bg-stone-100 rounded-2xl flex items-center justify-center text-stone-400 mb-6">
          <FolderKanban size={32} />
        </div>
        <p className="text-xs font-bold text-stone-600 tracking-widest uppercase mb-4">Videos Library</p>
        <h2 className="text-3xl font-bold text-stone-800 mb-4">还没有分类 (Series)</h2>
        <p className="text-stone-500 leading-relaxed text-lg">
          请先在 <code className="bg-stone-100 px-2 py-1 rounded text-stone-700 font-mono text-sm mx-1">videos/&lt;series&gt;/</code> 目录中放入视频文件，首页会自动识别每个分类。
        </p>
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
        <div className="border-b border-stone-100 dark:border-stone-800 px-5 pb-4 pt-5">
          <p className="text-[10px] font-bold uppercase tracking-widest text-stone-600 dark:text-zinc-400 mb-1">Series Shelf</p>
          <h2 className="text-xl font-bold text-stone-900 dark:text-stone-100">所有书架</h2>
          <p className="mt-2 text-sm leading-relaxed text-stone-500 dark:text-stone-400">
            这里直接承载首页的 series 主内容。点击一个书架进入该系列的视频工作区。
          </p>
          <div className="mt-4 grid grid-cols-2 gap-2 text-xs">
            <div className="workspace-muted-panel rounded-2xl border px-3 py-2">
              <span className="block text-stone-400 dark:text-stone-500">分类</span>
              <strong className="text-stone-800 dark:text-stone-100">{series.length}</strong>
            </div>
            <div className="workspace-accent-panel rounded-2xl border px-3 py-2">
              <span className="block text-stone-600 dark:text-zinc-400">已处理</span>
              <strong className="text-stone-900 dark:text-white">{totalProcessed}</strong>
            </div>
          </div>
        </div>

        <div className="flex-1 overflow-y-auto p-4" aria-label="series 列表">
        <motion.div className="flex flex-col gap-3" variants={staggerContainer} initial="initial" animate="animate">
            {series.map((seriesItem, index) => {
              const processedCount = getProcessedCount(seriesItem);
              const latestVideo = seriesItem.videos.at(-1);

              return (
                <motion.button
                  key={seriesItem.id}
                  type="button"
                  variants={blurVariant}
                  whileHover="hover"
                  whileTap="tap"
                  className="workspace-muted-panel group flex flex-col rounded-[1.5rem] border p-5 text-left hover:border-stone-300 dark:hover:border-white/16 hover:bg-white dark:hover:bg-[#1f1f1f] hover:shadow-[0_10px_24px_rgba(15,23,42,0.08)] dark:hover:shadow-[0_10px_24px_rgba(0,0,0,0.28)] cursor-pointer"
                  onClick={() => onOpenSeries(seriesItem.id)}
                >
                  <div className="mb-3 flex items-start justify-between gap-3">
                    <span className="inline-flex items-center rounded-full bg-stone-100 dark:bg-stone-800 px-3 py-1 text-[11px] font-bold tracking-wide text-stone-600 dark:text-stone-300">
                      {seriesItem.videos.length} videos
                    </span>
                    <span className="motion-arrow-shift flex h-8 w-8 items-center justify-center rounded-full bg-stone-50 dark:bg-[#111111] text-stone-400 dark:text-stone-500 transition-colors group-hover:bg-sky-50 dark:group-hover:bg-sky-950/30 group-hover:text-[#0070f3]">
                      <ArrowRight size={17} />
                    </span>
                  </div>
                  <strong className="text-xl font-bold leading-tight text-stone-900 dark:text-stone-100">{seriesItem.title}</strong>
                  <p className="mt-1 truncate font-mono text-xs text-stone-400 dark:text-stone-500">videos/{seriesItem.id}/</p>
                  <div className="mt-4 border-t border-stone-100 dark:border-stone-800 pt-3 text-xs">
                    <span className="inline-flex items-center gap-2 font-semibold text-stone-600 dark:text-stone-300">
                      <PlayCircle size={13} className="text-[#0070f3]" />
                      {processedCount} / {seriesItem.videos.length} 已处理
                    </span>
                    <span className="mt-2 inline-flex items-start gap-2 text-stone-500 dark:text-stone-400">
                      <Sparkles size={13} className="mt-0.5 shrink-0 text-stone-400 dark:text-zinc-500" />
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

  return (
    <section className="p-6 md:p-10 w-full max-w-7xl mx-auto flex flex-col h-full">
      {/* Header Container */}
      <div className="flex flex-col md:flex-row md:items-start justify-between gap-6 mb-10">
        <div className="max-w-2xl">
          <p className="text-xs font-bold text-stone-600 tracking-widest uppercase mb-2">Videos Library</p>
          <h2 className="text-4xl font-bold text-stone-900 mb-4">所有书架 (Series)</h2>
          <p className="text-stone-600 text-lg leading-relaxed">
            首页总览所有的视频分类。点击进入某个分类后，可以查看具体视频、生成 AI 总结，并在右侧阅读核心要点。
          </p>
        </div>
        
        {/* Top Right Quick Stat */}
        <div className="flex-shrink-0">
          <span className="inline-flex items-center gap-2 px-4 py-2 rounded-2xl bg-white border border-stone-200 text-stone-700 shadow-sm font-semibold">
            <LayoutGrid size={18} className="text-[#0070f3]" />
            {series.length} 个分类
          </span>
        </div>
      </div>

      {/* Overview Stats Row */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-10">
        <article className="flex flex-col p-6 rounded-3xl bg-white border border-stone-200 shadow-sm">
          <span className="text-sm font-semibold text-stone-500 uppercase tracking-widest mb-2">系列总数</span>
          <strong className="text-3xl font-bold text-stone-900">{series.length}</strong>
        </article>
        <article className="flex flex-col p-6 rounded-3xl bg-white border border-stone-200 shadow-sm">
          <span className="text-sm font-semibold text-stone-500 uppercase tracking-widest mb-2">视频总数</span>
          <strong className="text-3xl font-bold text-stone-900">{totalVideos}</strong>
        </article>
        <article className="workspace-accent-panel flex flex-col p-6 rounded-3xl border shadow-sm">
          <span className="text-sm font-semibold text-stone-700 dark:text-zinc-300 uppercase tracking-widest mb-2">已处理视频</span>
          <div className="flex items-center gap-3">
             <strong className="text-3xl font-bold text-stone-900 dark:text-white">{totalProcessed}</strong>
             <CheckCircle2 size={24} className="text-[#0070f3]" />
          </div>
        </article>
      </div>

      {/* Series Grid */}
      <motion.div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5" aria-label="series 列表" variants={staggerContainer} initial="initial" animate="animate">
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
              className="text-left group flex flex-col p-6 rounded-3xl bg-white border-2 border-stone-100 hover:border-[#0070f3]/30 hover:bg-white hover:shadow-[0_14px_30px_rgba(15,23,42,0.08)] outline-none focus:ring-4 focus:ring-[#0070f3]/20"
              onClick={() => onOpenSeries(seriesItem.id)}
            >
              {/* Card Header */}
              <div className="flex justify-between items-start w-full mb-4">
                <span className="inline-flex items-center px-3 py-1 rounded-full bg-stone-100 text-stone-600 text-xs font-bold tracking-wide">
                  {seriesItem.videos.length} videos
                </span>
                <span className="motion-arrow-shift w-8 h-8 rounded-full bg-stone-50 flex items-center justify-center text-stone-400 group-hover:bg-sky-50 group-hover:text-[#0070f3] transition-colors">
                  <ArrowRight size={18} />
                </span>
              </div>
              
              {/* Card Body */}
              <div className="flex flex-col gap-2 mb-6">
                <strong className="text-2xl font-bold text-stone-900 leading-tight">
                  {seriesItem.title}
                </strong>
                <p className="text-sm font-mono text-stone-400 truncate">
                  videos/{seriesItem.id}/
                </p>
              </div>
              
              {/* Card Footer (Stats) */}
              <div className="flex flex-col gap-2 mt-auto pt-4 border-t border-stone-100 w-full">
                <span className="inline-flex items-center gap-2 text-xs font-semibold text-stone-600">
                  <PlayCircle size={14} className="text-[#0070f3]" />
                  {processedCount} / {seriesItem.videos.length} 已处理
                </span>
                <span className="inline-flex items-start gap-2 text-xs text-stone-500">
                  <Sparkles size={14} className="text-stone-400 shrink-0 mt-0.5" />
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
