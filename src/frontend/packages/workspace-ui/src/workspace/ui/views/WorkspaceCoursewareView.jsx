import { useCallback, useEffect, useRef, useState } from "react";
import {
  ChevronLeft,
  ChevronRight,
  Download,
  LayoutGrid,
  Maximize2,
  PlayCircle,
  Presentation,
  RefreshCw,
} from "lucide-react";

import { useWorkspaceRuntime } from "../../../runtime/WorkspaceProvider";
import { WorkspaceGenerationStatus } from "../shared/WorkspaceGenerationStatus";
import { WorkspaceStateBlock } from "../shared/WorkspaceStateBlock";

export function formatCoursewareTime(seconds) {
  const total = Math.max(0, Math.floor(Number(seconds) || 0));
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const secs = String(total % 60).padStart(2, "0");
  return hours
    ? `${hours}:${String(minutes).padStart(2, "0")}:${secs}`
    : `${String(minutes).padStart(2, "0")}:${secs}`;
}

export function WorkspaceCoursewareView({
  seriesId,
  videoId,
  tools,
  onGenerate,
  onSeek,
}) {
  const { api } = useWorkspaceRuntime();
  const [deck, setDeck] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [progress, setProgress] = useState(null);
  const [activeSlideIndex, setActiveSlideIndex] = useState(null);
  const unsubscribeRef = useRef(null);

  const toolState = tools?.courseware ?? null;
  const coursewareUrl =
    seriesId && videoId
      ? `/api/videos/${encodeURIComponent(seriesId)}/${encodeURIComponent(videoId)}/courseware`
      : null;
  const pdfExportUrl =
    seriesId && videoId
      ? api.resourceUrl(
          `/api/videos/${encodeURIComponent(seriesId)}/${encodeURIComponent(videoId)}/exports/courseware.pdf`,
        )
      : null;

  const loadCourseware = useCallback(async () => {
    if (!coursewareUrl) {
      setDeck(null);
      return;
    }
    const payload = await api.fetchJson(coursewareUrl, undefined, {
      notFoundValue: null,
    });
    setDeck(payload ?? null);
  }, [api, coursewareUrl]);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    setDeck(null);
    setActiveSlideIndex(null);
    if (!coursewareUrl) {
      setLoading(false);
      return undefined;
    }
    api
      .fetchJson(coursewareUrl, undefined, { notFoundValue: null })
      .then((payload) => {
        if (!cancelled) {
          setDeck(payload ?? null);
        }
      })
      .catch((reason) => {
        if (!cancelled) {
          setError(
            reason instanceof Error ? reason.message : "视频课件读取失败",
          );
        }
      })
      .finally(() => {
        if (!cancelled) {
          setLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [api, coursewareUrl]);

  useEffect(() => () => unsubscribeRef.current?.(), []);

  const slides = Array.isArray(deck?.slides) ? deck.slides : [];

  useEffect(() => {
    if (activeSlideIndex === null) return undefined;
    function handleKeyDown(event) {
      if (event.key === "ArrowLeft") {
        setActiveSlideIndex((prev) =>
          prev === null ? null : Math.max(0, prev - 1),
        );
      } else if (event.key === "ArrowRight") {
        setActiveSlideIndex((prev) =>
          prev === null ? null : Math.min(slides.length - 1, prev + 1),
        );
      } else if (event.key === "Escape") {
        setActiveSlideIndex(null);
      }
    }
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [activeSlideIndex, slides.length]);

  async function handleGenerate() {
    setError(null);
    let submitted;
    try {
      submitted = await onGenerate?.();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "视频课件提取失败");
      return;
    }
    if (!submitted?.jobId) {
      return;
    }
    setProgress({ status: "queued", startedAt: Date.now() / 1000 });
    unsubscribeRef.current?.();
    unsubscribeRef.current = api.subscribeDurableJobProgress(
      submitted.jobId,
      async (snapshot) => {
        setProgress(snapshot);
        if (snapshot.status === "completed") {
          unsubscribeRef.current?.();
          try {
            await loadCourseware();
          } catch (reason) {
            setError(
              reason instanceof Error ? reason.message : "视频课件读取失败",
            );
          }
          setProgress(null);
        } else if (
          snapshot.status === "failed" ||
          snapshot.status === "cancelled"
        ) {
          unsubscribeRef.current?.();
          setProgress(null);
          setError(snapshot.error || snapshot.detail || "视频课件提取失败");
        }
      },
    );
  }

  function jumpToSlide(slide) {
    if (!slide) return;
    const startSeconds = Number(slide.start_seconds ?? 0);
    const endSeconds = Number(slide.end_seconds ?? startSeconds);
    onSeek?.({
      seconds: startSeconds,
      endSeconds,
      chapterTitle: `课件第 ${slide.ordinal} 页`,
      reveal: true,
    });
  }

  if (progress) {
    return (
      <WorkspaceStateBlock title="正在提取视频课件">
        <WorkspaceGenerationStatus
          snapshot={progress}
          label="正在捕捉画面跳变并抽取高清课件"
        />
      </WorkspaceStateBlock>
    );
  }

  if (loading) {
    return (
      <WorkspaceStateBlock
        title="载入视频课件"
        description="正在读取已提取的课件页面。"
        loading
      />
    );
  }

  if (!deck) {
    if (toolState?.status === "audio_only") {
      return (
        <WorkspaceStateBlock
          title="纯音频不支持提取课件"
          description="当前媒体不含视频画面，无法提取课件。"
        />
      );
    }
    if (toolState?.status === "source_released") {
      return (
        <WorkspaceStateBlock
          title="未在导入时选择课件"
          description="课件需在导入视频时，于「联动生成」中勾选「视频课件」。"
        />
      );
    }
    if (toolState?.available === false) {
      return (
        <WorkspaceStateBlock
          title="原视频暂不可用"
          description="请先下载或链接原始视频文件后再提取课件。"
        />
      );
    }
    return (
      <WorkspaceStateBlock
        title="视频课件尚未生成"
        description="自动捕捉网课中的 PPT 翻页与完整板书画面，可点击跳转对应讲解并导出 PDF。"
      >
        {error ? (
          <p role="alert" className="mb-3 text-sm text-danger">
            {error}
          </p>
        ) : null}
        <button
          type="button"
          onClick={handleGenerate}
          className="inline-flex items-center gap-2 rounded-2xl bg-inverse px-5 py-3 text-sm font-semibold text-on-accent transition hover:bg-accent"
        >
          <Presentation size={16} strokeWidth={2.2} />
          提取视频课件
        </button>
      </WorkspaceStateBlock>
    );
  }

  if (!slides.length) {
    return (
      <WorkspaceStateBlock
        title="未检测到有效课件页面"
        description="视频画面未提取出可用帧，可尝试重新提取。"
      >
        {deck.can_regenerate !== false ? (
          <button
            type="button"
            onClick={handleGenerate}
            className="inline-flex items-center gap-2 rounded-xl border border-accent/30 bg-accent/8 px-4 py-2.5 text-sm font-semibold text-accent transition-colors hover:bg-accent/14"
          >
            <RefreshCw size={15} />
            重新提取
          </button>
        ) : null}
      </WorkspaceStateBlock>
    );
  }

  const activeSlide =
    activeSlideIndex !== null ? (slides[activeSlideIndex] ?? null) : null;

  return (
    <div className="flex flex-col gap-4 pb-8">
      {error ? (
        <p
          role="alert"
          className="rounded-xl border border-danger/30 bg-danger-subtle px-3.5 py-2.5 text-sm text-danger"
        >
          {error}
        </p>
      ) : null}

      <div className="flex flex-wrap items-center justify-between gap-2 rounded-2xl border border-line-soft bg-soft/60 px-3.5 py-2.5">
        <div className="flex items-center gap-2 text-xs font-medium text-subtle">
          <span className="inline-flex items-center gap-1.5 font-semibold text-strong">
            <Presentation size={15} className="text-accent" />
            共 {slides.length} 页课件
          </span>
          {activeSlide ? (
            <span>
              · 当前第 {activeSlide.ordinal} 页（
              {formatCoursewareTime(activeSlide.start_seconds)} –{" "}
              {formatCoursewareTime(activeSlide.end_seconds)}）
            </span>
          ) : null}
        </div>

        <div className="flex flex-wrap items-center gap-1.5">
          {activeSlide ? (
            <button
              type="button"
              onClick={() => setActiveSlideIndex(null)}
              className="inline-flex items-center gap-1.5 rounded-xl border border-line bg-surface px-2.5 py-1.5 text-xs font-semibold text-body transition hover:border-accent/40 hover:text-accent"
            >
              <LayoutGrid size={13} />
              返回网格
            </button>
          ) : (
            <button
              type="button"
              onClick={() => setActiveSlideIndex(0)}
              className="inline-flex items-center gap-1.5 rounded-xl border border-line bg-surface px-2.5 py-1.5 text-xs font-semibold text-body transition hover:border-accent/40 hover:text-accent"
            >
              <Maximize2 size={13} />
              大图精读
            </button>
          )}
          {pdfExportUrl ? (
            <a
              href={pdfExportUrl}
              download
              className="inline-flex items-center gap-1.5 rounded-xl border border-line bg-surface px-2.5 py-1.5 text-xs font-semibold text-body transition hover:border-accent/40 hover:text-accent"
            >
              <Download size={13} />
              导出 PDF
            </a>
          ) : null}
          {deck.can_regenerate !== false ? (
            <button
              type="button"
              onClick={handleGenerate}
              title="重新提取课件"
              className="inline-flex items-center gap-1.5 rounded-xl border border-line bg-surface px-2.5 py-1.5 text-xs font-semibold text-subtle transition hover:border-accent/40 hover:text-accent"
            >
              <RefreshCw size={13} />
              重新提取
            </button>
          ) : null}
        </div>
      </div>

      {activeSlide ? (
        <div className="flex flex-col gap-3 rounded-2xl border border-line bg-surface p-3 sm:p-4">
          <div className="relative overflow-hidden rounded-xl bg-black/95">
            <img
              src={api.resourceUrl(activeSlide.image_url)}
              alt={`课件第 ${activeSlide.ordinal} 页`}
              className="mx-auto max-h-[68vh] w-auto object-contain"
            />
          </div>
          <div className="flex flex-wrap items-center justify-between gap-2 pt-1">
            <div className="flex items-center gap-2">
              <button
                type="button"
                disabled={activeSlideIndex <= 0}
                onClick={() =>
                  setActiveSlideIndex((prev) => Math.max(0, (prev ?? 0) - 1))
                }
                className="inline-flex items-center gap-1 rounded-xl border border-line px-3 py-1.5 text-xs font-semibold text-body transition hover:bg-soft disabled:cursor-not-allowed disabled:opacity-40"
              >
                <ChevronLeft size={14} />
                上一页
              </button>
              <span className="text-xs font-semibold text-subtle">
                {activeSlide.ordinal} / {slides.length}
              </span>
              <button
                type="button"
                disabled={activeSlideIndex >= slides.length - 1}
                onClick={() =>
                  setActiveSlideIndex((prev) =>
                    Math.min(slides.length - 1, (prev ?? 0) + 1),
                  )
                }
                className="inline-flex items-center gap-1 rounded-xl border border-line px-3 py-1.5 text-xs font-semibold text-body transition hover:bg-soft disabled:cursor-not-allowed disabled:opacity-40"
              >
                下一页
                <ChevronRight size={14} />
              </button>
            </div>

            <button
              type="button"
              onClick={() => jumpToSlide(activeSlide)}
              className="inline-flex items-center gap-1.5 rounded-xl bg-accent/10 px-3.5 py-1.5 text-xs font-semibold text-accent transition hover:bg-accent/20"
            >
              <PlayCircle size={14} />
              跳转到本页讲解 ({formatCoursewareTime(activeSlide.start_seconds)})
            </button>
          </div>
        </div>
      ) : (
        <div className="grid gap-3.5 [grid-template-columns:repeat(auto-fill,minmax(min(100%,15.5rem),1fr))]">
          {slides.map((slide, index) => (
            <article
              key={slide.id || slide.ordinal || index}
              className="group flex flex-col overflow-hidden rounded-2xl border border-line bg-surface transition hover:border-accent/40 hover:shadow-sm"
            >
              <button
                type="button"
                onClick={() => setActiveSlideIndex(index)}
                className="relative aspect-video w-full overflow-hidden bg-muted text-left"
                title="点击放大查看"
              >
                <img
                  src={api.resourceUrl(slide.image_url)}
                  alt={`课件第 ${slide.ordinal} 页`}
                  loading="lazy"
                  className="h-full w-full object-cover transition-transform duration-200 group-hover:scale-[1.015]"
                />
                <span className="absolute left-2.5 top-2.5 rounded-lg bg-black/70 px-2 py-0.5 text-[11px] font-semibold text-white backdrop-blur-xs">
                  P{String(slide.ordinal).padStart(2, "0")}
                </span>
              </button>
              <div className="flex items-center justify-between gap-2 px-3 py-2.5">
                <span className="text-xs font-medium text-subtle">
                  {formatCoursewareTime(slide.start_seconds)} –{" "}
                  {formatCoursewareTime(slide.end_seconds)}
                </span>
                <button
                  type="button"
                  onClick={() => jumpToSlide(slide)}
                  className="inline-flex items-center gap-1 rounded-lg bg-accent/10 px-2.5 py-1 text-xs font-semibold text-accent transition hover:bg-accent/20"
                  title="跳转到该页开始讲解的时间点"
                >
                  <PlayCircle size={13} />
                  跳转讲解
                </button>
              </div>
            </article>
          ))}
        </div>
      )}
    </div>
  );
}
