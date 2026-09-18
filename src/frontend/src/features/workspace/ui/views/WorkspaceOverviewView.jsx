import { useState } from "react";
import { LoaderCircle, Pencil } from "lucide-react";

import { WorkspaceStateBlock } from "../shared/WorkspaceStateBlock";
import { WorkspaceContentEditorModal } from "./WorkspaceContentEditorModal";
import { WorkspaceOverviewContent } from "./WorkspaceOverviewContent";

export function WorkspaceOverviewView({
  ui,
  tools,
  summary,
  playbackTime,
  followOverviewPlayback,
  onFollowOverviewPlaybackChange,
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
  onOpenAiSummary,
}) {
  const [editorOpen, setEditorOpen] = useState(false);
  const hasSummary = Boolean(summary);
  const overviewTitle = summary?.title ?? selectedVideo?.title ?? "AI 整理逐字稿";

  if (!selectedVideo) {
    return (
      <WorkspaceStateBlock
        eyebrow="AI Transcript"
        title="等待视频"
        description="先在左侧选中一个具体视频，这里才会显示对应的整理逐字稿。"
        dashed
      />
    );
  }

  if (!tools?.overview.generated) {
    return (
      <WorkspaceStateBlock
        eyebrow="AI Transcript"
        title={overviewTitle}
        description="整理逐字稿会在 AI 概括生成流程中一并生成，包含章节、时间轴与原文定位。"
        actionLabel="前往 AI 概括"
        onAction={onOpenAiSummary}
      >
        {isGeneratingSelectedVideo ? (
          <div className="motion-fade-up mt-6 w-full max-w-xl">
            <div className="motion-busy-button inline-flex items-center gap-2 rounded-full border border-stone-200 bg-white px-4 py-2 text-sm text-stone-600 shadow-sm">
              <LoaderCircle size={16} strokeWidth={2.2} className="animate-spin text-accent" />
              正在整理逐字稿...
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
        eyebrow="AI Transcript"
        title={overviewTitle}
        description="正在读取已生成的整理逐字稿。"
        loading
      />
    );
  }

  if (!hasSummary) {
    return null;
  }

  return (
    <div className="mx-auto flex w-full max-w-3xl flex-col gap-8 pb-32">
      {isGeneratingSelectedVideo ? (
        <div className="flex items-center gap-2 rounded-lg border border-accent/25 bg-accent/5 px-3 py-2 text-sm text-stone-700 dark:text-stone-200">
          <LoaderCircle size={16} className="animate-spin text-accent" />
          正在整理逐字稿，当前仍显示上一次结果。
        </div>
      ) : null}
      <div className="flex flex-wrap justify-end gap-2">
        <button type="button" onClick={() => setEditorOpen(true)} className="inline-flex items-center gap-2 rounded-lg border border-stone-200 bg-white px-3 py-2 text-sm font-semibold text-stone-700 shadow-sm transition-colors hover:bg-stone-100 dark:border-stone-700 dark:bg-neutral-900 dark:text-stone-200 dark:hover:bg-neutral-800"><Pencil size={16} />编辑内容</button>
      </div>
      <WorkspaceOverviewContent
        ui={ui}
        summary={summary}
        playbackTime={playbackTime}
        followOverviewPlayback={followOverviewPlayback}
        onFollowOverviewPlaybackChange={onFollowOverviewPlaybackChange}
        selectedChapterId={selectedChapterId}
        citationFocus={citationFocus}
        onSeek={onSeek}
      />
      {editorOpen ? <WorkspaceContentEditorModal onClose={() => setEditorOpen(false)} onLoadSummaryMarkdown={onLoadSummaryMarkdown} onLoadTranscriptMarkdown={onLoadTranscriptMarkdown} onUpdateSummary={onUpdateSummary} onUpdateTranscript={onUpdateTranscript} /> : null}
    </div>
  );
}
