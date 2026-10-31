import {useWorkspaceRuntime} from "../../runtime/WorkspaceProvider";
import { lazy, Suspense } from "react";

import { WorkspaceStateBlock } from "./shared/WorkspaceStateBlock";
import { WorkspaceToolGrid } from "./shared/WorkspaceToolGrid";
import { WorkspaceToolHeader } from "./shared/WorkspaceToolHeader";
import { buildWorkspaceToolExportActions } from "./workspaceToolExports";
import { isPlaygroundSeries } from "../model/workspaceControllerConstants";
import {
  SERIES_TOOL_TILES,
  SERIES_STUDIO_TOOL_TILES,
  SOURCE_MISSING_STATUS,
  TOOL_TILES,
  describeToolState,
  getToolState,
  resolveToolMeta,
} from "./workspaceToolMeta";

const WorkspaceKnowledgeCardsView = lazy(() =>
  import("./views/WorkspaceKnowledgeCardsView").then((module) => ({
    default: module.WorkspaceKnowledgeCardsView,
  })),
);
const WorkspaceMindmapView = lazy(() =>
  import("./views/WorkspaceMindmapView").then((module) => ({
    default: module.WorkspaceMindmapView,
  })),
);
const WorkspaceNotesView = lazy(() =>
  import("./views/WorkspaceNotesView").then((module) => ({
    default: module.WorkspaceNotesView,
  })),
);
const WorkspaceAiSummaryView = lazy(() =>
  import("./views/WorkspaceAiSummaryView").then((module) => ({ default: module.WorkspaceAiSummaryView })),
);
const WorkspaceOverviewView = lazy(() =>
  import("./views/WorkspaceOverviewView").then((module) => ({
    default: module.WorkspaceOverviewView,
  })),
);
const WorkspacePreviewView = lazy(() =>
  import("./views/WorkspacePreviewView").then((module) => ({
    default: module.WorkspacePreviewView,
  })),
);
const WorkspaceSeriesHomeView = lazy(() =>
  import("./views/WorkspaceSeriesHomeView").then((module) => ({
    default: module.WorkspaceSeriesHomeView,
  })),
);
const WorkspaceSeriesMindmapView = lazy(() =>
  import("./views/WorkspaceSeriesMindmapView").then((module) => ({
    default: module.WorkspaceSeriesMindmapView,
  })),
);
const WorkspaceSeriesOverviewView = lazy(() =>
  import("./views/WorkspaceSeriesOverviewView").then((module) => ({
    default: module.WorkspaceSeriesOverviewView,
  })),
);

const WorkspaceStudioHomeView = lazy(() =>
  import("./views/WorkspaceStudioHomeView").then((module) => ({
    default: module.WorkspaceStudioHomeView,
  })),
);

