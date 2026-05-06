import { lazy, Suspense, useEffect, useRef, useState } from "react";
import { CheckCircle2, Database, LoaderCircle, X } from "lucide-react";
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
import {
  clampMiddleWidth,
  clampSidebarWidth,
  loadWorkspaceLayout,
  persistWorkspaceLayout,
} from "./workspaceLayout";

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
  const [layout, setLayout] = useState(loadWorkspaceLayout);
  const [importModalState, setImportModalState] = useState(null);
  const [pendingDelete, setPendingDelete] = useState(null);
  const [deletePending, setDeletePending] = useState(false);
  const containerRef = useRef(null);
  const isPlaygroundHome = activeSeries?.id === "__playground__" && !selectedVideo;
  const currentAsrModel = generation.fasterWhisperModels?.find((model) => model.id === ui.asrModelQuality) ?? null;
  const hasRightPane = Boolean(activeSeries);

  useEffect(() => {
    persistWorkspaceLayout(layout);
  }, [layout]);

  function beginResize(type, startEvent) {
    const container = containerRef.current;
    if (!container) {
      return;
    }

    const startX = startEvent.clientX;
    const startSidebarWidth = layout.sidebarWidth;
    const startMiddleWidth = layout.middleWidth;
    const containerWidth = container.getBoundingClientRect().width;

    function handlePointerMove(event) {
      const deltaX = event.clientX - startX;
      if (type === "sidebar") {
        setLayout((current) => ({
          ...current,
          sidebarWidth: clampSidebarWidth({
            proposedWidth: startSidebarWidth + deltaX,
            containerWidth,
            hasRightPane,
          }),
        }));
        return;
      }

      setLayout((current) => ({
        ...current,
        middleWidth: clampMiddleWidth({
          proposedWidth: startMiddleWidth + deltaX,
          containerWidth,
          sidebarWidth: isSidebarOpen ? current.sidebarWidth : 0,
        }),
      }));
    }

    function handlePointerUp() {
      window.removeEventListener("pointermove", handlePointerMove);
      window.removeEventListener("pointerup", handlePointerUp);
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
    }

    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";
    window.addEventListener("pointermove", handlePointerMove);
    window.addEventListener("pointerup", handlePointerUp, { once: true });
  }

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
    <div ref={containerRef} className="flex h-screen w-full overflow-hidden p-4 gap-4 text-stone-900 dark:text-stone-100 transition-colors">
      {/* Left Sidebar (Sources) */}
      <aside
        style={
          isSidebarOpen
            ? { width: `${layout.sidebarWidth}px` }
            : undefined
        }
        className={`workspace-panel shrink-0 flex flex-col rounded-[2rem] border overflow-hidden relative z-10 transition-all duration-300 ease-in-out ${isSidebarOpen ? "opacity-100 mr-1" : "w-0 opacity-0 border-0 m-0"}`}
      >
        <div className="h-full flex flex-col">
          {activeSeries ? (
            <WorkspaceLibraryPanel
              activeSeries={activeSeries}
              selectedContextType={selectedContextType}
              selectedVideo={selectedVideo}
              isGeneratingSelectedVideo={generation.isGeneratingSummary}
              isGeneratingSeries={generation.isGeneratingSeries}
              onEnterLibraryHome={actions.enterLibraryHome}
              onSelectSeriesContext={actions.selectSeriesContext}
              onSelectVideo={actions.selectVideo}
              onGenerateVideo={actions.generateVideo}
              onGenerateSeries={actions.generateSeries}
              onCancelGeneration={actions.cancelGeneration}
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
              ragModels={generation.ragModels}
              onOpenSettings={() => actions.openSettingsPanel("network")}
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
      {isSidebarOpen ? (
        <div
          role="separator"
          aria-orientation="vertical"
          aria-label="调整来源列表宽度"
          onPointerDown={(event) => beginResize("sidebar", event)}
          className="group relative hidden w-2 shrink-0 cursor-col-resize rounded-full md:block"
        >
          <div className="absolute inset-y-0 left-1/2 w-px -translate-x-1/2 bg-stone-200 transition-colors group-hover:bg-accent dark:bg-stone-800 dark:group-hover:bg-accent" />
        </div>
      ) : null}

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

        <WorkspaceKnowledgeMemoryStatusBar snapshot={state.knowledgeMemorySnapshot} />

        <div className="flex-1 min-h-0 relative flex overflow-hidden bg-transparent">
          {activeSeries && !isPlaygroundHome ? (
            <section
              style={hasRightPane ? { width: `clamp(320px, ${layout.middleWidth}px, 52%)` } : undefined}
              className="shrink-0 min-w-[320px] h-full overflow-hidden block border-r border-stone-200/70 dark:border-stone-800/90"
            >
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
                ragModels={generation.ragModels}
                onSelectChatSession={chat.selectChatSession}
                onOpenSeekReference={chat.openSeekReference}
                onOpenSettings={() => actions.openSettingsPanel("network")}
                onSubmitChat={chat.submit}
              />
            </section>
          ) : null}
          {isPlaygroundHome ? (
            <section className="flex-1 min-w-[320px] h-full overflow-hidden block border-r border-stone-200/70 dark:border-stone-800/90">
              <div className="flex h-full items-center justify-center p-8">
                <WorkspaceStateBlock
                  eyebrow="Playground"
                  title="选择一个视频开始分析"
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
            <>
              <div
                role="separator"
                aria-orientation="vertical"
                aria-label="调整对话与工具页宽度"
                onPointerDown={(event) => beginResize("middle", event)}
                className="group relative hidden w-2 shrink-0 cursor-col-resize md:block"
              >
                <div className="absolute inset-y-0 left-1/2 w-px -translate-x-1/2 bg-stone-200 transition-colors group-hover:bg-accent dark:bg-stone-800 dark:group-hover:bg-accent" />
              </div>
              <motion.section
                key={`${selectedContextType}:${selectedVideo?.id ?? "series"}:${state.selectedToolId}:pane`}
                variants={blurVariant}
                initial="initial" animate="animate" exit="exit"
                className="min-w-[320px] flex-1 h-full overflow-y-auto relative z-10 border-l border-stone-200/80 dark:border-stone-800/90 transition-all"
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
                  onGenerateMindmap={actions.generateMindmap}
                  onGenerateKnowledgeCards={actions.generateKnowledgeCards}
                  onCreateNote={actions.createNote}
                  onUpdateNote={actions.updateNote}
                  onDeleteNote={actions.deleteNote}
                />
              </motion.section>
            </>
          )}

          {/* Loading Overlay when generating AI Summary */}
          <AnimatePresence>
            {activeSeries && generation.showOverlay && generation.snapshot && (
              <Suspense fallback={null}>
                <WorkspaceGenerationOverlay
                  generationProgress={generation.progress}
                  generationSnapshot={generation.snapshot}
                  title={generation.isGeneratingSeries ? "正在处理整个系列" : "正在生成 AI 概况"}
                  onCancel={actions.cancelGeneration}
                  cancelLabel={generation.isGeneratingSeries ? "取消整个系列" : "取消本次生成"}
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
                  initialTab={state.settingsPanelInitialTab}
                  fasterWhisperModels={generation.fasterWhisperModels}
                  fasterWhisperModelsLoading={generation.fasterWhisperModelsLoading}
                  ragModels={generation.ragModels}
                  ragModelsLoading={generation.ragModelsLoading}
                  downloadingRagModelKey={generation.downloadingRagModelKey}
                  downloadingModelId={generation.downloadingModelId}
                  modelDownloadStatus={generation.modelDownloadStatus}
                  modelDownloadProgress={generation.modelDownloadProgress}
                  onChangeSetting={actions.changeSetting}
                  onSaveApiKey={actions.saveApiKey}
                  onTestProviderConnection={actions.testProviderConnection}
                  onDownloadFasterWhisperModel={actions.downloadFasterWhisperModel}
                  onCancelFasterWhisperModelDownload={actions.cancelFasterWhisperModelDownload}
                  onDownloadRagModel={actions.downloadRagModel}
                  onCancelRagModelDownload={actions.cancelRagModelDownload}
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

function WorkspaceKnowledgeMemoryStatusBar({ snapshot }) {
  if (!snapshot || snapshot.status === "idle") {
    return null;
  }
  if (
    snapshot.status === "completed" &&
    typeof snapshot.updatedAt === "number" &&
    Date.now() / 1000 - snapshot.updatedAt > 10
  ) {
    return null;
  }
  if (snapshot.status !== "running" && snapshot.status !== "completed" && snapshot.status !== "failed") {
    return null;
  }

  const isRunning = snapshot.status === "running";
  const isFailed = snapshot.status === "failed";
  const Icon = isRunning ? LoaderCircle : isFailed ? Database : CheckCircle2;
  const title = isRunning ? "长期记忆整理中" : isFailed ? "长期记忆整理失败" : "长期记忆已整理";
  const detail = isFailed
    ? snapshot.error ?? "请查看后端日志。"
    : snapshot.detail ?? (isRunning ? "正在重建 RAG 索引与 catalog 记忆。" : "RAG 索引已可用于检索。");
  const progressText = typeof snapshot.progress === "number" ? `${Math.round(snapshot.progress)}%` : "";
  const toneClassName = isFailed
    ? "border-red-100 bg-red-50/90 text-red-800 dark:border-red-900/70 dark:bg-red-950/40 dark:text-red-200"
    : "border-amber-100 bg-amber-50/90 text-amber-900 dark:border-amber-900/60 dark:bg-amber-950/30 dark:text-amber-100";

  return (
    <div className={`mx-6 mt-4 flex items-center gap-3 rounded-2xl border px-4 py-3 text-sm ${toneClassName}`}>
      <span className="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-white/70 dark:bg-black/20">
        <Icon size={18} className={isRunning ? "animate-spin" : ""} />
      </span>
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2 font-semibold">
          <span>{title}</span>
          {progressText ? <span className="text-xs opacity-70">{progressText}</span> : null}
        </div>
        <p className="mt-0.5 truncate text-xs opacity-80">{detail}</p>
      </div>
    </div>
  );
}

function WorkspaceSidePaneLoadingState({ title }) {
  return (
    <section className="w-[clamp(320px,38vw,720px)] shrink-0 h-full overflow-y-auto relative z-10 border-l border-stone-200/80 dark:border-stone-800/90 transition-all">
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
