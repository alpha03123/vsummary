import { motion } from "framer-motion";
import { PlusCircle } from "lucide-react";

import { blurVariant, staggerContainer } from "../../../lib/animations";

function summarizeLibrary(library) {
  const series = library?.series ?? [];
  const visibleSeries = series.filter((item) => item.id !== "__playground__");
  const totalVideos = series.reduce((count, item) => count + item.videos.length, 0);
  const processedVideos = series.reduce(
    (count, item) => count + item.videos.filter((video) => video.processed).length,
    0,
  );

  return {
    seriesCount: visibleSeries.length,
    totalVideos,
    processedVideos,
    latestSeries: visibleSeries.slice(0, 4),
  };
}

export function WorkspaceLibraryHomePane({ library, onSelectSeries, onAddSeries, onAddPlaygroundVideo }) {
  const librarySummary = summarizeLibrary(library);
  const playgroundSeries = (library?.series ?? []).find((item) => item.id === "__playground__") ?? {
    id: "__playground__",
    title: "Playground",
    videos: [],
  };
  const playgroundVideoCount = playgroundSeries.videos.length;
  const playgroundProcessedCount = playgroundSeries.videos.filter((video) => video.processed).length;
  const progressPercentage = librarySummary.totalVideos > 0
    ? Math.round((librarySummary.processedVideos / librarySummary.totalVideos) * 100)
    : 0;
  const playgroundProgressPercentage = playgroundVideoCount > 0
    ? Math.round((playgroundProcessedCount / playgroundVideoCount) * 100)
    : 0;

  return (
    <motion.section
      key="library-home:pane"
      variants={blurVariant}
      initial="initial"
      animate="animate"
      exit="exit"
      className="flex-1 min-w-0 h-full overflow-y-auto relative z-10 border-l border-stone-200/80 dark:border-stone-800/90 bg-stone-50/30 dark:bg-transparent"
    >
      <div className="w-full max-w-5xl mx-auto px-8 xl:px-10 py-6 xl:py-8 flex min-h-full flex-col gap-5">

        {/* Header Section */}
        <motion.div variants={blurVariant} className="flex flex-col gap-3">

          <h2 className="text-3xl lg:text-4xl font-extrabold tracking-tight text-stone-900 dark:text-stone-100">
            Welcome to your{" "}
            <span className="text-stone-400 dark:text-zinc-500">Knowledge Base.</span>
          </h2>

        </motion.div>

        {/* Bento Grid Layout */}
        <motion.div variants={staggerContainer} initial="initial" animate="animate" className="grid grid-cols-1 md:grid-cols-12 gap-4 flex-1">

          {/* Main Progress Card (Spans 8 cols) */}
          <motion.article variants={blurVariant} className="md:col-span-8 workspace-elevated-panel rounded-[2rem] border border-stone-200 dark:border-white/5 p-6 flex flex-col justify-between overflow-hidden relative">
            <div className="relative z-10">
              <p className="text-[11px] font-bold uppercase tracking-widest text-stone-500 dark:text-zinc-500 mb-3 flex items-center gap-2">
                Processing Overview
              </p>
              <div className="flex items-baseline gap-3 mb-2">
                <h3 className="text-5xl font-black text-stone-900 dark:text-stone-100 tracking-tighter">{progressPercentage}%</h3>
                <p className="text-sm font-semibold text-stone-500 dark:text-zinc-400 pb-1">processed</p>
              </div>

              <div className="h-3 w-full bg-stone-200/60 dark:bg-neutral-900/80 rounded-full overflow-hidden mt-4 shadow-inner relative">
                <motion.div
                  initial={{ width: 0 }}
                  animate={{ width: `${progressPercentage}%` }}
                  transition={{ duration: 1.2, ease: [0.16, 1, 0.3, 1] }}
                  className="absolute top-0 left-0 h-full bg-accent rounded-full"
                />
              </div>
              <div className="flex justify-between items-center mt-3 text-xs font-semibold text-stone-500 dark:text-zinc-500">
                <span>已解析 {librarySummary.processedVideos} 个视频</span>
                <span>库内共计 {librarySummary.totalVideos} 个视频</span>
              </div>
            </div>
          </motion.article>

          {/* Quick Stats (Spans 4 cols) */}
          <motion.div variants={blurVariant} className="md:col-span-4 flex flex-col gap-4">
            <div className="workspace-panel flex-1 rounded-[2rem] border border-stone-200 dark:border-white/5 p-6 flex flex-col justify-center items-center text-center group">
              <span className="text-4xl font-black text-stone-900 dark:text-stone-100 mb-2 transition-transform group-hover:scale-105">{librarySummary.seriesCount}</span>
              <span className="text-[10px] font-bold uppercase tracking-widest text-stone-500 dark:text-zinc-500">Total Series</span>
            </div>
            <div className="workspace-panel flex-1 rounded-[2rem] border border-stone-200 dark:border-white/5 p-6 flex flex-col justify-center items-center text-center group">
              <span className="text-4xl font-black text-stone-900 dark:text-stone-100 mb-2 transition-transform group-hover:scale-105">{librarySummary.totalVideos}</span>
              <span className="text-[10px] font-bold uppercase tracking-widest text-stone-500 dark:text-zinc-500">Total Videos</span>
            </div>
          </motion.div>

          {/* Recent Shelves (Spans 7 cols) */}
          <motion.article variants={blurVariant} className="md:col-span-7 workspace-panel rounded-[2rem] border border-stone-200 dark:border-white/5 p-6">
            <div className="flex items-center justify-between mb-4">
              <p className="text-[11px] font-bold uppercase tracking-widest text-stone-500 dark:text-zinc-500">Recent Shelves</p>
              <span className="text-[10px] font-bold uppercase text-stone-500 dark:text-zinc-400 bg-stone-100 dark:bg-neutral-900 px-2.5 py-1 rounded-full border border-stone-200 dark:border-white/5 shadow-sm">Top {librarySummary.latestSeries.length}</span>
            </div>

            {librarySummary.latestSeries.length > 0 ? (
              <div className="grid grid-cols-1 gap-3">
                {librarySummary.latestSeries.map((seriesItem) => (
                  <motion.button
                    key={seriesItem.id}
                    variants={blurVariant}
                    whileHover={{ scale: 0.99 }}
                    whileTap={{ scale: 0.98 }}
                    onClick={() => onSelectSeries(seriesItem.id)}
                    className="group relative flex items-center justify-between p-4 rounded-2xl border border-stone-200/60 dark:border-white/5 bg-stone-50/50 dark:bg-neutral-900/50 hover:bg-white dark:hover:bg-neutral-800 transition-all text-left shadow-sm hover:shadow-md"
                  >
                    <div>
                      <strong className="block text-[14px] font-bold text-stone-900 dark:text-stone-100 group-hover:text-accent transition-colors">{seriesItem.title}</strong>
                      <span className="block text-xs font-semibold text-stone-500 dark:text-zinc-500 mt-1">{seriesItem.videos.length} 个视频片段</span>
                    </div>
                    <div className="w-8 h-8 rounded-full bg-stone-200/50 dark:bg-neutral-800 flex items-center justify-center opacity-0 group-hover:opacity-100 transition-all -translate-x-2 group-hover:translate-x-0 border border-stone-300/50 dark:border-white/5">
                      <span className="text-stone-600 dark:text-zinc-300 text-xs font-bold">→</span>
                    </div>
                  </motion.button>
                ))}
              </div>
            ) : (
              <div className="h-32 flex items-center justify-center border-2 border-dashed border-stone-200 dark:border-white/5 rounded-2xl">
                <p className="text-sm font-semibold text-stone-400">暂无阅读记录</p>
              </div>
            )}
          </motion.article>

          {/* Playground Card (Spans 5 cols) */}
          <motion.article variants={blurVariant} className="md:col-span-5 workspace-muted-panel rounded-[2rem] border border-stone-200 dark:border-white/5 p-6 relative overflow-hidden flex flex-col">
            <div className="absolute top-0 right-0 w-40 h-40 bg-accent/10 dark:bg-accent/[0.06] rounded-full blur-3xl -mr-10 -mt-10 pointer-events-none" />
            <p className="text-[11px] font-bold uppercase tracking-widest text-stone-500 dark:text-zinc-500 mb-4 relative z-10">Playground</p>
            <div className="relative z-10 flex flex-col gap-4 flex-1">
              <div>
                <h3 className="text-2xl font-extrabold tracking-tight text-stone-900 dark:text-stone-100">排练场</h3>
                <p className="mt-2 text-sm font-medium leading-relaxed text-stone-500 dark:text-zinc-400">
                  处理非系列视频
                </p>
              </div>
              <div className="mt-2">
                <div className="flex items-baseline gap-3 mb-2">
                  <h3 className="text-3xl font-black text-stone-900 dark:text-stone-100 tracking-tighter">{playgroundProgressPercentage}%</h3>
                  <p className="text-xs font-semibold text-stone-500 dark:text-zinc-400 pb-1">AI 处理率</p>
                </div>
                <div className="h-2.5 w-full bg-stone-200/60 dark:bg-neutral-900/80 rounded-full overflow-hidden mt-3 shadow-inner relative">
                  <motion.div
                    initial={{ width: 0 }}
                    animate={{ width: `${playgroundProgressPercentage}%` }}
                    transition={{ duration: 1.2, ease: [0.16, 1, 0.3, 1] }}
                    className="absolute top-0 left-0 h-full bg-accent rounded-full"
                  />
                </div>
                <div className="flex justify-between items-center mt-3 text-xs font-semibold text-stone-500 dark:text-zinc-500">
                  <span>已解析 {playgroundProcessedCount} 个视频</span>
                  <span>库内共计 {playgroundVideoCount} 个视频</span>
                </div>
              </div>
            </div>
            <div className="mt-4 relative z-10 flex flex-col gap-3">

              <button
                type="button"
                onClick={() => onSelectSeries(playgroundSeries.id)}
                className="inline-flex items-center justify-center gap-2 w-full px-4 py-3 rounded-2xl bg-accent hover:bg-accent/90 text-white text-sm font-bold shadow-sm transition-colors"
              >
                <PlusCircle size={15} /> 进入 Playground
              </button>
            </div>
          </motion.article>

        </motion.div>
      </div>
    </motion.section>
  );
}