export function WorkspaceReadingPane({
  ui,
  tools,
  chat,
  summary,
  aiSummary,
  playbackTime,
  followOverviewPlayback,
  onFollowOverviewPlaybackChange,
  mindmap,
  knowledgeCards,
  knowledgeCardsGenerating,
  knowledgeCardsGenerationProgress,
  knowledgeCardsFeedback,
  notes,
  activeSeries,
  selectedVideo,
  selectedContextType,
  selectedNode,
  previewUrl,
  playerSeekRequest,
  citationFocus,
  toolId,
  selectedChapterId,
  summaryLoading,
  aiSummaryLoading,
  generatingAiSummary,
  mindmapLoading,
  knowledgeCardsLoading,
  notesLoading,
  savingNote,
  isGeneratingMindmapSelectedVideo,
  isGeneratingSelectedVideo,
  seriesMindmap,
  seriesMindmapAvailable,
  seriesMindmapLoading,
  seriesOverviewSummariesByVideoId,
  seriesOverviewLoading,
  generatingSeriesMindmap,
  onGenerateSeriesMindmap,
  onSelectVideo,
  mindmapGenerationProgress,
  onSelectTool,
  onFocusNode,
  onSeek,
  onGenerateMindmap,
  onGenerateKnowledgeCards,
  onClearKnowledgeCardsFeedback,
  onGenerateAiSummary,
  onUpdateAiSummary,
  onCreateNote,
  onUpdateNote,
  onDeleteNote,
  onLoadTranscriptMarkdown,
  onLoadSummaryMarkdown,
  onUpdateSummary,
  onUpdateTranscript,
  onUploadSrt,
  onRestoreAutomaticTranscript,
  onOpenCitationReference,
  onPanelSelectTool = null,
  embeddedInStudioPanel = false,
}) {
 const {api,host}=useWorkspaceRuntime();
  const isStudioHome = toolId === "studio";
  const isSeriesHome = toolId === "series-home";
  const isMindmapTool = toolId === "mindmap" || toolId === "series-mindmap";
  const isPlaygroundHome = isPlaygroundSeries(activeSeries) && !selectedVideo;
  const currentToolMeta = resolveToolMeta(toolId);
  const rawPreviewSource = tools?.preview?.previewUrl ?? previewUrl;
  const previewSource = rawPreviewSource ? api.resourceUrl(rawPreviewSource) : undefined;
  const previewSubtitleSource = tools?.preview?.subtitleUrl ?? null;
  const toolHeaderBadge = resolveSeriesOverviewBadge({
    toolId,
    activeSeries,
    seriesOverviewSummariesByVideoId,
    seriesOverviewLoading,
  });
  const sourceMissing = selectedVideo?.status === "source_missing";

  function openAiSummaryTranscript(reference) {
    if (!reference || !Number.isFinite(reference.seconds)) {
      return;
    }
    onOpenCitationReference?.({
      ...reference,
      videoId: reference.videoId || selectedVideo?.id,
    });
  }

  return (
    <section className="@container relative flex h-full w-full flex-col bg-transparent">
      {/* 面板宽度是拖拽的（最小 320px），字号与间距都比视口更早到临界点：
          这里按容器宽度整体收一档，否则窄面板下每层留白叠加起来要拉很长才换行。 */}
      <div className={`flex flex-1 flex-col ${isMindmapTool ? "overflow-hidden p-0" : "gap-3 overflow-auto p-4 @[480px]:gap-5 @[480px]:p-6"}`}>
        {!activeSeries ? (
          <WorkspaceStateBlock
            title="等待系列"
            description="从左侧打开一个系列，这里会显示它的工具。"
            dashed
          />
        ) : (
          <div key={`${selectedContextType}:${toolId}:${selectedVideo?.id ?? activeSeries.id}`} className="motion-fade-scale flex h-full min-h-0 flex-col">
            {!embeddedInStudioPanel && !(isStudioHome && onPanelSelectTool) ? (
              <header className="mb-3 flex shrink-0 flex-col gap-3 border-b border-stone-200/80 pb-3 dark:border-white/5 @[480px]:mb-5 @[480px]:gap-5 @[480px]:pb-5">
              {isStudioHome ? (
                <WorkspaceHomeHeader
                  title={isPlaygroundHome ? activeSeries.title : summary?.title ?? selectedVideo?.title}
                  description={isPlaygroundHome ? "从左侧选择一个媒体文件，进入对应的单项工具页。" : "选择下方任意卡片进入独立工具页"}
                />
              ) : isSeriesHome ? (
                <WorkspaceHomeHeader
                  title={activeSeries.title}
                  description="可以在对话栏里问整个系列的内容。"
                >
                </WorkspaceHomeHeader>
              ) : (
                <WorkspaceToolHeader
                  meta={currentToolMeta}
                  badge={toolHeaderBadge}
                  aiGenerated={toolId !== "notes"}
                  onBack={() => onSelectTool(selectedContextType === "series" ? "series-home" : "studio")}
                  exportActions={buildWorkspaceToolExportActions({
                    activeSeries,
                    notes,
                    summary,
                    toolId,
                    selectedVideo,
                    tools,
                  })}
                />
              )}
              </header>
            ) : null}

            <div className={`relative min-h-0 flex-1 ${isMindmapTool ? "overflow-hidden" : "overflow-y-auto"}`}>
              <Suspense fallback={<WorkspaceToolLoadingState toolName={currentToolMeta.label} />}>
                  {isSeriesHome ? (
                    <div className="flex flex-col gap-6">
                      <WorkspaceToolGrid
                        items={buildSeriesToolItems({ activeSeries, seriesMindmapAvailable })}
                        onSelect={onSelectTool}
                      />
                      <WorkspaceSeriesHomeView activeSeries={activeSeries} />
                    </div>
                  ) : null}
                  {toolId === "series-mindmap" ? (
                    <WorkspaceSeriesMindmapView
                      seriesId={activeSeries.id}
                      seriesMindmap={seriesMindmap}
                      seriesMindmapAvailable={seriesMindmapAvailable}
                      seriesMindmapLoading={seriesMindmapLoading}
                      generatingSeriesMindmap={generatingSeriesMindmap}
                      selectedNode={selectedNode}
                      onFocusNode={onFocusNode}
                      onGenerateSeriesMindmap={onGenerateSeriesMindmap}
                      mindmapGenerationProgress={mindmapGenerationProgress}
                      theme={ui?.theme}
                    />
                  ) : null}
                  {toolId === "series-overview" ? (
                    <WorkspaceSeriesOverviewView
                      activeSeries={activeSeries}
                      ui={ui}
                      summariesByVideoId={seriesOverviewSummariesByVideoId}
                      loading={seriesOverviewLoading}
                      citationFocus={citationFocus}
                      onOpenVideoOverview={(videoId) => {
                        onSelectVideo(activeSeries.id, videoId);
                        onSelectTool("overview");
                      }}
                    />
                  ) : null}
                  {isStudioHome ? (
                    <div className="pb-8 pt-2">
                      {isPlaygroundHome ? (
                        <WorkspaceStateBlock
                          title="选择要处理的视频文件"
                          description=""
                          dashed
                        />
                      ) : (
                        <WorkspaceToolGrid
                          items={Object.entries(selectedContextType === "series" ? SERIES_STUDIO_TOOL_TILES : TOOL_TILES)
                            .filter(([toolId]) => toolId !== 'preview' || host.features?.mediaPreview !== false)
                            .map(([toolId, meta]) => ({
                              id: toolId,
                              meta,
                              disabled: sourceMissing || getToolState(tools, toolId)?.available === false,
                              status: sourceMissing
                                ? SOURCE_MISSING_STATUS
                                : describeToolState(toolId, getToolState(tools, toolId)),
                            }))}
                          onSelect={onSelectTool}
                        />
                      )}
                    </div>
                  ) : null}
                  {toolId === "overview" ? (
                    <WorkspaceOverviewView
                      ui={ui}
                      tools={tools}
                      summary={summary}
                      playbackTime={playbackTime}
                      followOverviewPlayback={followOverviewPlayback}
                      onFollowOverviewPlaybackChange={onFollowOverviewPlaybackChange}
                      selectedVideo={selectedVideo}
                      selectedChapterId={selectedChapterId}
                      citationFocus={citationFocus}
                      summaryLoading={summaryLoading}
                      isGeneratingSelectedVideo={isGeneratingSelectedVideo}
                      onSeek={onSeek}
                      onLoadTranscriptMarkdown={onLoadTranscriptMarkdown}
                      onLoadSummaryMarkdown={onLoadSummaryMarkdown}
                      onUpdateSummary={onUpdateSummary}
                      onUpdateTranscript={onUpdateTranscript}
                      onOpenAiSummary={() => onSelectTool("ai-summary")}
                      onUploadSrt={onUploadSrt}
                      onRestoreAutomaticTranscript={onRestoreAutomaticTranscript}
                    />
                  ) : null}
                  {toolId === "ai-summary" ? (
                    <WorkspaceAiSummaryView
                      aiSummary={aiSummary}
                      loading={aiSummaryLoading}
                      generating={generatingAiSummary || tools?.aiSummary?.status === "running"}
                      canGenerate={!(selectedVideo?.isLinked === true || selectedVideo?.status === "linked")}
                      canEdit={host.features?.aiSummaryEditing !== false}
                      canRegenerate={host.features?.sourceRegeneration !== false}
                      onGenerate={onGenerateAiSummary}
                      onUpdate={onUpdateAiSummary}
                      noteImageContext={activeSeries && selectedVideo ? { seriesId: activeSeries.id, videoId: selectedVideo.id, durationSeconds: Number.POSITIVE_INFINITY } : null}
                      onSeek={onSeek}
                      onOpenCitationReference={openAiSummaryTranscript}
                      onOpenTranscriptAtTime={openAiSummaryTranscript}
                    />
                  ) : null}
                  {toolId === "mindmap" ? (
                    <WorkspaceMindmapView
                      tools={tools}
                      mindmap={mindmap}
                      selectedNode={selectedNode}
                      mindmapLoading={mindmapLoading}
                      isGeneratingMindmapSelectedVideo={isGeneratingMindmapSelectedVideo}
                      onFocusNode={onFocusNode}
                      onGenerateMindmap={onGenerateMindmap}
                      seriesId={activeSeries?.id}
                      videoId={selectedVideo?.id}
                      mindmapGenerationProgress={mindmapGenerationProgress}
                      theme={ui?.theme}
                    />
                  ) : null}
                  {toolId === "knowledge-cards" ? (
                    <WorkspaceKnowledgeCardsView
                      tools={tools}
                      knowledgeCards={knowledgeCards}
                      knowledgeCardsGenerating={knowledgeCardsGenerating}
                      knowledgeCardsGenerationProgress={knowledgeCardsGenerationProgress}
                      knowledgeCardsFeedback={knowledgeCardsFeedback}
                      knowledgeCardsLoading={knowledgeCardsLoading}
                      onGenerateKnowledgeCards={onGenerateKnowledgeCards}
                      onClearKnowledgeCardsFeedback={onClearKnowledgeCardsFeedback}
                    />
                  ) : null}
                  {toolId === "notes" ? (
                    <WorkspaceNotesView
                      notes={notes}
                      notesLoading={notesLoading}
                      savingNote={savingNote}
                      onCreateNote={onCreateNote}
                      onUpdateNote={onUpdateNote}
                      onDeleteNote={onDeleteNote}
                      noteImageContext={activeSeries && selectedVideo ? {
                        seriesId: activeSeries.id,
                        videoId: selectedVideo.id,
                        durationSeconds: Array.isArray(summary?.chapters)
                          ? Math.max(0, ...summary.chapters.map((chapter) => Number.isFinite(chapter.end_seconds) ? chapter.end_seconds : 0))
                          : Number.POSITIVE_INFINITY,
                      } : null}
                      onSeek={onSeek}
                    />
                  ) : null}
                  {toolId === "preview" ? (
                    <WorkspacePreviewView previewSource={previewSource} previewSubtitleSource={previewSubtitleSource} previewSeekRequest={playerSeekRequest} />
                  ) : null}
              </Suspense>
            </div>
          </div>
        )}
      </div>
    </section>
  );
}

