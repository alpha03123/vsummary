import { useEffect, useState } from "react";
import { ExternalLink, Sparkles } from "lucide-react";

import { WorkspaceOverviewContent } from "./WorkspaceOverviewContent";
import { WorkspaceStateBlock } from "../shared/WorkspaceStateBlock";
import { WorkspaceVideoScopePicker } from "../shared/WorkspaceVideoScopePicker";

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
  const showingAll = selectedVideoId === "all";
  const visibleVideos = showingAll
    ? seriesVideos
    : seriesVideos.filter((video) => video.id === selectedVideoId);

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
    <div className="mx-auto flex w-full max-w-3xl flex-col gap-8 pb-24">
      <div className="flex border-b border-stone-200/80 pb-5 dark:border-white/5">
        <WorkspaceVideoScopePicker
          videos={seriesVideos}
          value={selectedVideoId}
          onChange={setSelectedVideoId}
        />
      </div>

      {visibleVideos.map((video) => {
        const summary = summariesByVideoId?.[video.id] ?? null;

        if (!summary) {
          return (
            <article
              id={`series-overview-${video.id}`}
              key={video.id}
              className="workspace-muted-panel flex flex-wrap items-center justify-between gap-3 rounded-2xl border px-5 py-4"
            >
              <div className="min-w-0">
                <h2 className="truncate text-base font-bold text-stone-900 dark:text-stone-100">{video.title}</h2>
                <p className="mt-1 text-sm text-stone-600 dark:text-stone-400">尚未生成 AI 概况</p>
              </div>
              <button
                type="button"
                onClick={() => onOpenVideoOverview?.(video.id)}
                className="inline-flex shrink-0 items-center gap-2 rounded-xl border border-accent/25 bg-accent/5 px-3 py-2 text-sm font-semibold text-accent transition-colors hover:bg-accent/10"
              >
                <Sparkles size={15} aria-hidden="true" />
                去生成概况
              </button>
            </article>
          );
        }

        const title = summary.title ?? video.title;

        return (
          <section
            id={`series-overview-${video.id}`}
            key={video.id}
            className={`flex flex-col gap-6 border-b border-stone-200/80 pb-10 last:border-b-0 dark:border-white/5 ${
              citationFocus?.videoId === video.id ? "rounded-2xl ring-2 ring-accent/20" : ""
            }`}
          >
            <div
              className={`flex items-center justify-between gap-4 ${
                showingAll
                  ? "sticky top-0 z-20 border-b border-stone-200/70 bg-white/85 py-3 backdrop-blur dark:border-white/5 dark:bg-neutral-950/85"
                  : ""
              }`}
            >
              <h2 className="min-w-0 truncate text-xl font-bold text-stone-900 dark:text-stone-100">{title}</h2>
              <button
                type="button"
                onClick={() => onOpenVideoOverview?.(video.id)}
                className="inline-flex shrink-0 items-center gap-1.5 rounded-xl px-2.5 py-1.5 text-sm font-medium text-stone-600 transition-colors hover:bg-stone-100 hover:text-stone-900 dark:text-stone-400 dark:hover:bg-neutral-800 dark:hover:text-stone-100"
              >
                进入视频概况
                <ExternalLink size={14} aria-hidden="true" />
              </button>
            </div>
            <WorkspaceOverviewContent ui={ui} summary={summary} sectionHeadingLevel={3} />
          </section>
        );
      })}
    </div>
  );
}
