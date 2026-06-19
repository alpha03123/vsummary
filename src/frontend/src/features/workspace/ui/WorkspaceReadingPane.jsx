import { lazy, Suspense } from "react";

import { WorkspaceStateBlock } from "./shared/WorkspaceStateBlock";
import { WorkspaceToolGrid } from "./shared/WorkspaceToolGrid";
import { WorkspaceToolHeader } from "./shared/WorkspaceToolHeader";
import {
  SERIES_TOOL_TILES,
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

const WorkspaceChatManagementView = lazy(() =>
  import("./views/WorkspaceChatManagementView").then((module) => ({
    default: module.WorkspaceChatManagementView,
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
  mindmap,
  knowledgeCards,
  knowledgeCardsGenerating,
  knowledgeCardsFeedback,
  notes,
  activeSeries,
  selectedVideo,
  selectedContextType,
  selectedNode,
  previewUrl,
  playerSeekRequest,
  selectedToolId,
  selectedChapterId,
  toolsLoading,
  summaryLoading,
  mindmapLoading,
  knowledgeCardsLoading,
  notesLoading,
  savingNote,
  isGeneratingMindmapSelectedVideo,
  isGeneratingSelectedVideo,
  seriesMindmap,
  seriesMindmapAvailable,
  seriesMindmapLoading,
  generatingSeriesMindmap,
  onGenerateSeriesMindmap,
  mindmapGenerationProgress,
  onSelectTool,
  onFocusNode,
  onSeek,
  onGenerateMindmap,
  onGenerateKnowledgeCards,
  onClearKnowledgeCardsFeedback,
  onCreateNote,
  onUpdateNote,
  onDeleteNote,
}) {
  const isStudioHome = selectedToolId === "studio";
  const isSeriesHome = selectedToolId === "series-home";
  const isPlaygroundHome = activeSeries?.id === "__playground__" && !selectedVideo;
  const currentToolMeta = resolveToolMeta(selectedToolId);
  const previewSource = tools?.preview?.previewUrl ?? previewUrl ?? undefined;

  return (
    <section className="relative flex h-full w-full flex-col bg-transparent">
      <div className="flex flex-1 flex-col gap-5 overflow-auto p-6">
        {!activeSeries ? (
          <WorkspaceStateBlock
            title="等待系列"
            description="先进入一个 series，右侧才会显示系列或视频工具。"
            dashed
          />
        ) : (
          <div key={`${selectedContextType}:${selectedToolId}:${selectedVideo?.id ?? activeSeries.id}`} className="motion-fade-scale flex h-full min-h-0 flex-col">
            <header className="mb-5 flex shrink-0 flex-col gap-5 border-b border-stone-200/80 pb-5 dark:border-white/5">
              {isStudioHome ? (
                <WorkspaceHomeHeader
                  eyebrow="Studio"
                  title={isPlaygroundHome ? activeSeries.title : summary?.title ?? selectedVideo?.title}
                  description={isPlaygroundHome ? "从左侧选择一个媒体文件，进入对应的单项工具页。" : "选择下方任意卡片进入独立工具页"}
                />
              ) : isSeriesHome ? (
                <WorkspaceHomeHeader
                  eyebrow="Series Home"
                  title={activeSeries.title}
                  description="你可以在当前对话栏询问关于整个系列的问题。"
                />
              ) : (
                <WorkspaceToolHeader
                  meta={currentToolMeta}
                  onBack={() => onSelectTool(selectedContextType === "series" ? "series-home" : "studio")}
                  exportActions={buildExportActions({
                    activeSeries,
                    notes,
                    selectedToolId,
                    selectedVideo,
                    tools,
                  })}
                />
              )}
            </header>

            <div className="relative min-h-0 flex-1 overflow-y-auto">
              {toolsLoading ? (
                <WorkspaceStateBlock
                  title="读取工具状态"
                  description="正在同步当前视频的工具状态。"
                  loading
                />
              ) : null}

              {!toolsLoading ? (
                <Suspense fallback={<WorkspaceToolLoadingState toolName={currentToolMeta.label} />}>
                  {isSeriesHome ? (
                    <div className="flex flex-col gap-6">
                      <WorkspaceToolGrid
                        items={Object.entries(SERIES_TOOL_TILES).map(([toolId, meta]) => ({
                          id: toolId,
                          meta,
                          hint: "series 级工具",
                        }))}
                        onSelect={onSelectTool}
                      />
                      <WorkspaceSeriesHomeView activeSeries={activeSeries} />
                    </div>
                  ) : null}
                  {selectedToolId === "series-mindmap" ? (
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
                    />
                  ) : null}
                  {isStudioHome ? (
                    <div className="pb-8 pt-2">
                      {isPlaygroundHome ? (
                        <WorkspaceStateBlock
                          eyebrow="Playground"
                          title="选择一个 Playground 媒体文件"
                          description=""
                          dashed
                        />
                      ) : (
                        <WorkspaceToolGrid
                          items={Object.entries(TOOL_TILES)
                            .filter(([toolId]) => ui.layoutMode === "chat_center" || toolId !== "preview")
                            .map(([toolId, meta]) => ({
                              id: toolId,
                              meta,
                              disabled: getToolState(tools, toolId)?.available === false,
                              hint: describeToolState(toolId, getToolState(tools, toolId)),
                            }))}
                          onSelect={onSelectTool}
                        />
                      )}
                    </div>
                  ) : null}
                  {selectedToolId === "overview" ? (
                    <WorkspaceOverviewView
                      ui={ui}
                      tools={tools}
                      summary={summary}
                      selectedVideo={selectedVideo}
                      selectedChapterId={selectedChapterId}
                      summaryLoading={summaryLoading}
                      isGeneratingSelectedVideo={isGeneratingSelectedVideo}
                      onSeek={onSeek}
                    />
                  ) : null}
                  {selectedToolId === "mindmap" ? (
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
                    />
                  ) : null}
                  {selectedToolId === "knowledge-cards" ? (
                    <WorkspaceKnowledgeCardsView
                      tools={tools}
                      knowledgeCards={knowledgeCards}
                      knowledgeCardsGenerating={knowledgeCardsGenerating}
                      knowledgeCardsFeedback={knowledgeCardsFeedback}
                      knowledgeCardsLoading={knowledgeCardsLoading}
                      onGenerateKnowledgeCards={onGenerateKnowledgeCards}
                      onClearKnowledgeCardsFeedback={onClearKnowledgeCardsFeedback}
                    />
                  ) : null}
                  {selectedToolId === "chat-management" || selectedToolId === "series-chat-management" ? (
                    <WorkspaceChatManagementView chat={chat} />
                  ) : null}
                  {selectedToolId === "notes" ? (
                    <WorkspaceNotesView
                      notes={notes}
                      notesLoading={notesLoading}
                      savingNote={savingNote}
                      onCreateNote={onCreateNote}
                      onUpdateNote={onUpdateNote}
                      onDeleteNote={onDeleteNote}
                    />
                  ) : null}
                  {selectedToolId === "preview" ? (
                    <WorkspacePreviewView previewSource={previewSource} previewSeekRequest={playerSeekRequest} />
                  ) : null}
                </Suspense>
              ) : null}
            </div>
          </div>
        )}
      </div>
    </section>
  );
}

function buildExportActions({ activeSeries, notes, selectedToolId, selectedVideo, tools }) {
  if (!activeSeries || !selectedVideo) {
    return [];
  }
  if (selectedToolId === "overview") {
    const overviewGenerated = tools?.overview?.generated === true;
    return [
      {
        href: videoExportUrl(activeSeries.id, selectedVideo.id, "summary"),
        enabled: overviewGenerated,
        label: "概况导出",
        disabledReason: "AI 概况生成后才能导出",
      },
      {
        href: videoExportUrl(activeSeries.id, selectedVideo.id, "transcript"),
        enabled: overviewGenerated,
        label: "转写导出",
        disabledReason: "AI 概况生成后才能导出",
      },
      {
        href: videoExportUrl(activeSeries.id, selectedVideo.id, "mixed"),
        enabled: overviewGenerated,
        label: "混合导出",
        disabledReason: "AI 概况生成后才能导出",
      },
    ];
  }
  if (selectedToolId === "knowledge-cards") {
    return [
      {
        href: videoExportUrl(activeSeries.id, selectedVideo.id, "knowledge-cards"),
        enabled: tools?.knowledgeCards?.generated === true,
        label: "知识卡片导出",
        disabledReason: "知识卡片生成后才能导出",
      },
    ];
  }
  if (selectedToolId === "notes") {
    return [
      {
        href: videoExportUrl(activeSeries.id, selectedVideo.id, "notes"),
        enabled: Boolean(notes?.notes?.length),
        label: "笔记导出",
        disabledReason: "有笔记后才能导出",
      },
    ];
  }
  if (selectedToolId === "preview") {
    return [
      {
        href: videoSourceExportUrl(activeSeries.id, selectedVideo.id),
        enabled: tools?.preview?.available === true,
        label: "视频导出",
        disabledReason: "视频源存在后才能导出",
      },
    ];
  }
  return [];
}

function videoExportUrl(seriesId, videoId, exportName) {
  return `/api/videos/${encodeURIComponent(seriesId)}/${encodeURIComponent(videoId)}/exports/${exportName}.md`;
}

function videoSourceExportUrl(seriesId, videoId) {
  return `/api/videos/${encodeURIComponent(seriesId)}/${encodeURIComponent(videoId)}/exports/video`;
}
function WorkspaceHomeHeader({ eyebrow, title, description, children }) {
  return (
    <>
      <div>
        <p className="mb-1 text-xs font-bold uppercase text-stone-500 dark:text-stone-400">{eyebrow}</p>
        <h2 className="text-2xl font-bold leading-snug text-stone-900 dark:text-stone-100">{title}</h2>
        <p className="mt-2 text-sm text-stone-500 dark:text-stone-400">{description}</p>
      </div>
      {children}
    </>
  );
}

function WorkspaceToolLoadingState({ toolName }) {
  return (
    <WorkspaceStateBlock
      eyebrow="Loading Tool"
      title={`正在载入${toolName}`}
      description="当前工具页按需加载中，准备完成后会立刻显示内容。"
      loading
    />
  );
}
