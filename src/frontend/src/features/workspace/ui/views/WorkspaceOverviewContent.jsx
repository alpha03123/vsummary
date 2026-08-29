import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { useVirtualizer } from "@tanstack/react-virtual";
import { AlertTriangle, Captions, ChevronUp, Minus, Plus, Sparkles, X } from "lucide-react";

import { formatRange, formatTimestamp } from "../../../../shared/lib/time";

export function WorkspaceOverviewContent({
  ui,
  summary,
  playbackTime = null,
  selectedChapterId = null,
  citationFocus = null,
  onSeek,
  sectionHeadingLevel = 2,
}) {
  const [previewImage, setPreviewImage] = useState(null);
  const [expandedTranscriptChapters, setExpandedTranscriptChapters] = useState(() => new Set());
  const transcriptListRefs = useRef(new Map());
  const canSeek = typeof onSeek === "function";
  const SectionHeading = `h${sectionHeadingLevel}`;
  const ChapterHeading = `h${Math.min(sectionHeadingLevel + 1, 6)}`;
  const citationTarget = useMemo(
    () => resolveCitationTarget(summary, citationFocus),
    [summary, citationFocus],
  );
  const playbackTarget = useMemo(
    () => findPlaybackTarget(summary, playbackTime),
    [summary, playbackTime],
  );
  const hasPlaybackTime = Number.isFinite(playbackTime);
  const activeChapterId = hasPlaybackTime
    ? playbackTarget?.chapterId ?? null
    : citationTarget?.chapterId ?? selectedChapterId;
  const registerTranscriptList = useCallback((chapterId, list) => {
    if (list) {
      transcriptListRefs.current.set(chapterId, list);
      return;
    }
    transcriptListRefs.current.delete(chapterId);
  }, []);

  useEffect(() => {
    if (!citationTarget) {
      return;
    }
    setExpandedTranscriptChapters((current) => {
      if (current.has(citationTarget.chapterId)) {
        return current;
      }
      const next = new Set(current);
      next.add(citationTarget.chapterId);
      return next;
    });
  }, [citationTarget]);

  useEffect(() => {
    if (!citationTarget || !expandedTranscriptChapters.has(citationTarget.chapterId)) {
      return;
    }

    const frameId = window.requestAnimationFrame(() => {
      const transcriptDetails = document.getElementById(`overview-transcript-${citationTarget.chapterId}`);
      transcriptDetails?.scrollIntoView?.({ behavior: "smooth", block: "center" });
      const transcriptList = transcriptListRefs.current.get(citationTarget.chapterId);
      if (Number.isInteger(citationTarget.segmentIndex) && transcriptList) {
        transcriptList.scrollToIndex(citationTarget.segmentIndex);
        return;
      }
      document.getElementById(citationTarget.segmentId ?? citationTarget.chapterId)?.scrollIntoView?.({
        behavior: "smooth",
        block: "center",
      });
    });
    return () => window.cancelAnimationFrame(frameId);
  }, [citationTarget, expandedTranscriptChapters]);

  if (!summary) {
    return null;
  }

  return (
    <>
      <article className="workspace-accent-panel relative overflow-hidden rounded-2xl border p-6 text-stone-900 dark:text-stone-100">
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

      {summary.generationWarnings?.length ? (
        <div role="alert" className="flex items-start gap-3 border-l-4 border-warning bg-warning-subtle px-4 py-3 text-sm text-stone-700 dark:text-stone-200">
          <AlertTriangle size={18} className="mt-0.5 shrink-0 text-warning" aria-hidden="true" />
          <div className="space-y-1">
            {summary.generationWarnings.map((warning) => <p key={warning}>{warning}</p>)}
          </div>
        </div>
      ) : null}

      {ui.showTakeaways && summary.key_takeaways.length ? (
        <article className="workspace-muted-panel rounded-2xl border p-6">
          <p className="mb-3 text-[10px] font-bold uppercase tracking-widest text-stone-600 dark:text-stone-400">Key Takeaways</p>
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
        <SectionHeading className="mb-2 text-xl font-bold text-stone-900 dark:text-stone-100">章节纪要</SectionHeading>
        {(summary.chapters ?? []).map((chapter, index) => (
          <article
            key={chapter.id}
            id={chapter.id}
            className={`workspace-elevated-panel flex flex-col gap-4 rounded-2xl border p-5 transition-all duration-300 ${
              chapter.id === activeChapterId && !hasPlaybackTime
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
                <p className="mb-1.5 text-xs font-bold uppercase tracking-widest text-stone-600 dark:text-stone-400">Chapter {index + 1}</p>
                <ChapterHeading className="text-lg font-bold leading-tight text-stone-900 dark:text-stone-100">{chapter.title}</ChapterHeading>
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
              <details
                id={`overview-transcript-${chapter.id}`}
                open={expandedTranscriptChapters.has(chapter.id)}
                className={`group mt-1 rounded-2xl border border-stone-200/80 bg-stone-50/80 transition-all dark:border-stone-800 dark:bg-stone-950/60 ${
                  hasPlaybackTime && playbackTarget?.chapterId === chapter.id && !expandedTranscriptChapters.has(chapter.id)
                    ? "border-2 border-accent bg-accent/10 shadow-md ring-2 ring-accent/30 dark:bg-accent/15"
                    : ""
                }`}
              >
                <summary
                  className="flex cursor-pointer list-none items-center justify-between gap-4 px-4 py-3"
                  onClick={(event) => {
                    event.preventDefault();
                    setExpandedTranscriptChapters((current) => {
                      const next = new Set(current);
                      if (next.has(chapter.id)) next.delete(chapter.id);
                      else next.add(chapter.id);
                      return next;
                    });
                  }}
                >
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

                {expandedTranscriptChapters.has(chapter.id) ? (
                  <WorkspaceTranscriptList
                    chapterId={chapter.id}
                    chapterTitle={chapter.title}
                    segments={chapter.transcript_segments}
                    canSeek={canSeek}
                    highlightedSegmentIndex={
                      hasPlaybackTime && playbackTarget?.chapterId === chapter.id
                        ? playbackTarget.segmentIndex
                        : !hasPlaybackTime && citationTarget?.chapterId === chapter.id
                          ? citationTarget.segmentIndex
                          : null
                    }
                    onSeek={onSeek}
                    onRegister={registerTranscriptList}
                    onCollapse={() => {
                      setExpandedTranscriptChapters((current) => {
                        if (!current.has(chapter.id)) {
                          return current;
                        }
                        const next = new Set(current);
                        next.delete(chapter.id);
                        return next;
                      });
                    }}
                  />
                ) : null}
              </details>
            ) : null}
          </article>
        ))}
      </div>
      {previewImage ? <ScreenshotLightbox image={previewImage} onClose={() => setPreviewImage(null)} /> : null}
    </>
  );
}

function WorkspaceTranscriptList({
  chapterId,
  chapterTitle,
  segments,
  canSeek,
  highlightedSegmentIndex,
  onSeek,
  onRegister,
  onCollapse,
}) {
  const scrollRef = useRef(null);
  const virtualizer = useVirtualizer({
    count: segments.length,
    getScrollElement: () => scrollRef.current,
    estimateSize: () => 84,
    overscan: 8,
    initialRect: { width: 0, height: 480 },
    getItemKey: (index) => `${segments[index].start_seconds}-${segments[index].end_seconds}`,
  });
  const virtualRows = virtualizer.getVirtualItems();
  const visibleRows = virtualRows.length > 0
    ? virtualRows
    : Array.from({ length: Math.min(segments.length, 10) }, (_, index) => ({
      index,
      key: `initial-${index}`,
      start: index * 84,
    }));
  const totalSize = Math.max(virtualizer.getTotalSize(), segments.length * 84);

  useEffect(() => {
    onRegister(chapterId, {
      scrollToIndex(index) {
        virtualizer.scrollToIndex(index, { align: "center" });
      },
    });
    return () => onRegister(chapterId, null);
  }, [chapterId, onRegister, virtualizer]);

  return (
    <div className="border-t border-stone-200/80 px-4 py-4 dark:border-stone-800">
      <div ref={scrollRef} className="max-h-[min(60vh,42rem)] overflow-y-auto overscroll-contain pr-1">
        <div className="relative w-full" style={{ height: `${totalSize}px` }}>
          {visibleRows.map((virtualRow) => {
            const segment = segments[virtualRow.index];
            const isHighlighted = highlightedSegmentIndex === virtualRow.index;
            return (
              <div
                key={virtualRow.key}
                ref={virtualizer.measureElement}
                data-index={virtualRow.index}
                className="absolute left-0 top-0 w-full pb-3"
                style={{ transform: `translateY(${virtualRow.start}px)` }}
              >
                <button
                  id={`overview-transcript-segment-${chapterId}-${virtualRow.index}`}
                  type="button"
                  disabled={!canSeek}
                  onClick={() => onSeek?.({
                    seconds: segment.start_seconds,
                    endSeconds: segment.end_seconds,
                    chapterTitle,
                  })}
                  className={`block w-full scroll-mt-6 rounded-2xl bg-white/90 px-3 py-3 text-left transition-colors dark:bg-neutral-900 ${
                    isHighlighted ? "border-2 border-accent bg-accent/5 shadow-[inset_0_0_0_1px_rgba(99,102,241,0.2)] dark:bg-accent/10" : ""
                  } ${canSeek ? "hover:bg-accent/5 dark:hover:bg-accent/10" : "cursor-default"}`}
                >
                  <p className="text-[11px] font-bold uppercase tracking-widest text-stone-600 dark:text-stone-400">
                    {formatTimestamp(segment.start_seconds)} - {formatTimestamp(segment.end_seconds)}
                  </p>
                  <p className="mt-2 text-sm leading-relaxed text-stone-700 dark:text-stone-300">{segment.text}</p>
                </button>
              </div>
            );
          })}
        </div>
      </div>

      <div className="mt-4 flex justify-center border-t border-stone-200/80 pt-3 dark:border-stone-800">
        <button
          type="button"
          onClick={onCollapse}
          className="flex h-9 w-9 items-center justify-center rounded-full border border-stone-200 bg-white text-stone-600 transition-colors hover:border-accent/30 hover:bg-accent/5 hover:text-accent dark:border-stone-700 dark:bg-stone-900 dark:text-stone-300 dark:hover:border-accent/40 dark:hover:bg-accent/10"
          aria-label="收起本章原文"
          title="收起本章原文"
        >
          <ChevronUp size={18} />
        </button>
      </div>
    </div>
  );
}

function findPlaybackTarget(summary, playbackTime) {
  if (!summary || !Number.isFinite(playbackTime)) {
    return null;
  }
  const chapters = Array.isArray(summary.chapters) ? summary.chapters : [];
  for (const chapter of chapters) {
    if (playbackTime < chapter.start_seconds || playbackTime > chapter.end_seconds) {
      continue;
    }
    const segments = Array.isArray(chapter.transcript_segments) ? chapter.transcript_segments : [];
    const segmentIndex = segments.findIndex(
      (segment) => playbackTime >= segment.start_seconds && playbackTime <= segment.end_seconds,
    );
    return {
      chapterId: chapter.id,
      segmentId: segmentIndex >= 0 ? `overview-transcript-segment-${chapter.id}-${segmentIndex}` : null,
      segmentIndex: segmentIndex >= 0 ? segmentIndex : null,
    };
  }
  return null;
}

const MIN_SCALE = 0.25;
const MAX_SCALE = 8;

function clampScale(value) {
  return Math.min(MAX_SCALE, Math.max(MIN_SCALE, value));
}

function ScreenshotLightbox({ image, onClose }) {
  const [scale, setScale] = useState(1);
  const [offset, setOffset] = useState({ x: 0, y: 0 });
  const [dragging, setDragging] = useState(false);
  const containerRef = useRef(null);
  const dragOrigin = useRef(null);

  const reset = useCallback(() => {
    setScale(1);
    setOffset({ x: 0, y: 0 });
  }, []);

  const zoom = useCallback((delta) => {
    setScale((current) => {
      const next = clampScale(current + delta);
      if (next === 1) {
        setOffset({ x: 0, y: 0 });
      }
      return next;
    });
  }, []);

  useEffect(() => {
    const handleKeyDown = (event) => {
      if (event.key === "Escape") {
        onClose();
        return;
      }
      if (event.key === "+" || event.key === "=") {
        event.preventDefault();
        zoom(0.25);
        return;
      }
      if (event.key === "-") {
        event.preventDefault();
        zoom(-0.25);
        return;
      }
      if (event.key === "0") {
        event.preventDefault();
        reset();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [onClose, reset, zoom]);

  // Native listener so preventDefault actually blocks page zoom/scroll.
  useEffect(() => {
    const node = containerRef.current;
    if (!node) return undefined;
    const handleWheel = (event) => {
      event.preventDefault();
      zoom(event.deltaY < 0 ? 0.2 : -0.2);
    };
    node.addEventListener("wheel", handleWheel, { passive: false });
    return () => node.removeEventListener("wheel", handleWheel);
  }, [zoom]);

  function handlePointerDown(event) {
    if (scale <= 1) return;
    dragOrigin.current = { x: event.clientX - offset.x, y: event.clientY - offset.y };
    setDragging(true);
    event.currentTarget.setPointerCapture?.(event.pointerId);
  }

  function handlePointerMove(event) {
    if (!dragging || !dragOrigin.current) return;
    setOffset({
      x: event.clientX - dragOrigin.current.x,
      y: event.clientY - dragOrigin.current.y,
    });
  }

  function handlePointerUp(event) {
    dragOrigin.current = null;
    setDragging(false);
    event.currentTarget.releasePointerCapture?.(event.pointerId);
  }

  const cursor = scale > 1 ? (dragging ? "grabbing" : "grab") : "zoom-in";

  return createPortal(
    <div
      ref={containerRef}
      className="fixed inset-0 z-[9999] flex flex-col bg-black/80 backdrop-blur-md"
      role="dialog"
      aria-modal="true"
      aria-label="视频截图预览"
      onMouseDown={onClose}
    >
      <div
        className="flex items-center justify-end gap-2 p-3"
        onMouseDown={(event) => event.stopPropagation()}
      >
        <div className="flex items-center gap-1 rounded-full bg-black/50 p-1 text-white ring-1 ring-white/10">
          <button
            type="button"
            onClick={() => zoom(-0.25)}
            className="flex h-8 w-8 items-center justify-center rounded-full transition-colors hover:bg-white/15"
            aria-label="缩小"
            title="缩小"
          >
            <Minus size={16} />
          </button>
          <button
            type="button"
            onClick={reset}
            className="min-w-[3.5rem] rounded-full px-2 py-1 text-xs font-medium tabular-nums transition-colors hover:bg-white/15"
            aria-label="重置缩放"
            title="重置缩放"
          >
            {Math.round(scale * 100)}%
          </button>
          <button
            type="button"
            onClick={() => zoom(0.25)}
            className="flex h-8 w-8 items-center justify-center rounded-full transition-colors hover:bg-white/15"
            aria-label="放大"
            title="放大"
          >
            <Plus size={16} />
          </button>
        </div>
        <button
          type="button"
          onClick={onClose}
          className="flex h-10 w-10 items-center justify-center rounded-full bg-black/50 text-white ring-1 ring-white/10 transition-colors hover:bg-white/15"
          aria-label="关闭截图预览"
          title="关闭"
          autoFocus
        >
          <X size={18} />
        </button>
      </div>

      <div className="flex min-h-0 flex-1 items-center justify-center overflow-hidden px-4 pb-2">
        <img
          src={image.src}
          alt={image.alt}
          draggable={false}
          style={{
            transform: `translate(${offset.x}px, ${offset.y}px) scale(${scale})`,
            cursor,
          }}
          className={`max-h-full max-w-full select-none object-contain ${dragging ? "" : "transition-transform duration-150"}`}
          onMouseDown={(event) => event.stopPropagation()}
          onPointerDown={handlePointerDown}
          onPointerMove={handlePointerMove}
          onPointerUp={handlePointerUp}
          onPointerCancel={handlePointerUp}
          onDoubleClick={() => (scale > 1 ? reset() : setScale(2))}
        />
      </div>

      <p className="pb-4 text-center text-xs text-white/50" onMouseDown={(event) => event.stopPropagation()}>
        滚轮缩放 · 拖拽平移 · 双击复位 · Esc 关闭
      </p>
    </div>,
    document.body,
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
    segmentIndex: segmentIndex >= 0 ? segmentIndex : null,
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
