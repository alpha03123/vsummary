import { formatRange } from "../../../shared/lib/time";

export function WorkspaceChapterPane({
  visible,
  summary,
  currentVideoTitle,
  selectedChapterId,
  onFocusChapter,
}) {
  return (
    <aside
      className={`chapter-pane${visible ? "" : " is-hidden"}`}
      aria-hidden={!visible}
    >
      <div className="chapter-pane-head">
        <p className="eyebrow">Timeline</p>
        <h2>章节导航</h2>
        <p>{currentVideoTitle}</p>
      </div>

      <nav className="chapter-list" aria-label="章节导航">
        {(summary?.chapters ?? []).map((chapter, index) => (
          <button
            key={chapter.id}
            type="button"
            className={`chapter-card${chapter.id === selectedChapterId ? " is-active" : ""}`}
            onClick={() => onFocusChapter(chapter.id)}
          >
            <span className="chapter-index">{String(index + 1).padStart(2, "0")}</span>
            <div className="chapter-card-copy">
              <strong>{chapter.title}</strong>
              <span>{formatRange(chapter.start_seconds, chapter.end_seconds)}</span>
            </div>
          </button>
        ))}
      </nav>
    </aside>
  );
}
