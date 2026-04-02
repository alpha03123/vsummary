import {
  Clock3,
  FolderTree,
  GalleryVerticalEnd,
  LoaderCircle,
  Sparkles,
} from "lucide-react";

import { formatRange } from "../../../shared/lib/time";

export function WorkspaceReadingPane({
  children,
  ui,
  summary,
  activeSeries,
  selectedVideo,
  selectedChapterId,
  summaryLoading,
  isGeneratingSelectedVideo,
}) {
  const hasSummary = Boolean(summary);

  return (
    <section
      className={`reading-pane${ui.contentWidth === "wide" ? " is-wide" : ""}${ui.readingDensity === "compact" ? " is-compact" : ""}`}
    >
      <div className="reading-scroll">
        {children}

        {!selectedVideo ? (
          <section className="empty-state-card">
            <p className="eyebrow">No Video</p>
            <h2>先选择一个视频</h2>
            <p>选择 series 后，点选一个视频，我们再决定展示已有结果还是开始生成。</p>
          </section>
        ) : summaryLoading ? (
          <section className="empty-state-card is-busy">
            <p className="eyebrow">Loading Summary</p>
            <h2>正在读取结果</h2>
            <p>如果这个视频已经生成过，这里会自动加载 `workspace` 中对应结果。</p>
            <div className="inline-status">
              <LoaderCircle size={18} strokeWidth={2.2} className="spin-icon" />
              正在载入视频总结
            </div>
          </section>
        ) : !hasSummary ? (
          <section className="empty-state-card">
            <p className="eyebrow">Not Generated</p>
            <h2>{selectedVideo.title}</h2>
            <p>
              当前视频还没有处理结果。生成后，中间文件会写入
              {" "}
              <strong>`workspace/{activeSeries?.id}/{selectedVideo.id}/`</strong>
              {" "}
              目录。
            </p>
            {isGeneratingSelectedVideo ? (
              <div className="inline-status">
                <LoaderCircle size={18} strokeWidth={2.2} className="spin-icon" />
                正在生成视频总结与中间文件
              </div>
            ) : null}
          </section>
        ) : (
          <>
            <header className="content-header">
              <div className="content-header-main">
                <div className="content-title-wrapper">
                  <p className="eyebrow">Selected Video</p>
                  <h2>{summary.title}</h2>
                  <p className="content-summary">{summary.one_sentence_summary ?? "当前没有总结内容。"}</p>
                </div>
              </div>
              <div className="content-meta">
                <span className="meta-pill">
                  <FolderTree size={14} strokeWidth={2.2} />
                  {activeSeries?.title ?? "Default Series"}
                </span>
                <span className="meta-pill">
                  <Clock3 size={14} strokeWidth={2.2} />
                  {formatRange(0, summary.chapters?.at(-1)?.end_seconds ?? 0)}
                </span>
                <span className="meta-pill">
                  <GalleryVerticalEnd size={14} strokeWidth={2.2} />
                  {summary.chapters?.length ?? 0} 章
                </span>
              </div>
            </header>

            <article className="problem-card">
              <p className="eyebrow">Core Problem</p>
              <p>{summary.core_problem ?? "当前没有核心问题描述。"}</p>
            </article>

            {ui.showTakeaways ? (
              <section className="takeaways-section">
                <div className="section-heading">
                  <p className="eyebrow">Signals</p>
                  <h2>关键收获</h2>
                </div>
                <div className="takeaway-grid">
                  {(summary.key_takeaways ?? []).map((item) => (
                    <article key={item} className="takeaway-card">
                      <Sparkles size={15} strokeWidth={2.2} />
                      <p>{item}</p>
                    </article>
                  ))}
                </div>
              </section>
            ) : null}

            <div className="article-stack">
              {(summary.chapters ?? []).map((chapter, index) => (
                <article
                  key={chapter.id}
                  id={chapter.id}
                  className={`article-card${chapter.id === selectedChapterId ? " is-focused" : ""}`}
                >
                  <div className="article-head">
                    <div>
                      <p className="eyebrow">Chapter {index + 1}</p>
                      <h3>{chapter.title}</h3>
                    </div>
                    <span className="timestamp-chip">{formatRange(chapter.start_seconds, chapter.end_seconds)}</span>
                  </div>
                  <p className="article-summary">{chapter.summary}</p>
                  <div className="keypoint-grid">
                    {chapter.key_points.map((point) => (
                      <div key={point} className="keypoint-card">
                        <span className="keypoint-bullet" />
                        <p>{point}</p>
                      </div>
                    ))}
                  </div>
                </article>
              ))}
            </div>
          </>
        )}
      </div>
    </section>
  );
}
