import { useEffect, useMemo, useState } from "react";
import {
  BookOpenText,
  ChevronLeft,
  ChevronRight,
  Clock3,
  FileUp,
  FolderTree,
  GalleryVerticalEnd,
  Network,
  Sparkles,
  PanelLeft,
  PanelRight
} from "lucide-react";
import "./styles.css";

const initialState = {
  summary: null,
  library: null,
  selectedChapterId: null,
  selectedNodeId: null,
  mindmapVisible: true,
  chapterNavVisible: true,
  error: "",
  loading: true,
};

export function App() {
  const [state, setState] = useState(initialState);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const summaryPath = params.get("summary");
    const mindmapPath = params.get("mindmap");
    const loader = summaryPath ? loadRemoteWorkspace(summaryPath, mindmapPath) : loadDefaultWorkspace();

    loader
      .then(({ summary, library }) => {
        if (!summary) {
          throw new Error("没有找到可展示的总结结果。");
        }
        setState(createLoadedState(summary, library));
      })
      .catch((error) => {
        setState((current) => ({
          ...current,
          loading: false,
          error: error instanceof Error ? error.message : "加载失败",
        }));
      });
  }, []);

  const summary = state.summary;
  const activeSeries = state.library?.series?.[0] ?? null;
  const currentVideoTitle = summary?.title ?? activeSeries?.videos?.[0]?.title ?? "未命名视频";
  const selectedNode = useMemo(
    () => findNodeById(summary?.mindmap, state.selectedNodeId),
    [summary?.mindmap, state.selectedNodeId],
  );

  async function onSummaryFileChange(event) {
    const [summaryFile] = event.target.files ?? [];
    if (!summaryFile) {
      return;
    }

    setState((current) => ({ ...current, loading: true, error: "" }));
    try {
      const summaryData = await readJsonFile(summaryFile);
      setState(
        createLoadedState(
          { ...summaryData, mindmap: summaryData.mindmap ?? null },
          currentLibrary(state.library, summaryData),
        ),
      );
    } catch (error) {
      setState((current) => ({
        ...current,
        loading: false,
        error: error instanceof Error ? error.message : "summary.json 解析失败",
      }));
    }
  }

  async function onMindmapFileChange(event) {
    const [mindmapFile] = event.target.files ?? [];
    if (!mindmapFile || !summary) {
      return;
    }

    try {
      const mindmapData = await readJsonFile(mindmapFile);
      setState(createLoadedState({ ...summary, mindmap: mindmapData }, state.library));
    } catch (error) {
      setState((current) => ({
        ...current,
        error: error instanceof Error ? error.message : "mindmap.json 解析失败",
      }));
    }
  }

  function focusChapter(chapterId) {
    setState((current) => ({
      ...current,
      selectedChapterId: chapterId,
    }));

    requestAnimationFrame(() => {
      document.getElementById(chapterId)?.scrollIntoView({ behavior: "smooth", block: "start" });
    });
  }

  function focusNode(node) {
    setState((current) => ({
      ...current,
      selectedNodeId: node.id,
      selectedChapterId:
        findChapterForNode(current.summary?.chapters ?? [], node)?.id ?? current.selectedChapterId,
    }));

    requestAnimationFrame(() => {
      const linkedChapter = findChapterForNode(summary?.chapters ?? [], node)?.id;
      if (linkedChapter) {
        document.getElementById(linkedChapter)?.scrollIntoView({ behavior: "smooth", block: "start" });
      }
    });
  }

  function toggleMindmapVisibility() {
    setState((current) => ({
      ...current,
      mindmapVisible: !current.mindmapVisible,
    }));
  }

  function toggleChapterNavVisibility() {
    setState((current) => ({
      ...current,
      chapterNavVisible: !current.chapterNavVisible,
    }));
  }

  if (state.loading && !summary) {
    return (
      <div className="loading-screen">
        <div className="loading-card">
          <p className="eyebrow">Preparing Workspace</p>
          <h1>正在载入知识工作台</h1>
          <p>默认会优先读取 sample 里的第一条总结结果。</p>
        </div>
      </div>
    );
  }

  return (
    <div className="workspace-shell">
      <header className="topbar">
        <div className="brand-block">
          <div className="brand-icon">
            <BookOpenText size={24} strokeWidth={2.1} />
          </div>
          <div>
            <p className="eyebrow">Editorial Knowledge Workspace</p>
            <h1 className="brand-title">Video Include</h1>
          </div>
        </div>

        <div className="toolbar">
          <button 
            className={`panel-toggle${state.mindmapVisible ? " is-active" : ""}`} 
            onClick={toggleMindmapVisibility}
            title="Toggle Mindmap"
          >
            <PanelLeft size={20} strokeWidth={2.2} />
          </button>
          <button 
            className={`panel-toggle${state.chapterNavVisible ? " is-active" : ""}`} 
            onClick={toggleChapterNavVisibility}
            title="Toggle Timeline"
          >
            <PanelRight size={20} strokeWidth={2.2} />
          </button>
          <div className="toolbar-divider" style={{ width: 1, height: 24, background: "rgba(24,24,27,0.1)", margin: "0 8px" }} />
          <label className="tool-button tool-button-icon" title="上传外部 Summary (Dev)">
            <FileUp size={18} strokeWidth={2.4} />
            <input type="file" accept=".json,application/json" onChange={onSummaryFileChange} hidden />
          </label>
          <label className="tool-button tool-button-secondary tool-button-icon" title="上传替换导图 (Dev)">
            <Network size={18} strokeWidth={2.4} />
            <input type="file" accept=".json,application/json" onChange={onMindmapFileChange} hidden />
          </label>
        </div>
      </header>

      {state.error ? <div className="error-banner">{state.error}</div> : null}

      <main
        className={`document-grid${state.mindmapVisible ? "" : " is-map-hidden"}${state.chapterNavVisible ? "" : " is-nav-hidden"}`}
      >
        <aside
          className={`mindmap-pane${state.mindmapVisible ? "" : " is-hidden"}`}
          aria-hidden={!state.mindmapVisible}
        >
          <div className="mindmap-pane-head">
            <p className="eyebrow">Mindmap View</p>
            <h2>{summary?.mindmap?.title ?? "思维导图"}</h2>
            <p className="mindmap-pane-copy">
              {selectedNode?.summary || "左侧用于宏观浏览知识结构，点击节点会联动正文和右侧章节。"}
            </p>
          </div>
          <MindmapCanvas root={summary?.mindmap} selectedNodeId={state.selectedNodeId} onSelectNode={focusNode} />
        </aside>

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
                  className={`article-card${chapter.id === state.selectedChapterId ? " is-focused" : ""}`}
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

        <aside
          className={`chapter-pane${state.chapterNavVisible ? "" : " is-hidden"}`}
          aria-hidden={!state.chapterNavVisible}
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
                className={`chapter-card${chapter.id === state.selectedChapterId ? " is-active" : ""}`}
                onClick={() => focusChapter(chapter.id)}
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
      </main>
    </div>
  );
}

