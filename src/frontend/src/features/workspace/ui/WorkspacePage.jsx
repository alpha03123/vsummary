import { lazy, Suspense, useState } from "react";
import { WorkspaceLibraryPanel } from "./WorkspaceLibraryPanel";
import { WorkspaceReadingPane } from "./WorkspaceReadingPane";
import { WorkspaceSeriesGrid } from "./WorkspaceSeriesGrid";
import { WorkspaceToolbar } from "./WorkspaceToolbar";
import { WorkspaceChatPanel } from "./WorkspaceChatPanel";
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

  if (state.loading && !summary) {
    return (
      <div className="flex h-screen w-full items-center justify-center bg-transparent">
        <div className="workspace-panel rounded-3xl p-8 border max-w-md text-center">
          <p className="text-stone-600 dark:text-zinc-400 text-sm font-bold tracking-widest uppercase mb-2">Preparing Workspace</p>
          <h1 className="text-2xl font-bold text-stone-900 mb-3">正在载入知识工作台</h1>
          <p className="text-stone-500">正在扫描 `videos/` 目录并构建当前工作区。</p>
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
            />
          ) : (
            <WorkspaceSeriesGrid library={library} onOpenSeries={actions.selectSeries} compact />
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
          <div className="mx-6 mt-4 p-4 rounded-2xl bg-red-50/90 dark:bg-red-950/40 text-red-800 dark:text-red-200 border border-red-100 dark:border-red-900/70 text-sm flex-shrink-0 relative z-20">
            {state.error}
          </div>
        )}

        <div className="flex-1 min-h-0 relative flex overflow-hidden bg-transparent">
          <section className="flex-1 min-w-[380px] h-full overflow-hidden block border-r border-stone-200/70 dark:border-stone-800/90">
             <WorkspaceChatPanel
               workspaceTitle={library?.workspace?.title}
               activeSeries={activeSeries}
               selectedVideo={selectedVideo}
               selectedContextType={selectedContextType}
               selectedToolId={state.selectedToolId}
               tools={tools}
               chatMessages={chat.messages}
               chatPending={chat.pending}
               onSubmitChat={chat.submit}
             />
          </section>

          {!activeSeries ? (
            <AnimatePresence mode="wait">
              <Suspense fallback={<WorkspaceSidePaneLoadingState title="正在载入工作区首页" />}>
                <WorkspaceLibraryHomePane library={library} onSelectSeries={actions.selectSeries} />
              </Suspense>
            </AnimatePresence>
          ) : (
            <AnimatePresence mode="wait">
                <motion.section 
                  key={`${selectedContextType}:${selectedVideo?.id ?? "series"}:${state.selectedToolId}:pane`} 
                  variants={blurVariant}
                  initial="initial" animate="animate" exit="exit"
                  className="w-[45vw] xl:w-[760px] shrink-0 h-full overflow-hidden relative z-10 border-l border-stone-200/80 dark:border-stone-800/90 transition-all"
                >
                  <WorkspaceReadingPane
                    ui={ui}
                    tools={tools}
                    library={library}
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
    </div>
  );
}

function WorkspaceSidePaneLoadingState({ title }) {
  return (
    <section className="w-[45vw] xl:w-[760px] shrink-0 h-full overflow-hidden relative z-10 border-l border-stone-200/80 dark:border-stone-800/90 transition-all">
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
