import { lazy, Suspense, useState } from "react";
import { X } from "lucide-react";
import { WorkspaceLibraryPanel } from "./WorkspaceLibraryPanel";
import { WorkspaceReadingPane } from "./WorkspaceReadingPane";
import { WorkspaceSeriesGrid } from "./WorkspaceSeriesGrid";
import { WorkspaceToolbar } from "./WorkspaceToolbar";
import { WorkspaceChatPanel } from "./WorkspaceChatPanel";
import { WorkspaceImportModal } from "./WorkspaceImportModal";
import { WorkspaceConfirmDialog } from "./shared/WorkspaceConfirmDialog";
import { motion, AnimatePresence } from "framer-motion";
import { blurVariant } from "../../../lib/animations";
import { WorkspaceStateBlock } from "./shared/WorkspaceStateBlock";

const WorkspaceLibraryHomePane = lazy(() =>
  import("./WorkspaceLibraryHomePane").then((module) => ({
    default: module.WorkspaceLibraryHomePane,
  })),
);
const WorkspaceSettingsPanel = lazy(() =>
  import("./WorkspaceSettingsPanel").then((module) => ({
    default: module.WorkspaceSettingsPanel,
  })),
);
const WorkspaceGenerationOverlay = lazy(() =>
  import("./WorkspaceGenerationOverlay").then((module) => ({
    default: module.WorkspaceGenerationOverlay,
  })),
);

