import { useEffect, useMemo, useState } from "react";
import { Captions, ChevronUp, Sparkles, X } from "lucide-react";

import { formatRange, formatTimestamp } from "../../../../shared/lib/time";

export function WorkspaceOverviewContent({ ui, summary, selectedChapterId = null, citationFocus = null, onSeek }) {
  const [previewImage, setPreviewImage] = useState(null);
  const canSeek = typeof onSeek === "function";
  const citationTarget = useMemo(
    () => resolveCitationTarget(summary, citationFocus),
    [summary, citationFocus],
  );

  useEffect(() => {
    if (!citationTarget) {
      return;
    }
    const transcriptDetails = document.getElementById(`overview-transcript-${citationTarget.chapterId}`);
    if (transcriptDetails) {
      transcriptDetails.open = true;
    }
    const target = document.getElementById(citationTarget.segmentId ?? citationTarget.chapterId);
    const frameId = window.requestAnimationFrame(() => {
      target?.scrollIntoView?.({ behavior: "smooth", block: "center" });
    });
    return () => window.cancelAnimationFrame(frameId);
  }, [citationTarget]);

  if (!summary) {
    return null;
  }

  return (
    <>
      <article className="workspace-accent-panel relative overflow-hidden rounded-3xl border p-6 text-stone-900 dark:text-stone-100">
        <div className="absolute top-0 right-0 p-4 opacity-10">
          <Sparkles size={64} />
        </div>
        <p className="relative z-10 mb-3 text-[10px] font-bold uppercase tracking-widest text-stone-600 dark:text-stone-400">
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
                <span className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-accent"></span>
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
              chapter.id === (citationTarget?.chapterId ?? selectedChapterId)
                ? "border-accent shadow-md ring-2 ring-accent/10"
                : "border-stone-200/70 dark:border-stone-800 hover:border-stone-300 dark:hover:border-stone-700 hover:bg-white dark:hover:bg-neutral-800 hover:-translate-y-0.5 hover:shadow-[0_8px_20px_rgba(15,23,42,0.05)] dark:hover:shadow-[0_8px_20px_rgba(0,0,0,0.2)]"
            }`}
          >
            <button
              type="button"
              disabled={!canSeek}
              onClick={() => onSeek?.({
                seconds: chapter.start_seconds,
                endSeconds: chapter.end_seconds,
                chapterTitle: chapter.title,
              })}
              className={`flex w-full items-start justify-between gap-3 rounded-2xl px-2 py-2 text-left transition-colors ${
                canSeek ? "hover:bg-stone-100/60 dark:hover:bg-neutral-800/60" : "cursor-default"
              }`}
            >
              <div>
                <p className="mb-1.5 text-xs font-bold uppercase tracking-widest text-stone-600 dark:text-zinc-400">Chapter {index + 1}</p>
                <h3 className="text-lg font-bold leading-tight text-stone-900 dark:text-stone-100">{chapter.title}</h3>
              </div>
              <span className="shrink-0 rounded-lg bg-stone-100 px-2 py-1 text-xs font-mono font-bold text-stone-600 dark:bg-stone-900 dark:text-stone-400">
                {formatRange(chapter.start_seconds, chapter.end_seconds)}
              </span>
            </button>

            <p className="text-sm leading-relaxed text-stone-600 dark:text-stone-400">{chapter.summary}</p>

            {chapter.image_url ? (
              <button
                type="button"
                onClick={() => setPreviewImage({ src: chapter.image_url, alt: `${chapter.title} 视频截图` })}
                className="group relative block w-full overflow-hidden rounded-lg border border-stone-200 bg-stone-100 text-left dark:border-stone-800 dark:bg-stone-950"
              >
                <img
                  src={chapter.image_url}
                  alt={`${chapter.title} 视频截图`}
                  className="aspect-video w-full object-cover transition-transform duration-200 group-hover:scale-[1.01]"
                />
              </button>
            ) : null}

            <div className="mt-2 flex flex-col gap-2.5">
              {chapter.key_points.map((point) => (
                <div key={point} className="flex items-start gap-3">
                  <span className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-accent"></span>
                  <p className="text-sm leading-relaxed text-stone-700 dark:text-stone-300">{point}</p>
                </div>
              ))}
            </div>

            {chapter.transcript_segments.length ? (
              <details id={`overview-transcript-${chapter.id}`} className="group mt-1 rounded-2xl border border-stone-200/80 bg-stone-50/80 dark:border-stone-800 dark:bg-stone-950/60">
                <summary className="flex cursor-pointer list-none items-center justify-between gap-4 px-4 py-3">
                  <div className="flex items-center gap-3">
                    <span className="flex h-8 w-8 items-center justify-center rounded-xl bg-white text-accent shadow-sm dark:bg-stone-900">
                      <Captions size={16} />
                    </span>
                    <div>
                      <p className="text-sm font-semibold text-stone-900 dark:text-stone-100">查看本章原文</p>
                      <p className="text-xs text-stone-600 dark:text-stone-400">{chapter.transcript_segments.length} 段转写</p>
                    </div>
                  </div>
                  <span className="text-xs font-semibold text-stone-600 dark:text-stone-400">
                    {formatRange(chapter.start_seconds, chapter.end_seconds)}
                  </span>
                </summary>

                <div className="border-t border-stone-200/80 px-4 py-4 dark:border-stone-800">
                  <div className="flex flex-col gap-3">
                    {chapter.transcript_segments.map((segment, segmentIndex) => (
                      <button
                        key={`${chapter.id}-${segment.start_seconds}-${segment.end_seconds}`}
                        id={`overview-transcript-segment-${chapter.id}-${segmentIndex}`}
                        type="button"
                        disabled={!canSeek}
                        onClick={() => onSeek?.({
                          seconds: segment.start_seconds,
                          endSeconds: segment.end_seconds,
                          chapterTitle: chapter.title,
                        })}
                        className={`block w-full scroll-mt-6 rounded-2xl bg-white/90 px-3 py-3 text-left transition-colors dark:bg-neutral-900 ${
                          citationTarget?.segmentId === `overview-transcript-segment-${chapter.id}-${segmentIndex}`
                            ? "ring-2 ring-accent/30"
                            : ""
                        } ${
                          canSeek ? "hover:bg-accent/5 dark:hover:bg-accent/10" : "cursor-default"
                        }`}
                      >
                        <p className="text-[11px] font-bold uppercase tracking-widest text-stone-600 dark:text-stone-400">
                          {formatTimestamp(segment.start_seconds)} - {formatTimestamp(segment.end_seconds)}
                        </p>
                        <p className="mt-2 text-sm leading-relaxed text-stone-700 dark:text-stone-300">{segment.text}</p>
                      </button>
                    ))}
                  </div>

                  <div className="mt-4 flex justify-center border-t border-stone-200/80 pt-3 dark:border-stone-800">
                    <button
                      type="button"
                      onClick={(event) => {
                        const transcriptDetails = event.currentTarget.closest("details");
                        if (!transcriptDetails) {
                          return;
                        }
                        transcriptDetails.open = false;
                        transcriptDetails.scrollIntoView({ behavior: "smooth", block: "nearest" });
                      }}
                      className="flex h-9 w-9 items-center justify-center rounded-full border border-stone-200 bg-white text-stone-600 transition-colors hover:border-accent/30 hover:bg-accent/5 hover:text-accent dark:border-stone-700 dark:bg-stone-900 dark:text-stone-300 dark:hover:border-accent/40 dark:hover:bg-accent/10"
                      aria-label="收起本章原文"
                      title="收起本章原文"
                    >
                      <ChevronUp size={18} />
                    </button>
                  </div>
                </div>
              </details>
            ) : null}
          </article>
        ))}
      </div>
      {previewImage ? <ScreenshotLightbox image={previewImage} onClose={() => setPreviewImage(null)} /> : null}
    </>
  );
}

function ScreenshotLightbox({ image, onClose }) {
  useEffect(() => {
    const handleKeyDown = (event) => {
      if (event.key === "Escape") {
        onClose();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [onClose]);

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 p-4"
      role="dialog"
      aria-modal="true"
      aria-label="视频截图预览"
      onMouseDown={onClose}
    >
      <div className="relative max-h-full max-w-5xl" onMouseDown={(event) => event.stopPropagation()}>
        <button
          type="button"
          onClick={onClose}
          className="absolute right-2 top-2 z-10 flex h-9 w-9 items-center justify-center rounded-full bg-black/60 text-white transition-colors hover:bg-black/80"
          aria-label="关闭截图预览"
          title="关闭"
          autoFocus
        >
          <X size={18} />
        </button>
        <img src={image.src} alt={image.alt} className="max-h-[calc(100vh-2rem)] max-w-full object-contain" />
      </div>
    </div>
  );
}

function resolveCitationTarget(summary, citationFocus) {
  if (!summary || !citationFocus) {
    return null;
  }
  const chapters = Array.isArray(summary.chapters) ? summary.chapters : [];
  const chapterById = citationFocus.chapterId
    ? chapters.find((chapter) => chapter.id === citationFocus.chapterId)
    : null;
  const chapterByTime = typeof citationFocus.seconds === "number"
    ? chapters.find((chapter) => citationFocus.seconds >= chapter.start_seconds && citationFocus.seconds <= chapter.end_seconds)
    : null;
  const segmentMatch = findNearestTranscriptSegment(chapters, citationFocus);
  const chapter = chapterById ?? chapterByTime ?? segmentMatch?.chapter;
  if (!chapter) {
    return null;
  }
  const segmentIndex = segmentMatch?.chapter.id === chapter.id ? segmentMatch.index : -1;
  return {
    chapterId: chapter.id,
    segmentId: segmentIndex >= 0 ? `overview-transcript-segment-${chapter.id}-${segmentIndex}` : null,
  };
}

function findNearestTranscriptSegment(chapters, citationFocus) {
  if (typeof citationFocus.seconds !== "number") {
    return null;
  }
  const citationStart = citationFocus.seconds;
  const citationEnd = typeof citationFocus.endSeconds === "number" ? citationFocus.endSeconds : citationStart;
  let closest = null;

  chapters.forEach((chapter) => {
    const segments = Array.isArray(chapter.transcript_segments) ? chapter.transcript_segments : [];
    segments.forEach((segment, index) => {
      const distance = intervalDistance(
        citationStart,
        citationEnd,
        segment.start_seconds,
        segment.end_seconds,
      );
      if (closest === null || distance < closest.distance) {
        closest = { chapter, index, distance };
      }
    });
  });
  return closest;
}

function intervalDistance(start, end, candidateStart, candidateEnd) {
  if (end < candidateStart) {
    return candidateStart - end;
  }
  if (start > candidateEnd) {
    return start - candidateEnd;
  }
  return 0;
}
