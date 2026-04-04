import { useState } from "react";
import { LoaderCircle } from "lucide-react";
import { WorkspaceLibraryPanel } from "./WorkspaceLibraryPanel";
import { WorkspaceReadingPane } from "./WorkspaceReadingPane";
import { WorkspaceSeriesGrid } from "./WorkspaceSeriesGrid";
import { WorkspaceSettingsPanel } from "./WorkspaceSettingsPanel";
import { WorkspaceToolbar } from "./WorkspaceToolbar";
import { WorkspaceChatPanel } from "./WorkspaceChatPanel";
import { motion, AnimatePresence } from "framer-motion";
import { staggerContainer, blurVariant, popScaleVariant } from "../../../lib/animations";

const GENERATION_STAGE_ITEMS = [
  { id: "probe", label: "分析视频" },
  { id: "extract_audio", label: "MP4 转音频" },
  { id: "transcribe", label: "Whisper 转写" },
  { id: "enhance_transcript", label: "AI 修正文本" },
  { id: "summarize", label: "AI 生成概况" },
  { id: "completed", label: "完成" },
];

function summarizeLibrary(library) {
  const series = library?.series ?? [];
  const totalVideos = series.reduce((count, item) => count + item.videos.length, 0);
  const processedVideos = series.reduce(
    (count, item) => count + item.videos.filter((video) => video.processed).length,
    0,
  );

  return {
    seriesCount: series.length,
    totalVideos,
    processedVideos,
    latestSeries: series.slice(0, 3),
  };
}

function formatDurationLabel(value) {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    return "--";
  }
  const totalSeconds = Math.max(0, Math.round(value));
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  if (minutes >= 60) {
    const hours = Math.floor(minutes / 60);
    const remainingMinutes = minutes % 60;
    return `${hours}小时${remainingMinutes}分${seconds}秒`;
  }
  if (minutes > 0) {
    return `${minutes}分${seconds}秒`;
  }
  return `${seconds}秒`;
}

