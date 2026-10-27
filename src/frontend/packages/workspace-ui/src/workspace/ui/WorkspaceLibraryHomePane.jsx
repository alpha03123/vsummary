import { motion } from "framer-motion";
import { CheckCircle2, ChevronRight, Plus } from "lucide-react";

import { blurVariant, staggerContainer } from "../../lib/animations";
import { isBilibiliInboxSeries, isPlaygroundSeries, isSpecialSeries } from "../model/workspaceControllerConstants";

const PENDING_PREVIEW_LIMIT = 5;

// linked = 只导入了链接、按需下载处理，不算积压；已下载但未生成的才是「待生成」。
function videoState(video) {
  if (video.processed) return "processed";
  return video.status === "linked" ? "linked" : "pending";
}

function countVideoStates(videos) {
  const counts = { total: videos.length, processed: 0, pending: 0, linked: 0 };
  for (const video of videos) counts[videoState(video)] += 1;
  return counts;
}

function summarizeLibrary(library) {
  const series = library?.series ?? [];
  const allVideos = series.flatMap((item) => item.videos);
  const pendingVideos = series.flatMap((item) =>
    item.videos
      .filter((video) => videoState(video) === "pending")
      .map((video) => ({ video, series: item })),
  );

  const regularSeries = series.filter((item) => !isSpecialSeries(item));

  return {
    seriesCount: regularSeries.length,
    seriesTotals: countVideoStates(regularSeries.flatMap((item) => item.videos)),
    totals: countVideoStates(allVideos),
    bilibiliInbox: series.find(isBilibiliInboxSeries) ?? null,
    playground: series.find(isPlaygroundSeries) ?? { id: "__playground__", title: "Playground", videos: [], kind: "playground" },
    pendingVideos,
  };
}

function describeCounts(counts) {
  if (counts.total === 0) return "暂无视频";
  if (counts.processed === counts.total) return `${counts.total} 个视频 · 全部已生成`;
  const parts = [`${counts.total} 个视频`, `已生成 ${counts.processed}`];
  if (counts.pending > 0) parts.push(`待生成 ${counts.pending}`);
  if (counts.linked > 0) parts.push(`未下载 ${counts.linked}`);
  return parts.join(" · ");
}

function StateBar({ counts }) {
  if (counts.total === 0) return null;
  const segments = [
    { key: "processed", className: "bg-accent" },
    { key: "pending", className: "bg-accent/35" },
    { key: "linked", className: "bg-stone-300 dark:bg-zinc-700" },
  ];
  return (
    <div className="flex h-1.5 w-full gap-0.5 overflow-hidden rounded-full bg-stone-200/60 dark:bg-neutral-900/80">
      {segments.map(({ key, className }) =>
        counts[key] > 0 ? (
          <div key={key} className={className} style={{ width: `${(counts[key] / counts.total) * 100}%` }} />
        ) : null,
      )}
    </div>
  );
}

// 不传 onOpen 时是只读汇总行（例如「系列」，具体系列在侧栏里）。
function SourceRow({ title, description, counts, onOpen, action }) {
  const interactive = Boolean(onOpen);
  const body = (
    <>
      <div className="shrink-0 md:w-28">
        <strong className={`block text-[15px] font-bold text-stone-900 dark:text-stone-100 ${interactive ? "transition-colors group-hover:text-accent" : ""}`}>{title}</strong>
        <span className="text-xs text-stone-500 dark:text-zinc-500">{description}</span>
      </div>
      <div className="flex min-w-0 flex-1 flex-col gap-2">
        <span className="truncate text-xs font-semibold text-stone-600 dark:text-zinc-400">{describeCounts(counts)}</span>
        <StateBar counts={counts} />
      </div>
    </>
  );
  const bodyClassName = "flex min-w-0 flex-1 flex-col items-stretch gap-2 text-left md:flex-row md:items-center md:gap-6";

  return (
    <div className={`group flex items-center gap-4 rounded-2xl px-4 py-3.5 ${interactive ? "transition-colors hover:bg-white dark:hover:bg-neutral-800/60" : ""}`}>
      {interactive ? (
        <button type="button" onClick={onOpen} className={bodyClassName}>{body}</button>
      ) : (
        <div className={bodyClassName}>{body}</div>
      )}
      <div className="flex shrink-0 justify-end md:w-28">{action}</div>
      {interactive ? (
        <button
          type="button"
          onClick={onOpen}
          aria-label={`进入${title}`}
          className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-stone-400 transition-colors group-hover:bg-stone-200/60 group-hover:text-stone-700 dark:group-hover:bg-neutral-700 dark:group-hover:text-zinc-200"
        >
          <ChevronRight size={16} />
        </button>
      ) : (
        <span className="w-8 shrink-0" />
      )}
    </div>
  );
}

