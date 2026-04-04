import { lazy, Suspense } from "react";

import { WorkspaceStateBlock } from "./shared/WorkspaceStateBlock";
import { WorkspaceToolGrid } from "./shared/WorkspaceToolGrid";
import { WorkspaceToolHeader } from "./shared/WorkspaceToolHeader";
import {
  SERIES_TOOL_TILES,
  TOOL_TILES,
  describeToolState,
  getToolMeta,
  getToolState,
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
const WorkspaceSeriesOverviewView = lazy(() =>
  import("./views/WorkspaceSeriesOverviewView").then((module) => ({
    default: module.WorkspaceSeriesOverviewView,
  })),
);
const WorkspaceSeriesProgressView = lazy(() =>
  import("./views/WorkspaceSeriesProgressView").then((module) => ({
    default: module.WorkspaceSeriesProgressView,
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
  previewSeekRequest,
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
  onSelectTool,
  onFocusNode,
  onOpenCard,
  onGenerateMindmap,
  onGenerateKnowledgeCards,
  onCreateNote,
  onUpdateNote,
  onDeleteNote,
}) {
  const isStudioHome = selectedToolId === "studio";
  const isSeriesHome = selectedToolId === "series-home";
  const currentToolMeta = getToolMeta(selectedToolId);
  const previewSource = tools?.preview.previewUrl ?? previewUrl ?? undefined;

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
            <header className="mb-5 flex shrink-0 flex-col gap-5 border-b border-stone-200/80 pb-5 dark:border-stone-800">
              {isStudioHome ? (
                <WorkspaceHomeHeader
                  eyebrow="Studio"
                  title={summary?.title ?? selectedVideo?.title}
                  description="选择一个工具进入专门页面，进入后会隐藏其他卡片。"
                >
                  <WorkspaceToolGrid
                    items={Object.entries(TOOL_TILES).map(([toolId, meta]) => ({
                      id: toolId,
                      meta,
                      disabled: getToolState(tools, toolId)?.available === false,
                      hint: describeToolState(toolId, getToolState(tools, toolId)),
                    }))}
                    onSelect={onSelectTool}
                  />
                </WorkspaceHomeHeader>
              ) : isSeriesHome ? (
                <WorkspaceHomeHeader
                  eyebrow="Series Home"
                  title={activeSeries.title}
                  description="你现在看的不是某条视频，而是整个 series。先选系列工具，再决定是否切到单视频。"
                >
                  <WorkspaceToolGrid
                    items={Object.entries(SERIES_TOOL_TILES).map(([toolId, meta]) => ({
                      id: toolId,
                      meta,
                      hint: "series 级工具",
                    }))}
                    onSelect={onSelectTool}
                  />
                </WorkspaceHomeHeader>
              ) : (
                <WorkspaceToolHeader
                  meta={currentToolMeta}
                  onBack={() => onSelectTool(selectedContextType === "series" ? "series-home" : "studio")}
                />
              )}
            </header>

            <div className="relative min-h-0 flex-1">
              {toolsLoading ? (
                <WorkspaceStateBlock
                  title="读取工具状态"
                  description="正在同步当前视频的工具状态。"
                  loading
                />
              ) : null}

              {!toolsLoading ? (
                <Suspense fallback={<WorkspaceToolLoadingState toolName={currentToolMeta.label} />}>
                  {isSeriesHome ? <WorkspaceSeriesHomeView activeSeries={activeSeries} /> : null}
                  {selectedToolId === "series-overview" ? <WorkspaceSeriesOverviewView activeSeries={activeSeries} /> : null}
                  {selectedToolId === "series-progress" ? <WorkspaceSeriesProgressView activeSeries={activeSeries} /> : null}
                  {isStudioHome ? <WorkspaceStudioHomeView /> : null}
                  {selectedToolId === "overview" ? (
                    <WorkspaceOverviewView
                      ui={ui}
                      tools={tools}
                      summary={summary}
                      selectedVideo={selectedVideo}
                      selectedChapterId={selectedChapterId}
                      summaryLoading={summaryLoading}
                      isGeneratingSelectedVideo={isGeneratingSelectedVideo}
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
                      onOpenCard={onOpenCard}
                    />
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
                    <WorkspacePreviewView previewSource={previewSource} previewSeekRequest={previewSeekRequest} />
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
