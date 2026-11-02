import { useEffect, useMemo, useState } from "react";
import { FileText, LoaderCircle, PencilLine, RefreshCw, Save } from "lucide-react";

import { WorkspaceMarkdownMessage } from "../shared/WorkspaceMarkdownMessage";
import { WorkspaceStateBlock } from "../shared/WorkspaceStateBlock";
import { findContentScrollContainer, WorkspaceContentOutline } from "../shared/WorkspaceContentOutline";
import { buildMarkdownOutline } from "../../model/markdownOutline";

export function WorkspaceAiSummaryView({
  aiSummary,
  loading,
  generating,
  canGenerate = true,
  canEdit = true,
  onGenerate,
  // Hosts that discard the source video after processing (Cloud) cannot rewrite a finished summary.
  canRegenerate = true,
  onUpdate,
  noteImageContext,
  onSeek,
  onOpenCitationReference,
  onOpenTranscriptAtTime,
}) {
  const [editing, setEditing] = useState(false);
  const [title, setTitle] = useState("");
  const [content, setContent] = useState("");
  const outline = useMemo(() => buildMarkdownOutline(aiSummary?.content, "ai-summary-outline"), [aiSummary?.content]);
  const [activeOutlineId, setActiveOutlineId] = useState(null);

  useEffect(() => {
    setActiveOutlineId(outline.items[0]?.id ?? null);
  }, [outline.items]);

  useEffect(() => {
    if (!outline.items.length || typeof IntersectionObserver === "undefined") {
      return undefined;
    }
    const firstHeading = document.getElementById(outline.items[0].id);
    const observer = new IntersectionObserver((entries) => {
      const visible = entries
        .filter((entry) => entry.isIntersecting)
        .sort((left, right) => left.boundingClientRect.top - right.boundingClientRect.top)[0];
      if (visible?.target.id) {
        setActiveOutlineId(visible.target.id);
      }
    }, { root: findContentScrollContainer(firstHeading), rootMargin: "-12% 0px -72% 0px" });
    outline.items.forEach((item) => {
      const heading = document.getElementById(item.id);
      if (heading) observer.observe(heading);
    });
    return () => observer.disconnect();
  }, [outline.items]);

  function startEditing() {
    if (!aiSummary) return;
    setTitle(aiSummary.title);
    setContent(aiSummary.content);
    setEditing(true);
  }

  function save() {
    if (!title.trim() || !content.trim()) return;
    onUpdate?.({ title: title.trim(), content: content.trim() });
    setEditing(false);
  }

  function selectOutlineItem(id) {
    setActiveOutlineId(id);
    document.getElementById(id)?.scrollIntoView?.({ behavior: "smooth", block: "start" });
  }

  if (loading && !aiSummary) {
    return <WorkspaceStateBlock title="载入 AI 概括" description="正在读取当前视频的 AI 概括。" loading />;
  }

  if (!aiSummary) {
    return (
      <WorkspaceStateBlock
        title="尚未生成 AI 概括"
        description="生成后会得到完整的概括，带画面截图和时间点。"
        actionLabel={generating ? "正在生成" : "生成 AI 概括"}
        actionIcon={generating ? <LoaderCircle size={16} className="animate-spin" /> : <FileText size={16} />}
        actionDisabled={generating || !canGenerate}
        onAction={() => onGenerate?.("general")}
      />
    );
  }

  return (
    <div className="flex h-full flex-col gap-4 animate-in fade-in slide-in-from-right-4 duration-300">
      <div className="flex items-center justify-between gap-3 px-2">
        <div className="min-w-0">
          <h2 className="mt-1 text-lg font-bold text-strong">AI 概括</h2>
        </div>
        <div className="flex shrink-0 items-center gap-1">
          {editing ? (
            <>
              <button type="button" onClick={() => setEditing(false)} className="rounded-full border border-line px-3 py-1.5 text-xs font-bold text-subtle hover:bg-muted">取消</button>
              <button type="button" onClick={save} disabled={!title.trim() || !content.trim()} className="inline-flex items-center gap-1.5 rounded-full bg-inverse px-3 py-1.5 text-xs font-bold text-on-inverse disabled:opacity-50"><Save size={14} />保存</button>
            </>
          ) : (
            <>
              {canEdit&&<button type="button" onClick={startEditing} className="flex h-8 w-8 items-center justify-center rounded-full text-subtle hover:bg-soft" title="编辑 AI 概括"><PencilLine size={15} /></button>}
              {canRegenerate ? <button type="button" onClick={() => onGenerate?.("general")} disabled={generating || !canGenerate} className="flex h-8 w-8 items-center justify-center rounded-full text-accent hover:bg-accent/10 disabled:opacity-50" title="重新生成 AI 概括">{generating ? <LoaderCircle size={15} className="animate-spin" /> : <RefreshCw size={15} />}</button> : null}
            </>
          )}
        </div>
      </div>
      {editing ? (
        <article className="rounded-3xl border border-line/80 bg-surface p-6 shadow-sm">
          <div className="flex flex-col gap-4">
            <input value={title} onChange={(event) => setTitle(event.target.value)} className="w-full rounded-xl border border-line bg-muted px-4 py-3 text-lg font-bold text-strong outline-none focus:border-accent" />
            <textarea value={content} onChange={(event) => setContent(event.target.value)} className="min-h-[360px] w-full resize-y rounded-xl border border-line bg-muted px-4 py-3 text-sm leading-relaxed text-strong outline-none focus:border-accent" />
          </div>
        </article>
      ) : (
        <WorkspaceContentOutline
          label="概括目录"
          items={outline.items}
          activeItemId={activeOutlineId}
          onSelect={selectOutlineItem}
        >
          <article className="rounded-3xl border border-line/80 bg-surface p-6 shadow-sm">
            <h1 className="text-2xl font-bold text-strong">{aiSummary.title}</h1>
            <div className="my-5 h-px bg-soft" />
            <div className="markdown-body text-sm text-body"><WorkspaceMarkdownMessage content={aiSummary.content} citations={aiSummary.citations} headingIds={outline.headingIds} noteImageContext={noteImageContext} onSeek={onSeek} onOpenCitationReference={onOpenCitationReference} onOpenTranscriptAtTime={onOpenTranscriptAtTime} /></div>
          </article>
        </WorkspaceContentOutline>
      )}
    </div>
  );
}
