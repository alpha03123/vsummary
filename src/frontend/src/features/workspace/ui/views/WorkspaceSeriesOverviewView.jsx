import { useEffect, useState } from "react";
import { ExternalLink, ListFilter } from "lucide-react";

import { WorkspaceOverviewContent } from "./WorkspaceOverviewContent";
import { WorkspaceStateBlock } from "../shared/WorkspaceStateBlock";

export function WorkspaceSeriesOverviewView({
  activeSeries,
  ui,
  summariesByVideoId,
  loading,
  citationFocus,
  onOpenVideoOverview,
}) {
  const [selectedVideoId, setSelectedVideoId] = useState("all");
  const seriesVideos = activeSeries?.videos ?? [];
  const visibleVideos = selectedVideoId === "all"
    ? seriesVideos
    : seriesVideos.filter((video) => video.id === selectedVideoId);
  const overviewCount = seriesVideos.filter((video) => summariesByVideoId?.[video.id]).length;

  useEffect(() => {
    if (!citationFocus?.videoId) {
      return;
    }
    setSelectedVideoId("all");
  }, [citationFocus]);

  useEffect(() => {
    if (!citationFocus?.videoId || loading || selectedVideoId !== "all") {
      return;
    }
    document.getElementById(`series-overview-${citationFocus.videoId}`)?.scrollIntoView?.({
      behavior: "smooth",
      block: "center",
    });
  }, [citationFocus, loading, selectedVideoId]);

  if (loading) {
    return (
      <WorkspaceStateBlock
        eyebrow="Series AI Overview"
        title="正在读取视频概况"
        description="正在汇集系列中已生成的 AI 概况。"
        loading
      />
    );
  }

  if (!seriesVideos.length) {
    return (
      <WorkspaceStateBlock
        eyebrow="Series AI Overview"
        title="系列暂无视频"
        description="添加并处理视频后，这里会汇集各视频的 AI 概况。"
        dashed
      />
    );
  }

  return (
    <div className="mx-auto flex w-full max-w-3xl flex-col gap-8 pb-16">
      <div className="flex flex-wrap items-end justify-between gap-4 border-b border-stone-200/80 pb-5 dark:border-white/5">
        <div>
          <p className="text-[10px] font-bold uppercase tracking-widest text-stone-600 dark:text-stone-400">Series AI Overview</p>
          <p className="mt-2 text-sm text-stone-600 dark:text-stone-400">{overviewCount} / {seriesVideos.length} 视频概况</p>
        </div>
        <label className="flex min-w-52 flex-col gap-1.5 text-sm font-semibold text-stone-700 dark:text-stone-300">
          <span className="flex items-center gap-2 text-xs text-stone-500 dark:text-stone-400"><ListFilter size={14} />查看范围</span>
          <select
            aria-label="选择视频概况"
            value={selectedVideoId}
            onChange={(event) => setSelectedVideoId(event.target.value)}
            className="h-10 rounded-lg border border-stone-200 bg-white px-3 text-sm font-medium text-stone-800 outline-none transition-colors focus:border-accent dark:border-stone-700 dark:bg-neutral-900 dark:text-stone-100"
          >
            <option value="all">全部视频 AI 概况</option>
            {seriesVideos.map((video) => (
              <option key={video.id} value={video.id}>{video.title}</option>
            ))}
          </select>
        </label>
      </div>

      {visibleVideos.map((video) => {
        const summary = summariesByVideoId?.[video.id] ?? null;
        if (!summary) {
          return (
            <article id={`series-overview-${video.id}`} key={video.id} className="workspace-muted-panel rounded-lg border px-5 py-4">
              <h2 className="text-base font-bold text-stone-900 dark:text-stone-100">{video.title}</h2>
              <p className="mt-1 text-sm text-stone-600 dark:text-stone-400">尚未生成 AI 概况</p>
            </article>
          );
        }

        return (
          <section
            id={`series-overview-${video.id}`}
            key={video.id}
            className={`flex flex-col gap-6 border-b border-stone-200/80 pb-10 last:border-b-0 dark:border-white/5 ${
              citationFocus?.videoId === video.id ? "rounded-lg ring-2 ring-accent/20" : ""
            }`}
          >
            <div className="flex items-start justify-between gap-4">
              <div>
                <p className="text-[10px] font-bold uppercase tracking-widest text-stone-600 dark:text-stone-400">Video AI Overview</p>
                <h2 className="mt-1 text-xl font-bold text-stone-900 dark:text-stone-100">{summary.title ?? video.title}</h2>
              </div>
              <button
                type="button"
                onClick={() => onOpenVideoOverview?.(video.id)}
                className="inline-flex shrink-0 items-center gap-2 rounded-lg border border-stone-200 bg-white px-3 py-2 text-sm font-semibold text-stone-700 shadow-sm transition-colors hover:bg-stone-100 dark:border-stone-700 dark:bg-neutral-900 dark:text-stone-200 dark:hover:bg-neutral-800"
              >
                进入视频概况
                <ExternalLink size={15} />
              </button>
            </div>
            <WorkspaceOverviewContent ui={ui} summary={summary} />
          </section>
        );
      })}
    </div>
  );
}
