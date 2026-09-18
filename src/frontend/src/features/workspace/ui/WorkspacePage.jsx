import { lazy, Suspense, useEffect, useRef, useState } from "react";
import { CheckCircle2, Database, LoaderCircle, X } from "lucide-react";
import { WorkspaceLibraryPanel } from "./WorkspaceLibraryPanel";
import { WorkspaceVideoScopePane } from "./WorkspaceVideoScopePane";
import { WorkspaceSeriesGrid } from "./WorkspaceSeriesGrid";
import { WorkspaceToolbar } from "./WorkspaceToolbar";
import { WorkspaceVideoPlayer } from "./WorkspaceVideoPlayer";
import { WorkspaceChatPanel } from "./WorkspaceChatPanel";
import { WorkspaceStudioPanels } from "./WorkspaceStudioPanels";
import { ChatDrawer } from "./ChatDrawer";
import { WorkspaceImportModal } from "./WorkspaceImportModal";
import { WorkspaceConfirmDialog } from "./shared/WorkspaceConfirmDialog";
import { WorkspaceRenameDialog } from "./shared/WorkspaceRenameDialog";
import { motion, AnimatePresence } from "framer-motion";
import { useFocusTrap } from "../../../shared/lib/useFocusTrap";
import { WorkspaceStateBlock } from "./shared/WorkspaceStateBlock";
import { WorkspaceBackButton } from "./shared/WorkspaceBackButton";
import { WorkspaceExportMenu } from "./shared/WorkspaceToolHeader";
import { clampChatDrawerWidth, clampPanelWidth, clampSidebarWidth, createPanelId, getPanelType, isPanelAllowedForScope, loadWorkspaceLayout, persistWorkspaceLayout, STUDIO_PANEL_TYPES, WORKSPACE_LAYOUT_LIMITS } from "./workspaceLayout";
import { buildWorkspaceToolExportActions } from "./workspaceToolExports";

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
const WorkspaceUsagePage = lazy(() =>
  import("./WorkspaceUsagePage").then((module) => ({
    default: module.WorkspaceUsagePage,
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
    seriesMindmap,
    seriesMindmapAvailable,
    seriesOverviewSummariesByVideoId,
    knowledgeCards,
    knowledgeCardsGenerating,
    knowledgeCardsFeedback,
    notes,
    activeSeries,
    selectedVideo,
    selectedNode,
    previewUrl,
    playerSeekRequest,
    citationFocus,
    selectedContextType,
  } = shell;
  const [isSidebarOpen, setIsSidebarOpen] = useState(true);
  const studioScope = selectedContextType === "series" ? "series" : "video";
  const [layoutsByScope, setLayoutsByScope] = useState(() => ({
    video: loadWorkspaceLayout("video"),
    series: loadWorkspaceLayout("series"),
  }));
  const layout = layoutsByScope[studioScope];
  const setLayout = (updater) => setLayoutsByScope((current) => ({
    ...current,
    [studioScope]: typeof updater === "function" ? updater(current[studioScope]) : updater,
  }));
  const [focusedPanel, setFocusedPanel] = useState("overview");
  const [importModalState, setImportModalState] = useState(null);
  const [pendingDelete, setPendingDelete] = useState(null);
  const [deletePending, setDeletePending] = useState(false);
  const [pendingRename, setPendingRename] = useState(null);
  const [renamePending, setRenamePending] = useState(false);
  const [playbackTime, setPlaybackTime] = useState(null);
  const [followOverviewPlayback, setFollowOverviewPlayback] = useState(false);
  const [chatDraft, setChatDraft] = useState("");
  const [resumePosition, setResumePosition] = useState({ videoKey: null, seconds: null });
  const playbackPositionsRef = useRef(new Map());
  const containerRef = useRef(null);
  const settingsModalRef = useRef(null);
  const usageModalRef = useRef(null);
  // Engage focus trap on open modals so keyboard users stay inside
  // (WCAG 2.4.3 Focus Order) and focus returns to the trigger on close.
  useFocusTrap(settingsModalRef, state.settingsPanelOpen);
  useFocusTrap(usageModalRef, state.usagePageOpen);
  const isPlaygroundHome = activeSeries?.id === "__playground__" && !selectedVideo;
  const hasRightPane = Boolean(activeSeries);
  const currentAsrModel = generation.fasterWhisperModels?.find((model) => model.id === ui.asrModelQuality) ?? null;
  const summaryLocked = selectedContextType === "series"
    ? !(activeSeries?.videos ?? []).some((video) => video.processed)
    : selectedContextType === "video" && selectedVideo?.processed !== true;
  const chatPanelProps = {
    workspaceTitle: library?.workspace?.title,
    activeSeries,
    selectedVideo,
    selectedContextType,
    tools,
    chatMessages: chat.messages,
    chatSessions: chat.sessions,
    activeSessionId: chat.activeSessionId,
    chatPending: chat.pending,
    summaryLocked,
    contextUsage: chat.contextUsage,
    contextUsageLoading: chat.contextUsageLoading,
    ragModels: generation.ragModels,
    knowledgeMemorySnapshot: state.knowledgeMemorySnapshot,
    draft: chatDraft,
    onDraftChange: (nextDraft) => {
      setChatDraft(nextDraft);
    },
    onSelectChatSession: chat.selectChatSession,
    onStartNewChat: chat.startNewChat,
    onOpenSeekReference: chat.openSeekReference,
    onOpenCitationReference: chat.openCitationReference,
    onOpenSettings: () => actions.openSettingsPanel("network"),
    onSubmitChat: chat.submit,
    onCancelChat: chat.cancel,
  };

  useEffect(() => {
    persistWorkspaceLayout(layoutsByScope.video, "video");
    persistWorkspaceLayout(layoutsByScope.series, "series");
  }, [layoutsByScope]);

  const selectedVideoKey = activeSeries && selectedVideo
    ? `${activeSeries.id}/${selectedVideo.id}`
    : null;

  useEffect(() => {
    setPlaybackTime(null);
    setFollowOverviewPlayback(false);
    setResumePosition({
      videoKey: selectedVideoKey,
      seconds: selectedVideoKey ? playbackPositionsRef.current.get(selectedVideoKey) ?? null : null,
    });
  }, [selectedVideoKey]);

  function beginResize(type, startEvent) {
    startEvent.preventDefault();
    startEvent.stopPropagation();

    const container = containerRef.current;
    if (!container) {
      return;
    }

    const startX = startEvent.clientX;
    const startSidebarWidth = layout.sidebarWidth;
    const panelId = type === "sidebar" ? null : type;
    const panelIndex = panelId ? layout.studioPanels.indexOf(panelId) : -1;
    const rightPanelId = panelIndex >= 0 ? layout.studioPanels[panelIndex + 1] : null;
    const startPanelWidth = panelId ? (layout.panelWidths[panelId] ?? WORKSPACE_LAYOUT_LIMITS.panelDefaultWidth) : null;
    const startRightPanelWidth = rightPanelId ? (layout.panelWidths[rightPanelId] ?? WORKSPACE_LAYOUT_LIMITS.panelDefaultWidth) : null;
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

      const maxLeftWidth = rightPanelId
        ? startPanelWidth + startRightPanelWidth - WORKSPACE_LAYOUT_LIMITS.panelMinWidth
        : clampPanelWidth({
            proposedWidth: Number.MAX_SAFE_INTEGER,
            containerWidth,
            panelCount: layout.studioPanels.length,
            sidebarWidth: isSidebarOpen ? layout.sidebarWidth : 0,
          });
      const nextLeftWidth = Math.min(
        Math.max(WORKSPACE_LAYOUT_LIMITS.panelMinWidth, startPanelWidth + deltaX),
        maxLeftWidth,
      );
      const appliedDelta = nextLeftWidth - startPanelWidth;
      const nextRightWidth = rightPanelId
        ? Math.max(WORKSPACE_LAYOUT_LIMITS.panelMinWidth, startRightPanelWidth - appliedDelta)
        : null;
      setLayout((current) => ({
        ...current,
        panelWidths: {
          ...current.panelWidths,
          [panelId]: nextLeftWidth,
          ...(rightPanelId ? { [rightPanelId]: nextRightWidth } : {}),
        },
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

  function openStudioPanel(toolId) {
    if (!STUDIO_PANEL_TYPES.has(toolId) || !isPanelAllowedForScope(toolId, studioScope)) {
      return;
    }
    const existingPanel = layout.studioPanels.find((panelId) => (
      (layout.panelTools[panelId] ?? getPanelType(panelId)) === toolId
    ));
    if (existingPanel) {
      setFocusedPanel(existingPanel);
      return;
    }
    if (layout.studioPanels.length >= WORKSPACE_LAYOUT_LIMITS.maxPanels) {
      return;
    }
    const panelId = createPanelId(toolId);
    setLayout((current) => ({
      ...current,
      studioPanels: [...current.studioPanels, panelId],
      panelTools: { ...current.panelTools, [panelId]: toolId },
    }));
    setFocusedPanel(panelId);
  }

  function addStudioPanel() {
    if (layout.studioPanels.length >= WORKSPACE_LAYOUT_LIMITS.maxPanels) return;
    const panelId = createPanelId("studio");
    setLayout((current) => ({
      ...current,
      studioPanels: [...current.studioPanels, panelId],
      panelTools: { ...current.panelTools, [panelId]: "studio" },
    }));
    setFocusedPanel(panelId);
  }

  function setPanelTool(panelId, toolId) {
    if (!STUDIO_PANEL_TYPES.has(toolId) || !isPanelAllowedForScope(toolId, studioScope)) return;
    setLayout((current) => ({
      ...current,
      panelTools: { ...current.panelTools, [panelId]: toolId },
    }));
    setFocusedPanel(panelId);
  }

  function closeStudioPanel(panelId) {
    setLayout((current) => {
      const panelTools = { ...current.panelTools };
      const panelWidths = { ...current.panelWidths };
      delete panelTools[panelId];
      delete panelWidths[panelId];
      return { ...current, studioPanels: current.studioPanels.filter((item) => item !== panelId), panelTools, panelWidths };
    });
    setFocusedPanel((current) => current === panelId ? null : current);
  }

  function reorderStudioPanels(sourcePanelId, targetPanelId) {
    setLayout((current) => {
      const sourceIndex = current.studioPanels.indexOf(sourcePanelId);
      const targetIndex = current.studioPanels.indexOf(targetPanelId);
      if (sourceIndex < 0 || targetIndex < 0 || sourceIndex === targetIndex) {
        return current;
      }
      const studioPanels = [...current.studioPanels];
      studioPanels.splice(sourceIndex, 1);
      studioPanels.splice(targetIndex, 0, sourcePanelId);
      return { ...current, studioPanels };
    });
    setFocusedPanel(sourcePanelId);
  }

  function updateChatDrawerWidth(proposedWidth) {
    setLayout((current) => ({
      ...current,
      chatDrawerWidth: clampChatDrawerWidth({ proposedWidth, viewportWidth: window.innerWidth }),
    }));
  }

  function renderVideoPlayerPane(onOpenOverviewAtTime = null) {
    if (selectedVideo) {
      if (selectedVideo.status === "source_missing") {
        return (
          <div className="flex h-full items-center justify-center p-8">
            <WorkspaceStateBlock
              eyebrow="Media Preview"
              title="媒体链接已丢失"
              description="请在左侧点击“链接媒体”，文件选择框会打开原始文件所在目录。"
              dashed
            />
          </div>
        );
      }
      return (
        // 与右栏 WorkspaceReadingPane 的 p-6 保持一致，否则媒体卡贴着面板边缘、
        // 而右侧内容缩进 24px，同一行两栏看起来没有对齐。
        <div className="flex h-full flex-col overflow-y-auto p-6">
          <WorkspaceVideoPlayer
            videoSource={tools?.preview?.previewUrl ?? previewUrl}
            subtitleSource={tools?.preview?.subtitleUrl ?? null}
            playerSeekRequest={playerSeekRequest}
            videoSourceType={selectedVideo?.sourceType}
            resumeSeconds={resumePosition.videoKey === selectedVideoKey ? resumePosition.seconds : null}
            onTimeUpdate={(seconds) => {
              setPlaybackTime(seconds);
              if (selectedVideoKey && Number.isFinite(seconds) && seconds > 0) {
                playbackPositionsRef.current.set(selectedVideoKey, seconds);
              }
            }}
            onPlaybackEnded={() => {
              if (selectedVideoKey) {
                playbackPositionsRef.current.delete(selectedVideoKey);
              }
            }}
            onOpenOverviewAtTime={tools?.overview?.generated === true ? onOpenOverviewAtTime : undefined}
            followOverviewPlayback={followOverviewPlayback}
            onFollowOverviewPlaybackChange={setFollowOverviewPlayback}
          />
        </div>
      );
    }
    return (
      <div className="flex h-full items-center justify-center p-8">
        <WorkspaceStateBlock
          eyebrow="Player"
          title="选择视频以开始预览"
          description="选中左侧的视频后,这里会显示可跳转的视频播放器。"
          dashed
        />
      </div>
    );
  }

  function renderStudioPanel(panelId, fallbackToolId) {
    const toolId = layout.panelTools[panelId] ?? fallbackToolId;
    if (toolId === "preview") {
      return renderVideoPlayerPane(
        (seconds) => {
          actions.openOverviewAtTime(seconds);
          setPanelTool(panelId, "overview");
        },
      );
    }
    if (toolId === "ai-chat") {
      return <WorkspaceChatPanel {...chatPanelProps} />;
    }
    if (toolId === "series-overview" || toolId === "series-mindmap") {
      return <WorkspaceVideoScopePane page={page} panelToolId={toolId} onPanelSelectTool={(nextTool) => setPanelTool(panelId, nextTool)} embeddedInStudioPanel />;
    }
    return <WorkspaceVideoScopePane page={page} panelToolId={toolId} onPanelSelectTool={(nextTool) => setPanelTool(panelId, nextTool)} embeddedInStudioPanel playbackTime={playbackTime} followOverviewPlayback={followOverviewPlayback} onFollowOverviewPlaybackChange={setFollowOverviewPlayback} />;
  }

  function renderPanelActions(panelId, toolId) {
    if (toolId === "studio" || toolId === "preview" || toolId === "ai-chat") {
      return null;
    }
    const exportActions = buildWorkspaceToolExportActions({
      activeSeries,
      notes,
      summary,
      toolId,
      selectedVideo,
      tools,
    });
    return exportActions.length ? <WorkspaceExportMenu exportActions={exportActions} /> : null;
  }

  function renderPanelLeadingActions(panelId, toolId) {
    if (toolId === "studio") {
      return null;
    }
    return <WorkspaceBackButton onClick={() => setPanelTool(panelId, "studio")} variant="panel" />;
  }

  if (state.loading && !summary) {
    const waitingForBackend = !state.backendReady;
    return (
      <div className="flex h-screen w-full items-center justify-center bg-transparent">
        <div className="workspace-panel max-w-md rounded-3xl border p-8 text-center">
          <p className="mb-2 text-sm font-bold uppercase tracking-widest text-stone-600 dark:text-zinc-400">Preparing Workspace</p>
          <h1 className="mb-3 text-2xl font-bold text-stone-900">
            {waitingForBackend ? "正在启动服务..." : "正在载入知识工作台"}
          </h1>
          <p className="text-stone-600">
            {waitingForBackend
              ? "正在等待后端服务响应，请稍等...."
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
              seriesGenerationQueue={generation.seriesGenerationQueue}
              downloadingVideoKey={generation.downloadingVideoKey}
              onEnterLibraryHome={actions.enterLibraryHome}
              onSelectSeriesContext={actions.selectSeriesContext}
              onSelectVideo={actions.selectVideo}
              onGenerateVideo={actions.generateVideo}
              onProcessLinkedVideo={actions.processLinkedVideo}
              processingMode={shell.processingMode}
              onChangeProcessingMode={actions.changeProcessingMode}
              onRelinkVideo={actions.relinkVideo}
              onGenerateSeries={actions.generateSeries}
              onCancelGeneration={actions.cancelGeneration}
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
              onRequestRenameSeries={() => {
                if (activeSeries) {
                  setPendingRename({ kind: "series", title: activeSeries.title, entityLabel: "系列名称" });
                }
              }}
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
              onRequestBulkDelete={(videoIds) => {
                const targets = Array.isArray(videoIds) ? [...new Set(videoIds)] : [];
                if (targets.length === 0) {
                  return;
                }
                setPendingDelete({
                  kind: "videos",
                  videoIds: targets,
                  title: `删除 ${targets.length} 个视频？`,
                  description: "将删除所选视频及其相关产物。该操作不可撤销。",
                });
              }}
              onRequestRenameCurrentVideo={() => {
                if (selectedVideo) {
                  setPendingRename({ kind: "video", title: selectedVideo.title, entityLabel: "视频名称" });
                }
              }}
              downloadProgress={generation.videoDownloadProgress}
              downloadError={generation.videoDownloadError}
              downloadErrorKey={generation.videoDownloadErrorKey}
              currentAsrModel={currentAsrModel}
              ragModels={generation.ragModels}
              onOpenSettings={() => actions.openSettingsPanel("ai")}
            />
          ) : (
            <WorkspaceSeriesGrid
              library={library}
              onOpenSeries={actions.selectSeries}
              onAddSeries={() => setImportModalState({ mode: "series" })}
              onRequestBulkDelete={(seriesIds) => {
                if (seriesIds.length === 0) {
                  return;
                }
                setPendingDelete({
                  kind: "series-batch",
                  seriesIds,
                  title: `删除 ${seriesIds.length} 个系列？`,
                  description: "将删除所选系列、其中的全部视频及产物。该操作不可撤销。",
                });
              }}
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
          className="group relative z-30 -mx-1 hidden w-5 shrink-0 cursor-col-resize touch-none md:block"
        >
          <div className="absolute inset-y-0 left-1/2 w-1 -translate-x-1/2 rounded-full bg-stone-200/80 transition-colors group-hover:bg-accent dark:bg-stone-800 dark:group-hover:bg-accent" />
        </div>
      ) : null}

      {/* Main Studio Area */}
      <main className="workspace-panel flex-1 min-w-0 flex flex-col relative rounded-[2rem] border overflow-hidden z-10">
        <WorkspaceToolbar
          settingsOpen={state.settingsPanelOpen}
          activeSeries={activeSeries}
          onEnterLibraryHome={actions.enterLibraryHome}
          onToggleSettingsPanel={actions.toggleSettingsPanel}
          onOpenUsagePage={actions.openUsagePage}
          onOpenUpdate={() => actions.openSettingsPanel("update")}
          isSidebarOpen={isSidebarOpen}
          onToggleSidebar={() => setIsSidebarOpen(!isSidebarOpen)}
          onToggleChatDrawer={chat.toggleDrawer}
          chatDrawerOpen={chat.drawerOpen}
          studioPanels={layout.studioPanels}
          onAddStudioPanel={addStudioPanel}
        />

        {state.error && (
          <div className="mx-6 mt-4 flex items-start justify-between gap-4 rounded-2xl border border-danger bg-danger-subtle p-4 text-sm text-danger flex-shrink-0 relative z-20">
            <div className="min-w-0 flex-1 break-words">
              {state.error}
            </div>
            {typeof actions.clearError === "function" ? (
              <button
                type="button"
                onClick={actions.clearError}
                className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-danger-muted transition-colors hover:bg-danger-subtle hover:text-danger"
                title="关闭错误提示"
                aria-label="关闭错误提示"
              >
                <X size={16} />
              </button>
            ) : null}
          </div>
        )}

        <WorkspaceKnowledgeMemoryStatusBar snapshot={state.knowledgeMemorySnapshot} />

        <div className="flex-1 min-h-0 relative overflow-hidden bg-transparent">
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
          ) : isPlaygroundHome ? (
            <div className="flex h-full items-center justify-center p-8"><WorkspaceStateBlock eyebrow="Playground" title="选择一个视频开始分析" dashed /></div>
          ) : (
            <WorkspaceStudioPanels
              panels={layout.studioPanels}
              panelWidths={layout.panelWidths}
              panelTools={layout.panelTools}
              focusedPanel={focusedPanel}
              onFocus={setFocusedPanel}
              onAdd={openStudioPanel}
              onClose={closeStudioPanel}
              onResizeStart={beginResize}
              onReorder={reorderStudioPanels}
              renderPanel={renderStudioPanel}
              renderPanelActions={renderPanelActions}
              renderPanelLeadingActions={renderPanelLeadingActions}
            />
          )}

          {/* Loading Overlay when generating AI Summary */}
          <AnimatePresence>
            {activeSeries && generation.showOverlay && generation.snapshot && (
              <Suspense fallback={null}>
                <WorkspaceGenerationOverlay
                  generationProgress={generation.progress}
                  generationSnapshot={generation.snapshot}
                  title={shell.processingMode === "transcript" ? "正在获取字幕" : generation.isGeneratingSeries ? "正在处理整个系列" : "正在生成 AI 概况"}
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
              ref={settingsModalRef}
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.2 }}
              onKeyDown={(event) => {
                if (event.key === "Escape") {
                  event.preventDefault();
                  actions.closeSettingsPanel();
                }
              }}
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
                  modelDownloadsById={generation.modelDownloadsById}
                  modelDownloadStatus={generation.modelDownloadStatus}
                  modelDownloadProgress={generation.modelDownloadProgress}
                  modelDownloadErrorModelId={generation.modelDownloadErrorModelId}
                  modelDownloadError={generation.modelDownloadError}
                  onChangeSetting={actions.changeSetting}
                  onSaveProviderSettings={actions.saveProviderSettings}
                  onSelectProviderModel={actions.selectProviderModel}
                  onDiscoverProviderModels={actions.discoverProviderModels}
                  onSaveApiKey={actions.saveApiKey}
                  onSaveAsrSettings={actions.saveAsrSettings}
                  onRevealAsrApiKey={actions.revealAsrApiKey}
                  onTestAsrConnection={actions.testAsrConnection}
                  onRevealOpenaiApiKey={actions.revealOpenaiApiKey}
                  onTestProviderConnection={actions.testProviderConnection}
                  onDownloadFasterWhisperModel={actions.downloadFasterWhisperModel}
                  onCancelFasterWhisperModelDownload={actions.cancelFasterWhisperModelDownload}
                  onDownloadRagModel={actions.downloadRagModel}
                  onCancelRagModelDownload={actions.cancelRagModelDownload}
                  onCheckApplicationUpdate={actions.checkApplicationUpdate}
                  onScheduleApplicationUpdate={actions.scheduleApplicationUpdate}
                  onResetSettings={actions.resetSettings}
                  onOpenUsagePage={() => {
                    actions.closeSettingsPanel();
                    actions.openUsagePage();
                  }}
                  onClose={actions.closeSettingsPanel}
                />
              </Suspense>
            </motion.div>
          )}
        </AnimatePresence>

        {/* Usage Overlay */}
        <AnimatePresence>
          {state.usagePageOpen && (
            <motion.div
              ref={usageModalRef}
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.2 }}
              onKeyDown={(event) => {
                if (event.key === "Escape") {
                  event.preventDefault();
                  actions.closeUsagePage();
                }
              }}
              className="absolute inset-0 z-50 bg-stone-900/20 dark:bg-black/50 backdrop-blur-md flex justify-center items-center p-4 md:p-8"
            >
              <Suspense fallback={<WorkspaceModalLoadingState />}>
                <WorkspaceUsagePage
                  usage={generation.providerUsage}
                  range={generation.providerUsageRange}
                  loading={generation.providerUsageLoading}
                  error={generation.providerUsageError}
                  onChangeRange={actions.changeProviderUsageRange}
                  onClose={actions.closeUsagePage}
                />
              </Suspense>
            </motion.div>
          )}
        </AnimatePresence>
      </main>

      <ChatDrawer
        isOpen={chat.drawerOpen}
        onClose={chat.closeDrawer}
        width={layout.chatDrawerWidth}
        onWidthChange={updateChatDrawerWidth}
        {...chatPanelProps}
      />

      {importModalState && (
        <WorkspaceImportModal
          mode={importModalState.mode}
          targetSeriesId={importModalState.targetSeriesId ?? null}
          targetSeriesTitle={importModalState.targetSeriesTitle ?? ""}
          onClose={() => setImportModalState(null)}
          onResolveSeries={async (provider, url) => actions.resolveLinkedSeries(provider, url)}
          onResolveVideo={async (provider, url, targetSeriesId) => (
            targetSeriesId
              ? actions.resolveSeriesVideo(provider, url, targetSeriesId)
              : actions.resolvePlaygroundVideo(provider, url)
          )}
          onInitExternalCookie={actions.initExternalCookie}
          onLoadChaoxingStatus={actions.loadChaoxingStatus}
          onInitChaoxing={actions.initChaoxing}
          onCancelChaoxingInit={actions.cancelChaoxingInit}
          onCancelChaoxingImport={actions.cancelChaoxingImport}
          onLoadChaoxingCourses={actions.loadChaoxingCourses}
          onImportChaoxingCourse={actions.importChaoxingCourse}
           onSelectLocalMedia={actions.selectLocalMedia}
           onImportLocalSeries={async (seriesTitle, sourcePaths, storageMode) => actions.importLocalSeries(seriesTitle, sourcePaths, storageMode)}
           onImportSeriesVideos={async (seriesId, sourcePaths) => actions.importSeriesVideos(seriesId, sourcePaths)}
           onImportLocalPlaygroundVideos={async (sourcePaths) => actions.importLocalPlaygroundVideos(sourcePaths)}
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
            } else if (pendingDelete.kind === "videos") {
              await actions.deleteVideos?.(pendingDelete.videoIds);
            } else if (pendingDelete.kind === "series-batch") {
              await actions.deleteSeriesByIds?.(pendingDelete.seriesIds);
            }
            setPendingDelete(null);
          } finally {
            setDeletePending(false);
          }
        }}
      />
      <WorkspaceRenameDialog
        open={pendingRename != null}
        entityLabel={pendingRename?.entityLabel ?? ""}
        initialTitle={pendingRename?.title ?? ""}
        pending={renamePending}
        onCancel={() => {
          if (!renamePending) setPendingRename(null);
        }}
        onConfirm={async (title) => {
          if (!pendingRename || renamePending) return;
          setRenamePending(true);
          try {
            if (pendingRename.kind === "series") {
              await actions.renameSeries?.(title);
            } else {
              await actions.renameCurrentVideo?.(title);
            }
            setPendingRename(null);
          } finally {
            setRenamePending(false);
          }
        }}
      />
    </div>
  );
}

