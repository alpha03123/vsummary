import {
  Clock3,
  FolderTree,
  GalleryVerticalEnd,
  Sparkles,
} from "lucide-react";

import { formatRange } from "../../../shared/lib/time";

export function WorkspaceReadingPane({ summary, activeSeries, selectedChapterId }) {
  return (
    <section className="reading-pane">
      <header className="content-header">
        <div className="content-header-main">
          <div className="content-title-wrapper">
            <p className="eyebrow">Selected Video</p>
            <h2>{summary?.title ?? "未加载内容"}</h2>
            <p className="content-summary">{summary?.one_sentence_summary ?? "当前没有总结内容。"}</p>
          </div>
        </div>
        <div className="content-meta">
          <span className="meta-pill">
            <FolderTree size={14} strokeWidth={2.2} />
            {activeSeries?.title ?? "Default Series"}
          </span>
          <span className="meta-pill">
            <Clock3 size={14} strokeWidth={2.2} />
            {formatRange(0, summary?.chapters?.at(-1)?.end_seconds ?? 0)}
          </span>
          <span className="meta-pill">
            <GalleryVerticalEnd size={14} strokeWidth={2.2} />
            {summary?.chapters?.length ?? 0} 章
          </span>
        </div>
      </header>

      <div className="reading-scroll">
        <article className="problem-card">
          <p className="eyebrow">Core Problem</p>
          <p>{summary?.core_problem ?? "当前没有核心问题描述。"}</p>
        </article>

        <section className="takeaways-section">
          <div className="section-heading">
            <p className="eyebrow">Signals</p>
            <h2>关键收获</h2>
          </div>
          <div className="takeaway-grid">
            {(summary?.key_takeaways ?? []).map((item) => (
              <article key={item} className="takeaway-card">
                <Sparkles size={15} strokeWidth={2.2} />
                <p>{item}</p>
              </article>
            ))}
          </div>
        </section>

        <div className="article-stack">
          {(summary?.chapters ?? []).map((chapter, index) => (
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
      </div>
    </section>
  );
}
