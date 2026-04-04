import { Captions, LoaderCircle, Sparkles } from "lucide-react";

import { formatRange, formatTimestamp } from "../../../../shared/lib/time";
import { WorkspaceStateBlock } from "../shared/WorkspaceStateBlock";

export function WorkspaceOverviewView({
  ui,
  tools,
  summary,
  selectedVideo,
  selectedChapterId,
  summaryLoading,
  isGeneratingSelectedVideo,
}) {
  const hasSummary = Boolean(summary);

  if (!tools?.overview.generated) {
    return (
      <WorkspaceStateBlock
        eyebrow="AI Overview"
        title={selectedVideo.title}
        description="先在左侧点击生成，生成完成后这里会显示 AI 概况、章节纪要和关键结论。"
      >
        {isGeneratingSelectedVideo ? (
          <div className="motion-fade-up mt-6 w-full max-w-xl">
            <div className="motion-busy-button inline-flex items-center gap-2 rounded-full border border-stone-200 bg-white px-4 py-2 text-sm text-stone-600 shadow-sm">
              <LoaderCircle size={16} strokeWidth={2.2} className="animate-spin text-[#0070f3]" />
              正在生成概况...
            </div>
            <div className="workspace-elevated-panel mt-6 rounded-3xl border p-6">
              <div className="motion-shimmer h-3 w-24 rounded-full bg-stone-100 dark:bg-stone-800"></div>
              <div className="motion-shimmer mt-5 h-7 w-3/4 rounded-2xl bg-stone-100 dark:bg-stone-800"></div>
              <div className="motion-shimmer mt-4 h-4 w-full rounded-full bg-stone-100 dark:bg-stone-800"></div>
              <div className="motion-shimmer mt-3 h-4 w-5/6 rounded-full bg-stone-100 dark:bg-stone-800"></div>
              <div className="motion-shimmer mt-8 h-24 w-full rounded-[1.5rem] bg-stone-100 dark:bg-stone-800"></div>
            </div>
          </div>
        ) : null}
      </WorkspaceStateBlock>
    );
  }

  if (summaryLoading) {
    return (
      <WorkspaceStateBlock
        eyebrow="AI Overview"
        title="载入 AI 概况"
        description="正在读取已生成的概况结果。"
        loading
      />
    );
  }

  if (!hasSummary) {
    return null;
  }

  return (
    <div className="w-full max-w-3xl mx-auto flex flex-col gap-8 pb-32">
      <article className="workspace-accent-panel relative overflow-hidden rounded-3xl border p-6 text-stone-900 dark:text-stone-100">
        <div className="absolute top-0 right-0 p-4 opacity-10">
          <Sparkles size={64} />
        </div>
        <p className="relative z-10 mb-3 text-[10px] font-bold uppercase tracking-widest text-stone-500 dark:text-stone-400">
          Core Problem
        </p>
        <p className="relative z-10 text-base font-medium leading-relaxed">
          {summary.core_problem ?? "无核心问题描述。"}
        </p>
      </article>

      {ui.showTakeaways && summary.key_takeaways.length ? (
        <article className="workspace-muted-panel rounded-3xl border p-6">
          <p className="mb-3 text-[10px] font-bold uppercase tracking-widest text-stone-600 dark:text-zinc-400">Key Takeaways</p>
          <div className="flex flex-col gap-3">
            {summary.key_takeaways.map((takeaway) => (
              <div key={takeaway} className="flex items-start gap-3">
                <span className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-[#0070f3]"></span>
                <p className="text-sm leading-relaxed text-stone-700 dark:text-stone-300">{takeaway}</p>
              </div>
            ))}
          </div>
        </article>
      ) : null}

      <div className="mt-2 flex flex-col gap-4">
        <h2 className="mb-2 text-xl font-bold text-stone-800">章节纪要</h2>
        {(summary.chapters ?? []).map((chapter, index) => (
          <article
            key={chapter.id}
            id={chapter.id}
            className={`workspace-elevated-panel flex flex-col gap-4 rounded-3xl border p-5 transition-all duration-300 ${
              chapter.id === selectedChapterId
                ? "border-[#0070f3] shadow-md ring-2 ring-[#0070f3]/10"
                : "border-stone-200/70 dark:border-stone-800 hover:border-stone-300 dark:hover:border-stone-700 hover:bg-white dark:hover:bg-[#1f1f1f] hover:-translate-y-0.5 hover:shadow-[0_8px_20px_rgba(15,23,42,0.05)] dark:hover:shadow-[0_8px_20px_rgba(0,0,0,0.2)]"
            }`}
          >
            <div className="flex items-start justify-between gap-3">
              <div>
                <p className="mb-1.5 text-xs font-bold uppercase tracking-widest text-stone-600 dark:text-zinc-400">Chapter {index + 1}</p>
                <h3 className="text-lg font-bold leading-tight text-stone-900 dark:text-stone-100">{chapter.title}</h3>
              </div>
              <span className="shrink-0 rounded-lg bg-stone-100 px-2 py-1 text-xs font-mono font-bold text-stone-500 dark:bg-stone-900 dark:text-stone-400">
                {formatRange(chapter.start_seconds, chapter.end_seconds)}
              </span>
            </div>

            <p className="text-sm leading-relaxed text-stone-600 dark:text-stone-400">{chapter.summary}</p>

            <div className="mt-2 flex flex-col gap-2.5">
              {chapter.key_points.map((point) => (
                <div key={point} className="flex items-start gap-3">
                  <span className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-[#0070f3]"></span>
                  <p className="text-sm leading-relaxed text-stone-700 dark:text-stone-300">{point}</p>
                </div>
              ))}
            </div>

            {chapter.transcript_segments.length ? (
              <details className="group mt-1 rounded-2xl border border-stone-200/80 bg-stone-50/80 dark:border-stone-800 dark:bg-stone-950/60">
                <summary className="flex cursor-pointer list-none items-center justify-between gap-4 px-4 py-3">
                  <div className="flex items-center gap-3">
                    <span className="flex h-8 w-8 items-center justify-center rounded-xl bg-white text-[#0070f3] shadow-sm dark:bg-stone-900">
                      <Captions size={16} />
                    </span>
                    <div>
                      <p className="text-sm font-semibold text-stone-900 dark:text-stone-100">查看本章原文</p>
                      <p className="text-xs text-stone-500 dark:text-stone-400">{chapter.transcript_segments.length} 段转写</p>
                    </div>
                  </div>
                  <span className="text-xs font-semibold text-stone-500 dark:text-stone-400">
                    {formatRange(chapter.start_seconds, chapter.end_seconds)}
                  </span>
                </summary>

                <div className="border-t border-stone-200/80 px-4 py-4 dark:border-stone-800">
                  <div className="flex flex-col gap-3">
                    {chapter.transcript_segments.map((segment) => (
                      <div key={`${chapter.id}-${segment.start_seconds}-${segment.end_seconds}`} className="rounded-2xl bg-white/90 px-3 py-3 dark:bg-[#121212]">
                        <p className="text-[11px] font-bold uppercase tracking-widest text-stone-500 dark:text-stone-400">
                          {formatTimestamp(segment.start_seconds)} - {formatTimestamp(segment.end_seconds)}
                        </p>
                        <p className="mt-2 text-sm leading-relaxed text-stone-700 dark:text-stone-300">{segment.text}</p>
                      </div>
                    ))}
                  </div>
                </div>
              </details>
            ) : null}
          </article>
        ))}
      </div>
    </div>
  );
}