export function WorkspacePage({
  state,
  ui,
  library,
  tools,
  summary,
  mindmap,
  knowledgeCards,
  notes,
  activeSeries,
  selectedVideo,
  selectedNode,
  previewUrl,
  previewSeekRequest,
  chatMessages,
  chatPending,
  fasterWhisperModels,
  fasterWhisperModelsLoading,
  downloadingModelId,
  modelDownloadProgress,
  isGeneratingMindmapSelectedVideo,
  isGeneratingSelectedVideo,
  knowledgeCardsLoading,
  notesLoading,
  savingNote,
  selectedContextType,
  onSelectSeries,
  onEnterLibraryHome,
  onSelectVideo,
  onSelectSeriesContext,
  onSelectTool,
  onFocusNode,
  onOpenCard,
  onSubmitChat,
  onGenerateVideo,
  onGenerateMindmap,
  onGenerateKnowledgeCards,
  onCreateNote,
  onUpdateNote,
  onDeleteNote,
  onToggleSettingsPanel,
  onCloseSettingsPanel,
  onChangeSetting,
  onDownloadFasterWhisperModel,
  onCancelFasterWhisperModelDownload,
  onResetSettings,
}) {
  const [isSidebarOpen, setIsSidebarOpen] = useState(true);
  const librarySummary = summarizeLibrary(library);
  const generationSnapshot = state.generationSnapshot;
  const hasRealGenerationProgress = typeof state.generationProgress === "number";
  const generationProgressLabel = hasRealGenerationProgress
    ? `${Math.round(state.generationProgress)}%`
    : "处理中";
  const activeStageId = generationSnapshot?.status === "completed" ? "completed" : generationSnapshot?.stage;
  const activeStageLabel =
    GENERATION_STAGE_ITEMS.find((item) => item.id === activeStageId)?.label ?? "处理中";
  const elapsedLabel = formatDurationLabel(generationSnapshot?.elapsedSeconds);
  const estimatedTotalLabel = formatDurationLabel(generationSnapshot?.estimatedTotalSeconds);
  const remainingLabel = formatDurationLabel(generationSnapshot?.remainingSeconds);

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
              isGeneratingSelectedVideo={isGeneratingSelectedVideo}
              onEnterLibraryHome={onEnterLibraryHome}
              onSelectSeriesContext={onSelectSeriesContext}
              onSelectVideo={onSelectVideo}
              onGenerateVideo={onGenerateVideo}
            />
          ) : (
            <WorkspaceSeriesGrid library={library} onOpenSeries={onSelectSeries} compact />
          )}
        </div>
      </aside>

      {/* Main Studio Area */}
      <main className="workspace-panel flex-1 min-w-0 flex flex-col relative rounded-[2rem] border overflow-hidden z-10">
        <WorkspaceToolbar
          settingsOpen={state.settingsPanelOpen}
          activeSeries={activeSeries}
          onEnterLibraryHome={onEnterLibraryHome}
          onToggleSettingsPanel={onToggleSettingsPanel}
          isSidebarOpen={isSidebarOpen}
          onToggleSidebar={() => setIsSidebarOpen(!isSidebarOpen)}
        />

        {state.error && (
          <div className="mx-6 mt-4 p-4 rounded-2xl bg-red-50/90 dark:bg-red-950/40 text-red-800 dark:text-red-200 border border-red-100 dark:border-red-900/70 text-sm flex-shrink-0 relative z-20">
            {state.error}
          </div>
        )}

        <div className="flex-1 min-h-0 relative flex overflow-hidden bg-transparent">
          {!activeSeries ? (
            <section className="flex-1 overflow-auto h-full bg-transparent">
              <div className="mx-auto flex h-full max-w-5xl flex-col gap-6 p-8 xl:p-10">
                <motion.div variants={blurVariant} initial="initial" animate="animate" className="workspace-hero-surface rounded-[2rem] border p-8">
                  <p className="text-xs font-bold uppercase tracking-widest text-stone-600 dark:text-zinc-400">Information Panel</p>
                  <h2 className="mt-3 text-4xl font-bold text-stone-900 dark:text-stone-100">Workspace 信息面板</h2>
                  <p className="mt-4 max-w-3xl text-lg leading-relaxed text-stone-600 dark:text-stone-400">
                    左侧书架现在就是首页主内容，右侧只负责提供当前工作区的汇总信息、说明和最近书架概览，不再重复展示整块首页卡片。
                  </p>
                </motion.div>

                <motion.div variants={staggerContainer} initial="initial" animate="animate" className="grid grid-cols-1 gap-4 md:grid-cols-3">
                  <motion.article variants={blurVariant} className="workspace-muted-panel rounded-3xl border p-6">
                    <p className="text-sm font-semibold uppercase tracking-widest text-stone-500 dark:text-stone-400">系列总数</p>
                    <strong className="mt-3 block text-4xl font-bold text-stone-900 dark:text-stone-100">{librarySummary.seriesCount}</strong>
                  </motion.article>
                  <motion.article variants={blurVariant} className="workspace-muted-panel rounded-3xl border p-6">
                    <p className="text-sm font-semibold uppercase tracking-widest text-stone-500 dark:text-stone-400">视频总数</p>
                    <strong className="mt-3 block text-4xl font-bold text-stone-900 dark:text-stone-100">{librarySummary.totalVideos}</strong>
                  </motion.article>
                  <motion.article variants={blurVariant} className="rounded-3xl border border-sky-200/80 dark:border-sky-900/60 bg-sky-50/80 dark:bg-sky-950/25 p-6">
                    <p className="text-sm font-semibold uppercase tracking-widest text-sky-700 dark:text-sky-300">已处理视频</p>
                    <strong className="mt-3 block text-4xl font-bold text-sky-900 dark:text-sky-100">{librarySummary.processedVideos}</strong>
                  </motion.article>
                </motion.div>

                <motion.div variants={staggerContainer} initial="initial" animate="animate" className="grid grid-cols-1 gap-6 lg:grid-cols-[1.3fr_0.9fr]">
                  <motion.article variants={blurVariant} className="workspace-muted-panel rounded-[2rem] border p-7">
                    <p className="text-xs font-bold uppercase tracking-widest text-stone-500 dark:text-stone-400">How To Use</p>
                    <div className="mt-4 flex flex-col gap-4 text-sm leading-relaxed text-stone-600 dark:text-stone-400">
                      <p>1. 在左侧选择一个 series，进入该主题下的视频工作区。</p>
                      <p>2. 进入 series 后，在左栏选择视频并生成 AI 概况。</p>
                      <p>3. 再从工具页进入 AI概况、思维导图或视频预览。</p>
                    </div>
                  </motion.article>

                  <motion.article variants={blurVariant} className="workspace-muted-panel rounded-[2rem] border p-7">
                    <p className="text-xs font-bold uppercase tracking-widest text-stone-500 dark:text-stone-400">Recent Shelves</p>
                    <div className="mt-4 flex flex-col gap-3">
                      {librarySummary.latestSeries.map((seriesItem, index) => (
                        <motion.button
                          key={seriesItem.id}
                          type="button"
                          variants={blurVariant}
                          whileHover="hover"
                          whileTap="tap"
                          onClick={() => onSelectSeries(seriesItem.id)}
                          className="workspace-elevated-panel rounded-2xl border px-4 py-3 text-left hover:border-stone-300 dark:hover:border-white/16 hover:bg-white dark:hover:bg-[#1f1f1f] hover:shadow-[0_8px_20px_rgba(15,23,42,0.05)] dark:hover:shadow-[0_8px_20px_rgba(0,0,0,0.2)]"
                        >
                          <strong className="block text-sm font-semibold text-stone-900 dark:text-stone-100">{seriesItem.title}</strong>
                          <span className="mt-1 block text-xs text-stone-500 dark:text-stone-400">{seriesItem.videos.length} 个视频</span>
                        </motion.button>
                      ))}
                    </div>
                  </motion.article>
                </motion.div>
              </div>
            </section>
          ) : (
            <>
              {/* Center AI Chat */}
              <section className="flex-1 min-w-[380px] h-full overflow-hidden block border-r border-stone-200/70 dark:border-stone-800/90">
                 <WorkspaceChatPanel
                   activeSeries={activeSeries}
                   selectedVideo={selectedVideo}
                   selectedContextType={selectedContextType}
                   selectedToolId={state.selectedToolId}
                   tools={tools}
                   chatMessages={chatMessages}
                   chatPending={chatPending}
                   onSubmitChat={onSubmitChat}
                 />
              </section>

              {/* Right Reading Pane */}
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
                    knowledgeCardsLoading={knowledgeCardsLoading}
                    notesLoading={notesLoading}
                    savingNote={savingNote}
                    isGeneratingMindmapSelectedVideo={isGeneratingMindmapSelectedVideo}
                    isGeneratingSelectedVideo={isGeneratingSelectedVideo}
                    onSelectTool={onSelectTool}
                    onFocusNode={onFocusNode}
                    onOpenCard={onOpenCard}
                    onGenerateMindmap={onGenerateMindmap}
                    onGenerateKnowledgeCards={onGenerateKnowledgeCards}
                    onCreateNote={onCreateNote}
                    onUpdateNote={onUpdateNote}
                    onDeleteNote={onDeleteNote}
                  />
                </motion.section>
              </AnimatePresence>
            </>
          )}

          {/* Loading Overlay when generating AI Summary */}
          <AnimatePresence>
            {activeSeries && isGeneratingSelectedVideo && (
              <motion.div 
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                transition={{ duration: 0.2 }}
                className="absolute inset-0 z-50 bg-white/40 dark:bg-[#0a0a0a]/50 backdrop-blur-[4px] flex justify-center items-center pointer-events-auto"
              >
                <motion.div 
                  initial={{ scale: 0.9, y: 10 }} animate={{ scale: 1, y: 0 }} exit={{ scale: 0.9 }} transition={{ type: "spring", damping: 25, stiffness: 350 }}
                  className="bg-white/90 dark:bg-stone-900/90 py-8 px-10 rounded-3xl shadow-2xl border border-stone-200/60 dark:border-white/10 flex flex-col items-center gap-5 text-center w-[340px]"
                >
                  <LoaderCircle size={36} className="animate-spin text-[#0b6bff]" strokeWidth={2.5} />
                  <div className="w-full">
                    <h3 className="font-bold text-stone-900 dark:text-stone-100 text-base mb-1.5">正在生成 AI 概况</h3>
                    <p className="text-[13px] font-medium text-stone-500 dark:text-stone-400 mb-2">
                      {generationSnapshot?.detail ?? "正在阅读视频并提炼核心内容..."}
                    </p>
                    <p className="text-xs font-bold text-[#0b6bff] mb-3">
                      {activeStageLabel} · {generationProgressLabel}
                    </p>
                    <div className="w-full h-1.5 bg-stone-200/60 dark:bg-stone-800 rounded-full overflow-hidden relative">
                      {hasRealGenerationProgress ? (
                        <motion.div 
                          className="absolute inset-y-0 left-0 bg-[#0b6bff]"
                          initial={{ width: "0%" }}
                          animate={{ width: `${state.generationProgress}%` }}
                          transition={{ duration: 0.2, ease: "easeOut" }}
                        />
                      ) : (
                        <motion.div
                          className="absolute inset-y-0 left-0 w-1/3 rounded-full bg-[#0b6bff]"
                          initial={{ x: "-120%" }}
                          animate={{ x: "320%" }}
                          transition={{ duration: 1.1, repeat: Infinity, ease: "easeInOut" }}
                        />
                      )}
                    </div>
                    <div className="mt-4 grid grid-cols-3 gap-2 text-left">
                      <div className="rounded-2xl border border-stone-200/70 bg-stone-50/80 px-3 py-2 dark:border-white/8 dark:bg-white/[0.03]">
                        <p className="text-[10px] uppercase tracking-[0.18em] text-stone-400 dark:text-stone-500">已耗时</p>
                        <p className="mt-1 text-sm font-semibold text-stone-900 dark:text-stone-100">{elapsedLabel}</p>
                      </div>
                      <div className="rounded-2xl border border-stone-200/70 bg-stone-50/80 px-3 py-2 dark:border-white/8 dark:bg-white/[0.03]">
                        <p className="text-[10px] uppercase tracking-[0.18em] text-stone-400 dark:text-stone-500">预计总时长</p>
                        <p className="mt-1 text-sm font-semibold text-stone-900 dark:text-stone-100">{estimatedTotalLabel}</p>
                      </div>
                      <div className="rounded-2xl border border-stone-200/70 bg-stone-50/80 px-3 py-2 dark:border-white/8 dark:bg-white/[0.03]">
                        <p className="text-[10px] uppercase tracking-[0.18em] text-stone-400 dark:text-stone-500">预计剩余</p>
                        <p className="mt-1 text-sm font-semibold text-stone-900 dark:text-stone-100">{remainingLabel}</p>
                      </div>
                    </div>
                    <div className="mt-4 flex flex-col gap-2">
                      {GENERATION_STAGE_ITEMS.filter((item) => item.id !== "completed" || generationSnapshot?.status === "completed").map((item) => {
                        const activeIndex = GENERATION_STAGE_ITEMS.findIndex((stage) => stage.id === activeStageId);
                        const itemIndex = GENERATION_STAGE_ITEMS.findIndex((stage) => stage.id === item.id);
                        const isCurrent = item.id === activeStageId;
                        const isDone = activeIndex > -1 && itemIndex < activeIndex;
                        return (
                          <div
                            key={item.id}
                            className={`flex items-center justify-between rounded-2xl border px-3 py-2 text-left transition-colors ${
                              isCurrent
                                ? "border-[#0b6bff]/30 bg-[#0b6bff]/8"
                                : isDone
                                  ? "border-emerald-200/80 bg-emerald-50/80 dark:border-emerald-900/50 dark:bg-emerald-950/20"
                                  : "border-stone-200/70 bg-stone-50/70 dark:border-white/8 dark:bg-white/[0.03]"
                            }`}
                          >
                            <span className="text-xs font-medium text-stone-700 dark:text-stone-300">{item.label}</span>
                            <span className="text-[11px] font-semibold text-stone-400 dark:text-stone-500">
                              {isCurrent ? "进行中" : isDone ? "已完成" : "等待中"}
                            </span>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                </motion.div>
              </motion.div>
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
              <WorkspaceSettingsPanel
                ui={ui}
                fasterWhisperModels={fasterWhisperModels}
                fasterWhisperModelsLoading={fasterWhisperModelsLoading}
                downloadingModelId={downloadingModelId}
                modelDownloadProgress={modelDownloadProgress}
                onChangeSetting={onChangeSetting}
                onDownloadFasterWhisperModel={onDownloadFasterWhisperModel}
                onCancelFasterWhisperModelDownload={onCancelFasterWhisperModelDownload}
                onResetSettings={onResetSettings}
                onClose={onCloseSettingsPanel}
              />
            </motion.div>
          )}
        </AnimatePresence>
      </main>
    </div>
  );
}
