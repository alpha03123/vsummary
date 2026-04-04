import { motion } from "framer-motion";

import { blurVariant, staggerContainer } from "../../../lib/animations";
import { WorkspaceMetricCard } from "./shared/WorkspaceMetricCard";

function summarizeLibrary(library) {
  const series = library?.series ?? [];
  const totalVideos = series.reduce((count, item) => count + item.videos.length, 0);
  const processedVideos = series.reduce(
    (count, item) => count + item.videos.filter((video) => video.processed).length,
    0,
  );

  return {
    seriesCount: series.length,
    totalVideos,
    processedVideos,
    latestSeries: series.slice(0, 3),
  };
}

export function WorkspaceLibraryHomePane({ library, onSelectSeries }) {
  const librarySummary = summarizeLibrary(library);

  return (
    <motion.section
      key="library-home:pane"
      variants={blurVariant}
      initial="initial"
      animate="animate"
      exit="exit"
      className="w-[45vw] xl:w-[760px] shrink-0 h-full overflow-auto relative z-10 border-l border-stone-200/80 dark:border-stone-800/90 transition-all"
    >
      <div className="mx-auto flex h-full max-w-5xl flex-col gap-6 p-8 xl:p-10">
        <motion.div variants={blurVariant} initial="initial" animate="animate" className="workspace-hero-surface rounded-[2rem] border p-8">
          <p className="text-xs font-bold uppercase tracking-widest text-stone-600 dark:text-zinc-400">Information Panel</p>
          <h2 className="mt-3 text-4xl font-bold text-stone-900 dark:text-stone-100">Workspace 信息面板</h2>
          <p className="mt-4 max-w-3xl text-lg leading-relaxed text-stone-600 dark:text-stone-400">
            现在首页也能直接和整个知识库对话。右侧继续保留工作区总览，用来快速理解当前书架规模和入口分布。
          </p>
        </motion.div>

        <motion.div variants={staggerContainer} initial="initial" animate="animate" className="grid grid-cols-1 gap-4 md:grid-cols-3">
          <motion.div variants={blurVariant}>
            <WorkspaceMetricCard label="系列总数" value={librarySummary.seriesCount} />
          </motion.div>
          <motion.div variants={blurVariant}>
            <WorkspaceMetricCard label="视频总数" value={librarySummary.totalVideos} />
          </motion.div>
          <motion.div variants={blurVariant}>
            <WorkspaceMetricCard label="已处理视频" value={librarySummary.processedVideos} accent="info" />
          </motion.div>
        </motion.div>

        <motion.div variants={staggerContainer} initial="initial" animate="animate" className="grid grid-cols-1 gap-6 lg:grid-cols-[1.3fr_0.9fr]">
          <motion.article variants={blurVariant} className="workspace-muted-panel rounded-[2rem] border p-7">
            <p className="text-xs font-bold uppercase tracking-widest text-stone-500 dark:text-stone-400">How To Use</p>
            <div className="mt-4 flex flex-col gap-4 text-sm leading-relaxed text-stone-600 dark:text-stone-400">
              <p>1. 先在首页直接问整个知识库，快速确定应该看哪个主题或视频。</p>
              <p>2. 在左侧选择 series，进入该主题下的视频工作区。</p>
              <p>3. 进入视频后，再从工具页进入 AI概况、知识卡片、思维导图或笔记。</p>
            </div>
          </motion.article>

          <motion.article variants={blurVariant} className="workspace-muted-panel rounded-[2rem] border p-7">
            <p className="text-xs font-bold uppercase tracking-widest text-stone-500 dark:text-stone-400">Recent Shelves</p>
            <div className="mt-4 flex flex-col gap-3">
              {librarySummary.latestSeries.map((seriesItem) => (
                <motion.button
                  key={seriesItem.id}
                  type="button"
                  variants={blurVariant}
                  whileHover="hover"
                  whileTap="tap"
                  onClick={() => onSelectSeries(seriesItem.id)}
                  className="workspace-elevated-panel rounded-2xl border px-4 py-3 text-left hover:border-stone-300 dark:hover:border-white/16 hover:bg-white dark:hover:bg-[#1f1f1f] hover:shadow-[0_8px_20px_rgba(15,23,42,0.05)] dark:hover:shadow-[0_8px_20px_rgba(0,0,0,0.2)]"
                >
                  <strong className="block text-sm font-semibold text-stone-900 dark:text-stone-100">{seriesItem.title}</strong>
                  <span className="mt-1 block text-xs text-stone-500 dark:text-stone-400">{seriesItem.videos.length} 个视频</span>
                </motion.button>
              ))}
            </div>
          </motion.article>
        </motion.div>
      </div>
    </motion.section>
  );
}