function WorkspaceKnowledgeMemoryStatusBar({ snapshot }) {
  const [dismissedSnapshotKey, setDismissedSnapshotKey] = useState(null);
  if (!snapshot || snapshot.status === "idle") {
    return null;
  }
  const snapshotKey = `${snapshot.status}:${snapshot.sequence ?? 0}:${snapshot.updatedAt ?? 0}`;
  if (dismissedSnapshotKey === snapshotKey) {
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
  const title = isRunning ? "数据库整理中" : isFailed ? "数据库整理失败" : "数据库已整理";
  const detail = isFailed
    ? snapshot.error ?? "服务发生异常，请稍后重试。"
    : snapshot.detail ?? (isRunning ? "正在构建视频关联知识库，完成后即可开始提问。" : "知识库已准备就绪，可用于问答检索。");
  const progressText = typeof snapshot.progress === "number" ? `${Math.round(snapshot.progress)}%` : "";
  const toneClassName = isFailed
    ? "border-danger bg-danger-subtle text-danger"
    : "border-warning bg-warning-subtle text-warning";

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
      <button
        type="button"
        onClick={() => setDismissedSnapshotKey(snapshotKey)}
        className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-full opacity-70 transition-colors hover:bg-white/60 hover:opacity-100 dark:hover:bg-black/20"
        title="关闭状态提示"
        aria-label="关闭状态提示"
      >
        <X size={16} />
      </button>
    </div>
  );
}

function WorkspaceSidePaneLoadingState({ title }) {
  return (
    <section className="flex-1 min-w-[320px] h-full overflow-y-auto relative z-10 border-l border-stone-200/80 dark:border-stone-800/90 transition-all">
      <div className="flex h-full items-center justify-center p-8">
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