function MindmapCanvas({ root, selectedNodeId, onSelectNode }) {
  if (!root) {
    return <div className="empty-note">当前没有导图数据。</div>;
  }

  function renderNode(node, depth) {
    const hasChildren = node.children && node.children.length > 0;
    const isRoot = depth === 0;

    return (
      <li key={node.id}>
        <div className="css-tree-node-wrapper">
          <button
            type="button"
            className={`mindmap-node depth-${depth}${node.id === selectedNodeId ? " is-active" : ""}`}
            onClick={() => onSelectNode(node)}
          >
            <span className="mindmap-label">{node.title}</span>
            {!isRoot && hasChildren && <span className="mindmap-badge">{node.children.length}</span>}
          </button>
        </div>
        {hasChildren && (
          <ul>
            {node.children.map((child) => renderNode(child, depth + 1))}
          </ul>
        )}
      </li>
    );
  }

  return (
    <div className="mindmap-scroll">
      <div className="css-tree">
        <ul>
          {renderNode(root, 0)}
        </ul>
      </div>
    </div>
  );
}

function createLoadedState(summary, library) {
  return {
    summary,
    library,
    selectedChapterId: summary.chapters?.[0]?.id ?? null,
    selectedNodeId: summary.mindmap?.children?.[0]?.id ?? summary.mindmap?.id ?? null,
    mindmapVisible: true,
    chapterNavVisible: true,
    error: "",
    loading: false,
  };
}

function currentLibrary(existingLibrary, summary) {
  if (existingLibrary) {
    return existingLibrary;
  }
  return {
    workspace: { id: "local", title: "Local Workspace" },
    series: [
      {
        id: "imported",
        title: "Imported Series",
        videos: [{ id: summary.title, title: summary.title }],
      },
    ],
  };
}

async function loadDefaultWorkspace() {
  const library = await fetchJson("/api/videos");
  const firstVideo = library.videos?.[0];
  if (!firstVideo) {
    throw new Error("sample/output 中没有可展示的视频总结。");
  }

  const summary = await fetchJson(`/api/videos/${encodeURIComponent(firstVideo.id)}/summary`);
  return { summary, library };
}

async function loadRemoteWorkspace(summaryPath, mindmapPath) {
  const [summaryData, mindmapData] = await Promise.all([
    fetchJson(summaryPath),
    mindmapPath ? fetchJson(mindmapPath) : Promise.resolve(null),
  ]);

  return {
    summary: {
      ...summaryData,
      mindmap: mindmapData ?? summaryData.mindmap ?? null,
    },
    library: currentLibrary(null, summaryData),
  };
}

async function fetchJson(path) {
  const response = await fetch(path);
  if (!response.ok) {
    throw new Error(`加载失败：${path}`);
  }
  return response.json();
}

async function readJsonFile(file) {
  const text = await file.text();
  return JSON.parse(text);
}

function formatRange(startSeconds, endSeconds) {
  return `${formatTimestamp(startSeconds)} - ${formatTimestamp(endSeconds)}`;
}

function formatTimestamp(totalSeconds) {
  const safeSeconds = Math.max(0, Math.floor(totalSeconds ?? 0));
  const hours = Math.floor(safeSeconds / 3600);
  const minutes = Math.floor((safeSeconds % 3600) / 60);
  const seconds = safeSeconds % 60;
  if (hours > 0) {
    return `${pad(hours)}:${pad(minutes)}:${pad(seconds)}`;
  }
  return `${pad(minutes)}:${pad(seconds)}`;
}

function pad(value) {
  return String(value).padStart(2, "0");
}

function findNodeById(root, targetId) {
  if (!root || !targetId) {
    return null;
  }
  let match = null;
  walkTree(root, (node) => {
    if (node.id === targetId) {
      match = node;
      return true;
    }
    return false;
  });
  return match;
}

function findChapterForNode(chapters, node) {
  return (
    chapters.find(
      (chapter) =>
        node.start_seconds >= chapter.start_seconds && node.end_seconds <= chapter.end_seconds,
    ) ?? null
  );
}

function walkTree(root, visitor, ancestors = []) {
  if (!root) {
    return false;
  }
  if (visitor(root, ancestors)) {
    return true;
  }
  return (root.children ?? []).some((child) => walkTree(child, visitor, [...ancestors, root]));
}