export function WorkspacePage({ page }) {
  const { shell, chat, generation, actions } = page;
  const {
    state,
    ui,
    library,
    tools,
    summary,
    mindmap,
    knowledgeCards,
    knowledgeCardsGenerating,
    knowledgeCardsFeedback,
    notes,
    activeSeries,
    selectedVideo,
    selectedNode,
    previewUrl,
    previewSeekRequest,
    selectedContextType,
  } = shell;
  const [isSidebarOpen, setIsSidebarOpen] = useState(true);
  const [importModalState, setImportModalState] = useState(null);
  const [pendingDelete, setPendingDelete] = useState(null);
  const [deletePending, setDeletePending] = useState(false);
  const isPlaygroundHome = activeSeries?.id === "__playground__" && !selectedVideo;
  const currentAsrModel = generation.fasterWhisperModels?.find((model) => model.id === ui.asrModelQuality) ?? null;

  if (state.loading && !summary) {
    const waitingForBackend = !state.backendReady;
    return (
      <div className="flex h-screen w-full items-center justify-center bg-transparent">
        <div className="workspace-panel rounded-3xl p-8 border max-w-md text-center">
          <p className="text-stone-600 dark:text-zinc-400 text-sm font-bold tracking-widest uppercase mb-2">Preparing Workspace</p>
          <h1 className="text-2xl font-bold text-stone-900 mb-3">
            {waitingForBackend ? "正在启动服务..." : "正在载入知识工作台"}
          </h1>
          <p className="text-stone-500">
            {waitingForBackend
              ? "正在等待后端服务响应，连接成功后会自动进入工作区。"
              : "正在扫描 `videos/` 目录并构建当前工作区。"}
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex h-screen w-full overflow-hidden p-4 gap-4 text-stone-900 dark:text-stone-100 transition-colors">
      {/* Left Sidebar (Sources) */}
      <aside
        className={`workspace-panel shrink-0 flex flex-col rounded-[2rem] border overflow-hidden relative z-10 transition-all duration-300 ease-in-out ${isSidebarOpen ? (activeSeries ? "w-[320px] xl:w-[340px] opacity-100 mr-1" : "w-[380px] xl:w-[420px] opacity-100 mr-1") : "w-0 opacity-0 border-0 m-0"}`}
      >
        <div className={`${activeSeries ? "w-[320px] xl:w-[340px]" : "w-[380px] xl:w-[420px]"} h-full flex flex-col`}>
          {activeSeries ? (
            <WorkspaceLibraryPanel
              activeSeries={activeSeries}
              selectedContextType={selectedContextType}
              selectedVideo={selectedVideo}
              isGeneratingSelectedVideo={generation.isGeneratingSummary}
              onEnterLibraryHome={actions.enterLibraryHome}
              onSelectSeriesContext={actions.selectSeriesContext}
              onSelectVideo={actions.selectVideo}
              onGenerateVideo={actions.generateVideo}
              onDownloadVideo={actions.downloadVideo}
              onAddPlaygroundVideo={() => setImportModalState({ mode: "playground" })}
              onAddSeriesVideo={() => {
                if (!activeSeries) {
                  return;
                }
                setImportModalState({
                  mode: "series-video",
                  targetSeriesId: activeSeries.id,
                  targetSeriesTitle: activeSeries.title,
                });
              }}
              onDeleteSeries={actions.deleteSeries}
              onRequestDeleteSeries={() => {
                if (!activeSeries) {
                  return;
                }
                setPendingDelete({
                  kind: "series",
                  title: "删除整个系列？",
                  description: `将删除“${activeSeries.title}”及其所有视频与产物。该操作不可撤销。`,
                });
              }}
              onRequestDeleteCurrentVideo={() => {
                if (!selectedVideo) {
                  return;
                }
                setPendingDelete({
                  kind: "video",
                  title: "删除当前视频？",
                  description: `将删除“${selectedVideo.title}”及其相关产物。该操作不可撤销。`,
                });
              }}
              downloadProgress={generation.videoDownloadProgress}
              currentAsrModel={currentAsrModel}
            />
          ) : (
            <WorkspaceSeriesGrid
              library={library}
              onOpenSeries={actions.selectSeries}
              onAddSeries={() => setImportModalState({ mode: "series" })}
              compact
            />
          )}
        </div>
      </aside>

      {/* Main Studio Area */}
      <main className="workspace-panel flex-1 min-w-0 flex flex-col relative rounded-[2rem] border overflow-hidden z-10">
        <WorkspaceToolbar
          settingsOpen={state.settingsPanelOpen}
          activeSeries={activeSeries}
          onEnterLibraryHome={actions.enterLibraryHome}
          onToggleSettingsPanel={actions.toggleSettingsPanel}
          isSidebarOpen={isSidebarOpen}
          onToggleSidebar={() => setIsSidebarOpen(!isSidebarOpen)}
        />

        {state.error && (
          <div className="mx-6 mt-4 flex items-start justify-between gap-4 rounded-2xl border border-red-100 bg-red-50/90 p-4 text-sm text-red-800 dark:border-red-900/70 dark:bg-red-950/40 dark:text-red-200 flex-shrink-0 relative z-20">
            <div className="min-w-0 flex-1 break-words">
              {state.error}
            </div>
            {typeof actions.clearError === "function" ? (
              <button
                type="button"
                onClick={actions.clearError}
                className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-red-500 transition-colors hover:bg-red-100 hover:text-red-700 dark:text-red-300 dark:hover:bg-red-950/50 dark:hover:text-red-100"
                title="关闭错误提示"
                aria-label="关闭错误提示"
              >
                <X size={16} />
              </button>
            ) : null}
          </div>
        )}

        <div className="flex-1 min-h-0 relative flex overflow-hidden bg-transparent">
          {activeSeries && !isPlaygroundHome ? (
            <section className="flex-1 min-w-[380px] h-full overflow-hidden block border-r border-stone-200/70 dark:border-stone-800/90">
              <WorkspaceChatPanel
                workspaceTitle={library?.workspace?.title}
                activeSeries={activeSeries}
                selectedVideo={selectedVideo}
                selectedContextType={selectedContextType}
                selectedToolId={state.selectedToolId}
                tools={tools}
                chatMessages={chat.messages}
                chatSessions={chat.sessions}
                activeSessionId={chat.activeSessionId}
                chatPending={chat.pending}
                contextUsage={chat.contextUsage}
                contextUsageLoading={chat.contextUsageLoading}
                onSelectChatSession={chat.selectChatSession}
                onOpenSeekReference={chat.openSeekReference}
                onSubmitChat={chat.submit}
              />
            </section>
          ) : null}
          {isPlaygroundHome ? (
            <section className="flex-1 min-w-[380px] h-full overflow-hidden block border-r border-stone-200/70 dark:border-stone-800/90">
              <div className="flex h-full items-center justify-center p-8">
                <WorkspaceStateBlock
                  eyebrow="Playground"
                  title="选择一个视频开始分析"
                  description="Playground 不提供 series 级分析。这里的每个视频都是一次独立的单视频工作区。"
                  dashed
                />
              </div>
            </section>
          ) : null}

          {!activeSeries ? (
            <AnimatePresence mode="wait">
              <Suspense fallback={<WorkspaceSidePaneLoadingState title="正在载入工作区首页" />}>
                <WorkspaceLibraryHomePane
                  library={library}
                  onSelectSeries={actions.selectSeries}
                  onAddSeries={() => setImportModalState({ mode: "series" })}
                  onAddPlaygroundVideo={() => setImportModalState({ mode: "playground" })}
                />
              </Suspense>
            </AnimatePresence>
          ) : (
            <AnimatePresence mode="wait">
              <motion.section
                key={`${selectedContextType}:${selectedVideo?.id ?? "series"}:${state.selectedToolId}:pane`}
                variants={blurVariant}
                initial="initial" animate="animate" exit="exit"
                className="w-[45vw] xl:w-[760px] shrink-0 h-full overflow-y-auto relative z-10 border-l border-stone-200/80 dark:border-stone-800/90 transition-all"
              >
                <WorkspaceReadingPane
                  ui={ui}
                  tools={tools}
                  library={library}
                  chat={chat}
                  summary={summary}
                  mindmap={mindmap}
                  knowledgeCards={knowledgeCards}
                  knowledgeCardsGenerating={knowledgeCardsGenerating}
                  knowledgeCardsFeedback={knowledgeCardsFeedback}
                  notes={notes}
                  activeSeries={activeSeries}
                  selectedVideo={selectedVideo}
                  selectedContextType={selectedContextType}
                  selectedNode={selectedNode}
                  previewUrl={previewUrl}
                  previewSeekRequest={previewSeekRequest}
                  selectedToolId={state.selectedToolId}
                  selectedChapterId={state.selectedChapterId}
                  toolsLoading={state.toolsLoading}
                  summaryLoading={state.summaryLoading}
                  mindmapLoading={state.mindmapLoading}
                  knowledgeCardsLoading={generation.knowledgeCardsLoading}
                  notesLoading={generation.notesLoading}
                  savingNote={generation.savingNote}
                  isGeneratingMindmapSelectedVideo={generation.isGeneratingMindmap}
                  isGeneratingSelectedVideo={generation.isGeneratingSummary}
                  onSelectTool={actions.selectTool}
                  onFocusNode={actions.focusNode}
                  onOpenCard={actions.openCard}
                  onGenerateMindmap={actions.generateMindmap}
                  onGenerateKnowledgeCards={actions.generateKnowledgeCards}
                  onCreateNote={actions.createNote}
                  onUpdateNote={actions.updateNote}
                  onDeleteNote={actions.deleteNote}
                />
              </motion.section>
            </AnimatePresence>
          )}

          {/* Loading Overlay when generating AI Summary */}
          <AnimatePresence>
            {activeSeries && generation.isGeneratingSummary && (
              <Suspense fallback={null}>
                <WorkspaceGenerationOverlay
                  generationProgress={generation.progress}
                  generationSnapshot={generation.snapshot}
                />
              </Suspense>
            )}
          </AnimatePresence>
        </div>

        {/* Settings Overlay */}
        <AnimatePresence>
          {state.settingsPanelOpen && (
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.2 }}
              className="absolute inset-0 z-50 bg-stone-900/20 dark:bg-black/50 backdrop-blur-md flex justify-center items-center p-4 md:p-8"
            >
              <Suspense fallback={<WorkspaceModalLoadingState />}>
                <WorkspaceSettingsPanel
                  ui={ui}
                  fasterWhisperModels={generation.fasterWhisperModels}
                  fasterWhisperModelsLoading={generation.fasterWhisperModelsLoading}
                  downloadingModelId={generation.downloadingModelId}
                  modelDownloadProgress={generation.modelDownloadProgress}
                  onChangeSetting={actions.changeSetting}
                  onSaveApiKey={actions.saveApiKey}
                  onDownloadFasterWhisperModel={actions.downloadFasterWhisperModel}
                  onCancelFasterWhisperModelDownload={actions.cancelFasterWhisperModelDownload}
                  onResetSettings={actions.resetSettings}
                  onClose={actions.closeSettingsPanel}
                />
              </Suspense>
            </motion.div>
          )}
        </AnimatePresence>
      </main>

      {importModalState && (
        <WorkspaceImportModal
          mode={importModalState.mode}
          targetSeriesId={importModalState.targetSeriesId ?? null}
          targetSeriesTitle={importModalState.targetSeriesTitle ?? ""}
          onClose={() => setImportModalState(null)}
          onResolveSeries={async (url) => actions.resolveLinkedSeries(url)}
          onResolveVideo={async (url, targetSeriesId) => (
            targetSeriesId
              ? actions.resolveSeriesVideo(url, targetSeriesId)
              : actions.resolvePlaygroundVideo(url)
          )}
          onImportLocalSeries={async (seriesTitle, files) => actions.importLocalSeries(seriesTitle, files)}
          onImportSeriesVideos={async (seriesId, files) => actions.importSeriesVideos(seriesId, files)}
          onImportLocalPlaygroundVideos={async (files) => actions.importLocalPlaygroundVideos(files)}
        />
      )}

      <WorkspaceConfirmDialog
        open={pendingDelete != null}
        title={pendingDelete?.title ?? ""}
        description={pendingDelete?.description ?? ""}
        confirmLabel="确认删除"
        destructive
        pending={deletePending}
        onCancel={() => {
          if (!deletePending) {
            setPendingDelete(null);
          }
        }}
        onConfirm={async () => {
          if (!pendingDelete || deletePending) {
            return;
          }
          setDeletePending(true);
          try {
            if (pendingDelete.kind === "series") {
              await actions.deleteSeries?.();
            } else if (pendingDelete.kind === "video") {
              await actions.deleteCurrentVideo?.();
            }
            setPendingDelete(null);
          } finally {
            setDeletePending(false);
          }
        }}
      />
    </div>
  );
}

function WorkspaceSidePaneLoadingState({ title }) {
  return (
    <section className="w-[45vw] xl:w-[760px] shrink-0 h-full overflow-y-auto relative z-10 border-l border-stone-200/80 dark:border-stone-800/90 transition-all">
      <div className="flex h-full p-8">
        <WorkspaceStateBlock title={title} description="界面资源按需加载中。" loading />
      </div>
    </section>
  );
}

function WorkspaceModalLoadingState() {
  return (
    <div className="workspace-panel flex w-full max-w-xl items-center justify-center rounded-[2rem] border p-10">
      <WorkspaceStateBlock
        title="正在载入设置面板"
        description="设置页首次打开时会按需加载。"
        loading
      />
    </div>
  );
}