/**
 * 会话标题由用户/Agent 生成，可能整条只是一个分隔符（例如 "·"），
 * 之前会被原样渲染成卡片上的状态文字。这里先剥掉首尾装饰性标点，
 * 再截断；只有确实没有内容时才回退到"当前对话"。
 */
function buildSeriesToolItems({ activeSeries, seriesMindmapAvailable }) {
  const videos = activeSeries?.videos ?? [];
  const processedVideoCount = videos.filter((video) => video.processed).length;

  return Object.entries(SERIES_TOOL_TILES).map(([toolId, meta]) => ({
    id: toolId,
    meta,
    status: resolveSeriesToolStatus({ toolId, processedVideoCount, totalVideoCount: videos.length, seriesMindmapAvailable }),
  }));
}

function resolveSeriesToolStatus({ toolId, processedVideoCount, totalVideoCount, seriesMindmapAvailable }) {
  if (toolId === "series-overview") {
    return totalVideoCount === 0
      ? { label: "暂无视频", tone: "pending" }
      : processedVideoCount > 0
        ? { label: `已处理 ${processedVideoCount} / ${totalVideoCount} 视频`, tone: "ready" }
        : { label: "等待视频处理", tone: "pending" };
  }

  if (toolId === "series-mindmap") {
    return seriesMindmapAvailable
      ? { label: "可生成", tone: "pending" }
      : { label: "需先生成 AI 概括", tone: "blocked" };
  }

  return null;
}

function resolveSeriesOverviewBadge({
  toolId,
  activeSeries,
  seriesOverviewSummariesByVideoId,
  seriesOverviewLoading,
}) {
  if (toolId !== "series-overview" || seriesOverviewLoading) {
    return null;
  }
  const videos = activeSeries?.videos ?? [];
  if (!videos.length) {
    return null;
  }
  const generated = videos.filter((video) => seriesOverviewSummariesByVideoId?.[video.id]).length;
  return `${generated} / ${videos.length} 视频概括`;
}

function WorkspaceHomeHeader({ title, description, children }) {
  return (
    <div className="flex flex-wrap items-start justify-between gap-4">
      <div className="min-w-[min(100%,20rem)] flex-1">
        <h2 className="break-words text-2xl font-bold leading-snug text-stone-900 dark:text-stone-100">{title}</h2>
        <p className="mt-2 text-sm text-stone-600 dark:text-stone-400">{description}</p>
      </div>
      {children ? <div className="ml-auto shrink-0">{children}</div> : null}
    </div>
  );
}

function WorkspaceToolLoadingState({ toolName }) {
  return (
    <WorkspaceStateBlock
      title={`正在载入${toolName}`}
      loading
    />
  );
}
