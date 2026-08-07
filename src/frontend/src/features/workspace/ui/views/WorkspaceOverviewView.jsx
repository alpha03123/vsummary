import { useRef, useState } from "react";
import { FileUp, LoaderCircle, Pencil, RotateCcw } from "lucide-react";

import { WorkspaceStateBlock } from "../shared/WorkspaceStateBlock";
import { WorkspaceConfirmDialog } from "../shared/WorkspaceConfirmDialog";
import { WorkspaceContentEditorModal } from "./WorkspaceContentEditorModal";
import { WorkspaceOverviewContent } from "./WorkspaceOverviewContent";

export function WorkspaceOverviewView({
  ui,
  tools,
  summary,
  selectedVideo,
  selectedChapterId,
  citationFocus,
  summaryLoading,
  isGeneratingSelectedVideo,
  onSeek,
  onLoadTranscriptMarkdown,
  onLoadSummaryMarkdown,
  onUpdateSummary,
  onUpdateTranscript,
  onUploadSrt,
  onRestoreAutomaticTranscript,
}) {
  const [editorOpen, setEditorOpen] = useState(false);
  const hasSummary = Boolean(summary);
  const overviewTitle = summary?.title ?? selectedVideo?.title ?? "AI 概况";

  if (!selectedVideo) {
    return (
      <WorkspaceStateBlock
        eyebrow="AI Overview"
        title="等待视频"
        description="先在左侧选中一个具体视频，这里才会显示对应的 AI 概况。"
        dashed
      />
    );
  }

  if (!tools?.overview.generated) {
    return (
      <WorkspaceStateBlock
        eyebrow="AI Overview"
        title={overviewTitle}
        description="先在左侧点击生成，生成完成后这里会显示 AI 概况、章节纪要和关键结论。"
      >
        <OverviewTranscriptActions
          summary={summary}
          disabled={isGeneratingSelectedVideo}
          onUploadSrt={onUploadSrt}
          onRestoreAutomaticTranscript={onRestoreAutomaticTranscript}
        />
        {isGeneratingSelectedVideo ? (
          <div className="motion-fade-up mt-6 w-full max-w-xl">
            <div className="motion-busy-button inline-flex items-center gap-2 rounded-full border border-stone-200 bg-white px-4 py-2 text-sm text-stone-600 shadow-sm">
              <LoaderCircle size={16} strokeWidth={2.2} className="animate-spin text-accent" />
              正在生成概况...
            </div>
            <div className="workspace-elevated-panel mt-6 rounded-3xl border p-6">
              <div className="motion-shimmer h-3 w-24 rounded-full bg-stone-100 dark:bg-stone-800"></div>
              <div className="motion-shimmer mt-5 h-7 w-3/4 rounded-2xl bg-stone-100 dark:bg-stone-800"></div>
              <div className="motion-shimmer mt-4 h-4 w-full rounded-full bg-stone-100 dark:bg-stone-800"></div>
              <div className="motion-shimmer mt-3 h-4 w-5/6 rounded-full bg-stone-100 dark:bg-stone-800"></div>
              <div className="motion-shimmer mt-8 h-24 w-full rounded-[1.5rem] bg-stone-100 dark:bg-stone-800"></div>
            </div>
          </div>
        ) : null}
      </WorkspaceStateBlock>
    );
  }

  if (summaryLoading) {
    return (
      <WorkspaceStateBlock
        eyebrow="AI Overview"
        title={overviewTitle}
        description="正在读取已生成的概况结果。"
        loading
      />
    );
  }

  if (!hasSummary) {
    return null;
  }

  return (
    <div className="w-full max-w-3xl mx-auto flex flex-col gap-8 pb-32">
      {isGeneratingSelectedVideo ? (
        <div className="flex items-center gap-2 rounded-lg border border-accent/25 bg-accent/5 px-3 py-2 text-sm text-stone-700 dark:text-stone-200">
          <LoaderCircle size={16} className="animate-spin text-accent" />
          正在生成概况，当前仍显示上一次结果。
        </div>
      ) : null}
      <div className="flex flex-wrap justify-end gap-2">
        <OverviewTranscriptActions
          summary={summary}
          disabled={isGeneratingSelectedVideo}
          onUploadSrt={onUploadSrt}
          onRestoreAutomaticTranscript={onRestoreAutomaticTranscript}
        />
        <button type="button" onClick={() => setEditorOpen(true)} className="inline-flex items-center gap-2 rounded-lg border border-stone-200 bg-white px-3 py-2 text-sm font-semibold text-stone-700 shadow-sm transition-colors hover:bg-stone-100 dark:border-stone-700 dark:bg-neutral-900 dark:text-stone-200 dark:hover:bg-neutral-800"><Pencil size={16} />编辑内容</button>
      </div>
      <WorkspaceOverviewContent
        ui={ui}
        summary={summary}
        selectedChapterId={selectedChapterId}
        citationFocus={citationFocus}
        onSeek={onSeek}
      />
      {editorOpen ? <WorkspaceContentEditorModal onClose={() => setEditorOpen(false)} onLoadSummaryMarkdown={onLoadSummaryMarkdown} onLoadTranscriptMarkdown={onLoadTranscriptMarkdown} onUpdateSummary={onUpdateSummary} onUpdateTranscript={onUpdateTranscript} /> : null}
    </div>
  );
}