export function WorkspaceLibraryHomePane({ library, onSelectSeries, onSelectVideo, onAddPlaygroundVideo }) {
  const summary = summarizeLibrary(library);
  const { totals, seriesTotals, bilibiliInbox, playground, pendingVideos } = summary;
  const hiddenPendingCount = Math.max(0, pendingVideos.length - PENDING_PREVIEW_LIMIT);

  return (
    <motion.section
      key="library-home:pane"
      variants={blurVariant}
      initial="initial"
      animate="animate"
      exit="exit"
      className="flex-1 min-w-0 h-full overflow-y-auto relative z-10 border-l border-stone-200/80 dark:border-stone-800/90 bg-stone-50/30 dark:bg-transparent"
    >
      <motion.div
        variants={staggerContainer}
        initial="initial"
        animate="animate"
        className="w-full max-w-4xl mx-auto px-8 xl:px-10 py-6 xl:py-8 flex flex-col gap-5"
      >
        <motion.header variants={blurVariant} className="flex flex-wrap items-baseline justify-between gap-x-6 gap-y-1 px-1">
          <h2 className="text-2xl font-extrabold tracking-tight text-stone-900 dark:text-stone-100">概览</h2>
          <p className="text-sm font-semibold text-stone-500 dark:text-zinc-500">
            {totals.total} 个视频 · 已生成 {totals.processed}
          </p>
        </motion.header>

        <motion.article variants={blurVariant} className="workspace-panel rounded-[2rem] border border-stone-200 dark:border-white/5 p-3">
          <p className="px-4 pt-3 pb-2 text-xs font-bold text-stone-500 dark:text-zinc-500">来源</p>
          <div className="flex flex-col">
            {summary.seriesCount > 0 ? (
              <SourceRow title="系列" description={`${summary.seriesCount} 个系列`} counts={seriesTotals} />
            ) : null}
            {bilibiliInbox ? (
              <SourceRow
                title="B站导入"
                description="收藏夹与链接"
                counts={countVideoStates(bilibiliInbox.videos)}
                onOpen={() => onSelectSeries(bilibiliInbox.id)}
              />
            ) : null}
            <SourceRow
              title="排练场"
              description="非系列视频"
              counts={countVideoStates(playground.videos)}
              onOpen={() => onSelectSeries(playground.id)}
              action={onAddPlaygroundVideo ? (
                <button
                  type="button"
                  onClick={onAddPlaygroundVideo}
                  className="inline-flex shrink-0 items-center gap-1 rounded-full border border-stone-200 px-3 py-1.5 text-xs font-bold text-stone-600 transition-colors hover:border-accent/40 hover:text-accent dark:border-white/10 dark:text-zinc-400"
                >
                  <Plus size={13} /> 添加视频
                </button>
              ) : null}
            />
          </div>
          {totals.total > 0 ? (
            <div className="flex flex-wrap items-center gap-x-4 gap-y-1 px-4 pt-2 pb-3 text-[11px] font-semibold text-stone-500 dark:text-zinc-500">
              <span className="flex items-center gap-1.5 whitespace-nowrap"><span className="h-2 w-2 rounded-full bg-accent" />已生成</span>
              <span className="flex items-center gap-1.5 whitespace-nowrap"><span className="h-2 w-2 rounded-full bg-accent/35" />待生成</span>
              <span className="flex items-center gap-1.5 whitespace-nowrap"><span className="h-2 w-2 rounded-full bg-stone-300 dark:bg-zinc-700" />未下载（按需处理）</span>
            </div>
          ) : null}
        </motion.article>

        {pendingVideos.length === 0 && totals.total > 0 ? (
          <motion.p variants={blurVariant} className="flex items-center gap-2 px-5 text-sm font-semibold text-stone-500 dark:text-zinc-500">
            <CheckCircle2 size={16} className="shrink-0 text-accent" />
            没有待生成的视频
            {totals.linked > 0 ? <span className="font-medium">· {totals.linked} 个未下载的视频可在来源里按需处理</span> : null}
          </motion.p>
        ) : null}

        {pendingVideos.length > 0 ? (
          <motion.article variants={blurVariant} className="workspace-panel rounded-[2rem] border border-stone-200 dark:border-white/5 p-3">
            <p className="px-4 pt-3 pb-2 text-xs font-bold text-stone-500 dark:text-zinc-500">已下载，待生成 · {pendingVideos.length}</p>
            <ul className="flex flex-col">
              {pendingVideos.slice(0, PENDING_PREVIEW_LIMIT).map(({ video, series }) => (
                <li key={`${series.id}:${video.id}`}>
                  <button
                    type="button"
                    onClick={() => (onSelectVideo ? onSelectVideo(series.id, video.id) : onSelectSeries(series.id))}
                    className="group flex w-full items-center gap-4 rounded-2xl px-4 py-3 text-left transition-colors hover:bg-white dark:hover:bg-neutral-800/60"
                  >
                    <span className="min-w-0 flex-1 truncate text-sm font-semibold text-stone-800 transition-colors group-hover:text-accent dark:text-stone-200">
                      {video.title}
                    </span>
                    <span className="max-w-[12rem] shrink-0 truncate text-xs text-stone-500 dark:text-zinc-500">
                      {isBilibiliInboxSeries(series) ? "B站导入" : isPlaygroundSeries(series) ? "排练场" : series.title}
                    </span>
                    <ChevronRight size={15} className="shrink-0 text-stone-400 transition-colors group-hover:text-stone-700 dark:group-hover:text-zinc-200" />
                  </button>
                </li>
              ))}
            </ul>
            {hiddenPendingCount > 0 ? (
              <p className="px-4 pt-1 pb-3 text-xs text-stone-500 dark:text-zinc-500">还有 {hiddenPendingCount} 个，在对应来源里查看</p>
            ) : null}
          </motion.article>
        ) : null}
      </motion.div>
    </motion.section>
  );
}
