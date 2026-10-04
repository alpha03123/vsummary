import { useEffect, useRef, useState } from "react";
import { Captions, FileText, LoaderCircle, Save, X } from "lucide-react";

export function WorkspaceContentEditorModal({
  onClose,
  onLoadSummaryMarkdown,
  onLoadTranscriptMarkdown,
  onUpdateSummary,
  onUpdateTranscript,
}) {
  const [tab, setTab] = useState("summary");
  const [summaryMarkdown, setSummaryMarkdown] = useState("");
  const [loadingSummary, setLoadingSummary] = useState(true);
  const [transcriptMarkdown, setTranscriptMarkdown] = useState("");
  const [loadingTranscript, setLoadingTranscript] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const backdropPointerDownRef = useRef(false);

  useEffect(() => {
    const onKeyDown = (event) => {
      if (event.key === "Escape" && !saving) {
        onClose();
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [onClose, saving]);

  useEffect(() => {
    let cancelled = false;
    onLoadSummaryMarkdown()
      .then((markdown) => {
        if (!cancelled) setSummaryMarkdown(markdown);
      })
      .catch((loadError) => {
        if (!cancelled) setError(loadError instanceof Error ? loadError.message : "概况读取失败");
      })
      .finally(() => {
        if (!cancelled) setLoadingSummary(false);
      });
    return () => { cancelled = true; };
  }, [onLoadSummaryMarkdown]);

  async function showTranscript() {
    setTab("transcript");
    if (transcriptMarkdown || loadingTranscript) {
      return;
    }
    setLoadingTranscript(true);
    setError("");
    try {
      setTranscriptMarkdown(await onLoadTranscriptMarkdown());
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : "转写读取失败");
    } finally {
      setLoadingTranscript(false);
    }
  }

  async function saveSummary() {
    setSaving(true);
    setError("");
    try {
      await onUpdateSummary(summaryMarkdown);
      onClose();
    } catch (saveError) {
      setError(saveError instanceof Error ? saveError.message : "概况保存失败");
    } finally {
      setSaving(false);
    }
  }

  async function saveTranscript() {
    if (!transcriptMarkdown) {
      return;
    }
    setSaving(true);
    setError("");
    try {
      await onUpdateTranscript(transcriptMarkdown);
      onClose();
    } catch (saveError) {
      setError(saveError instanceof Error ? saveError.message : "转写保存失败");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div
      className="fixed inset-0 z-[70] flex items-center justify-center bg-black/45 p-4 backdrop-blur-sm"
      role="presentation"
      onPointerDown={(event) => {
        backdropPointerDownRef.current = event.button === 0 && event.target === event.currentTarget;
      }}
      onPointerUp={(event) => {
        if (backdropPointerDownRef.current && event.target === event.currentTarget && !saving) onClose();
        backdropPointerDownRef.current = false;
      }}
    >
      <section className="workspace-panel flex h-[min(640px,calc(100vh-2rem))] w-full max-w-2xl flex-col rounded-lg border shadow-2xl" role="dialog" aria-modal="true" aria-labelledby="content-editor-title">
        <header className="flex items-center justify-between gap-4 border-b border-stone-200 px-5 py-4 dark:border-stone-800">
          <h2 id="content-editor-title" className="text-lg font-bold text-stone-900 dark:text-stone-100">编辑视频内容</h2>
          <button type="button" onClick={onClose} disabled={saving} aria-label="关闭编辑器" title="关闭" className="inline-flex h-9 w-9 items-center justify-center rounded-lg text-stone-600 hover:bg-stone-100 disabled:opacity-50 dark:text-stone-300 dark:hover:bg-neutral-800"><X size={18} /></button>
        </header>
        <div className="flex border-b border-stone-200 px-5 dark:border-stone-800">
          <button type="button" onClick={() => setTab("summary")} className={`inline-flex items-center gap-2 border-b-2 px-3 py-3 text-sm font-semibold ${tab === "summary" ? "border-accent text-accent" : "border-transparent text-stone-500 hover:text-stone-900 dark:text-stone-400 dark:hover:text-stone-100"}`}><FileText size={16} />概况</button>
          <button type="button" onClick={showTranscript} className={`inline-flex items-center gap-2 border-b-2 px-3 py-3 text-sm font-semibold ${tab === "transcript" ? "border-accent text-accent" : "border-transparent text-stone-500 hover:text-stone-900 dark:text-stone-400 dark:hover:text-stone-100"}`}><Captions size={16} />转写</button>
        </div>
        <div className="min-h-0 flex flex-1 flex-col gap-3 p-4">
          {tab === "summary" && loadingSummary ? <div className="flex flex-1 items-center justify-center text-sm text-stone-500"><LoaderCircle size={18} className="mr-2 animate-spin" />读取概况...</div> : null}
          {tab === "summary" && !loadingSummary ? <textarea aria-label="概况 Markdown" value={summaryMarkdown} onChange={(event) => setSummaryMarkdown(event.target.value)} spellCheck={false} className="min-h-0 flex-1 resize-none rounded-md border border-stone-300 bg-white p-3 font-mono text-sm leading-6 text-stone-900 outline-none focus:border-accent focus:ring-2 focus:ring-accent/20 dark:border-stone-700 dark:bg-neutral-900 dark:text-stone-100" /> : null}
          {tab === "transcript" && loadingTranscript ? <div className="flex flex-1 items-center justify-center text-sm text-stone-500"><LoaderCircle size={18} className="mr-2 animate-spin" />读取转写...</div> : null}
          {tab === "transcript" && !loadingTranscript ? <textarea aria-label="转写 Markdown" value={transcriptMarkdown} onChange={(event) => setTranscriptMarkdown(event.target.value)} spellCheck={false} className="min-h-0 flex-1 resize-none rounded-md border border-stone-300 bg-white p-3 font-mono text-sm leading-6 text-stone-900 outline-none focus:border-accent focus:ring-2 focus:ring-accent/20 dark:border-stone-700 dark:bg-neutral-900 dark:text-stone-100" /> : null}
          {error ? <p role="alert" className="mt-4 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700 dark:border-red-900/60 dark:bg-red-950/30 dark:text-red-300">{error}</p> : null}
        </div>
        <footer className="flex justify-end gap-3 border-t border-stone-200 px-5 py-4 dark:border-stone-800">
          <button type="button" onClick={onClose} disabled={saving} className="rounded-lg bg-stone-100 px-4 py-2 text-sm font-semibold text-stone-700 hover:bg-stone-200 disabled:opacity-50 dark:bg-neutral-800 dark:text-stone-200 dark:hover:bg-neutral-700">取消</button>
          <button type="button" disabled={saving || loadingSummary || (tab === "transcript" && !transcriptMarkdown)} onClick={tab === "summary" ? saveSummary : saveTranscript} className="inline-flex items-center gap-2 rounded-lg bg-accent px-4 py-2 text-sm font-bold text-white hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50"><Save size={16} />{saving ? "保存中..." : "保存"}</button>
        </footer>
      </section>
    </div>
  );
}