function OverviewTranscriptActions({ summary, disabled, onUploadSrt, onRestoreAutomaticTranscript }) {
  const inputRef = useRef(null);
  const [selectedFile, setSelectedFile] = useState(null);
  const [restoreOpen, setRestoreOpen] = useState(false);
  const hasManualSrt = summary?.transcriptSource === "manual_srt";

  return (
    <>
      {hasManualSrt ? (
        <span className="inline-flex items-center rounded-lg border border-accent/25 bg-accent/5 px-3 py-2 text-sm font-medium text-accent">
          人工 SRT
        </span>
      ) : null}
      <input
        ref={inputRef}
        type="file"
        accept=".srt,application/x-subrip,text/plain"
        className="hidden"
        onChange={(event) => {
          const file = event.target.files?.[0] ?? null;
          setSelectedFile(file);
          event.target.value = "";
        }}
      />
      <button
        type="button"
        disabled={disabled}
        onClick={() => inputRef.current?.click()}
        className="inline-flex items-center gap-2 rounded-lg border border-stone-200 bg-white px-3 py-2 text-sm font-semibold text-stone-700 shadow-sm transition-colors hover:bg-stone-100 disabled:cursor-not-allowed disabled:opacity-50 dark:border-stone-700 dark:bg-neutral-900 dark:text-stone-200 dark:hover:bg-neutral-800"
      >
        <FileUp size={16} />导入 SRT
      </button>
      {hasManualSrt ? (
        <button
          type="button"
          disabled={disabled}
          onClick={() => setRestoreOpen(true)}
          className="inline-flex items-center gap-2 rounded-lg border border-stone-200 bg-white px-3 py-2 text-sm font-semibold text-stone-700 shadow-sm transition-colors hover:bg-stone-100 disabled:cursor-not-allowed disabled:opacity-50 dark:border-stone-700 dark:bg-neutral-900 dark:text-stone-200 dark:hover:bg-neutral-800"
        >
          <RotateCcw size={16} />改用自动转写
        </button>
      ) : null}
      <WorkspaceConfirmDialog
        open={selectedFile != null}
        title="导入 SRT"
        description={`将使用 ${selectedFile?.name ?? "所选字幕"} 重新生成概况，您当前的内容将会被覆盖。`}
        confirmLabel="开始生成"
        onCancel={() => setSelectedFile(null)}
        onConfirm={() => {
          if (selectedFile) {
            onUploadSrt?.(selectedFile);
          }
          setSelectedFile(null);
        }}
      />
      <WorkspaceConfirmDialog
        open={restoreOpen}
        title="确认恢复自动转写？"
        description="系统将重新自动生成字幕和概况，您手动编辑的内容将会被覆盖。"
        confirmLabel="开始生成"
        onCancel={() => setRestoreOpen(false)}
        onConfirm={() => {
          onRestoreAutomaticTranscript?.();
          setRestoreOpen(false);
        }}
      />
    </>
  );
}
