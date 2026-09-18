import { useState } from "react";
import { FileText, LoaderCircle, PencilLine, RefreshCw, Save } from "lucide-react";

import { WorkspaceMarkdownMessage } from "../shared/WorkspaceMarkdownMessage";
import { WorkspaceStateBlock } from "../shared/WorkspaceStateBlock";

export function WorkspaceAiSummaryView({
  aiSummary,
  loading,
  generating,
  canGenerate = true,
  onGenerate,
  onUpdate,
  noteImageContext,
  onSeek,
}) {
  const [editing, setEditing] = useState(false);
  const [title, setTitle] = useState("");
  const [content, setContent] = useState("");

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

  if (loading && !aiSummary) {
    return <WorkspaceStateBlock eyebrow="AI Summary" title="载入 AI 概括" description="正在读取当前视频的 AI 概括。" loading />;
  }

  if (!aiSummary) {
    return (
      <WorkspaceStateBlock
        eyebrow="AI Summary"
        title="尚未生成 AI 概括"
        description="生成后会得到一份可编辑的完整总结，并保留画面与时间标记。"
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
          <p className="text-xs font-bold uppercase tracking-wider text-accent">AI Summary</p>
          <h2 className="mt-1 text-lg font-bold text-stone-900 dark:text-stone-100">AI 概括</h2>
        </div>
        <div className="flex shrink-0 items-center gap-1">
          {editing ? (
            <>
              <button type="button" onClick={() => setEditing(false)} className="rounded-full border border-stone-200 px-3 py-1.5 text-xs font-bold text-stone-600 hover:bg-stone-50 dark:border-stone-700 dark:text-stone-300">取消</button>
              <button type="button" onClick={save} disabled={!title.trim() || !content.trim()} className="inline-flex items-center gap-1.5 rounded-full bg-stone-900 px-3 py-1.5 text-xs font-bold text-white disabled:opacity-50 dark:bg-white dark:text-black"><Save size={14} />保存</button>
            </>
          ) : (
            <>
              <button type="button" onClick={startEditing} className="flex h-8 w-8 items-center justify-center rounded-full text-stone-600 hover:bg-stone-100 dark:text-stone-400 dark:hover:bg-stone-800" title="编辑 AI 概括"><PencilLine size={15} /></button>
              <button type="button" onClick={() => onGenerate?.("general")} disabled={generating || !canGenerate} className="flex h-8 w-8 items-center justify-center rounded-full text-accent hover:bg-accent/10 disabled:opacity-50" title="重新生成 AI 概括">{generating ? <LoaderCircle size={15} className="animate-spin" /> : <RefreshCw size={15} />}</button>
            </>
          )}
        </div>
      </div>
      <article className="rounded-3xl border border-stone-200/80 bg-white p-6 shadow-sm dark:border-stone-800 dark:bg-stone-950">
        {editing ? (
          <div className="flex flex-col gap-4">
            <input value={title} onChange={(event) => setTitle(event.target.value)} className="w-full rounded-xl border border-stone-200 bg-stone-50 px-4 py-3 text-lg font-bold text-stone-900 outline-none focus:border-accent dark:border-stone-800 dark:bg-stone-900 dark:text-stone-100" />
            <textarea value={content} onChange={(event) => setContent(event.target.value)} className="min-h-[360px] w-full resize-y rounded-xl border border-stone-200 bg-stone-50 px-4 py-3 text-sm leading-relaxed text-stone-900 outline-none focus:border-accent dark:border-stone-800 dark:bg-stone-900 dark:text-stone-100" />
          </div>
        ) : (
          <>
            <h1 className="text-2xl font-bold text-stone-900 dark:text-stone-100">{aiSummary.title}</h1>
            <div className="my-5 h-px bg-stone-100 dark:bg-stone-800" />
            <div className="markdown-body text-sm text-stone-700 dark:text-stone-300"><WorkspaceMarkdownMessage content={aiSummary.content} noteImageContext={noteImageContext} onSeek={onSeek} /></div>
          </>
        )}
      </article>
    </div>
  );
}
