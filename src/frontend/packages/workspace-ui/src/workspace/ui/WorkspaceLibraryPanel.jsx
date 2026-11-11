import {useWorkspaceRuntime} from "../../runtime/WorkspaceProvider";
import {
  ArrowLeft,
  ArrowDown,
  Search,
  LoaderCircle,
  RefreshCw,
  Sparkles,
  FileVideo,
  CheckCircle2,
  AlertTriangle,
  CircleDashed,
  FolderKanban,
  Link2,
  ExternalLink,
  Trash2,
  Square,
  CheckSquare,
  X,
  Pencil,
  FileArchive,
  Captions,
  LayoutGrid,
  Network,
  Download,
  ChevronDown,
  Check,
} from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import { createPortal } from "react-dom";
import { useEffect, useMemo, useRef, useState } from "react";
import { buildVideoKey } from "../model/workspaceControllerUtils";
import { isBilibiliInboxSeries, isPlaygroundSeries } from "../model/workspaceControllerConstants";
import { useOutsidePointerUp } from "../../shared/lib/useOutsidePointerUp";
import { WorkspaceOverflowMenu } from "./shared/WorkspaceOverflowMenu";
import { WorkspaceSelectionBar } from "./shared/WorkspaceSelectionControls";
import { WorkspaceCover, formatDuration } from "./shared/WorkspaceCover";
import { AI_SUMMARY_TEMPLATES, getAiSummaryTemplate } from "../model/aiSummaryTemplates";

const slideTransition = { type: "spring", stiffness: 350, damping: 25, mass: 0.8 };


function AiSummaryTemplateMenu({ value, onChange, disabled = false }) {
  const [open, setOpen] = useState(false);
  const selectedTemplate = getAiSummaryTemplate(value);

  return (
    <WorkspaceOverflowMenu
      open={open}
      onOpenChange={setOpen}
      disabled={disabled}
      label={`选择 AI 概括风格（当前：${selectedTemplate.label}）`}
      placement="top"
      menuClassName="min-w-[150px]"
      triggerClassName="inline-flex min-h-[42px] shrink-0 items-center gap-1 border-l border-current/20 px-2.5 transition-colors hover:bg-black/5 active:bg-black/10 disabled:cursor-not-allowed disabled:opacity-50 dark:hover:bg-soft dark:active:bg-softer"
      triggerContent={
        <ChevronDown
          size={16}
          strokeWidth={2.5}
          className={`transition-transform duration-200 ${open ? "rotate-180" : ""}`}
        />
      }
    >
      {AI_SUMMARY_TEMPLATES.map((template) => {
        const selected = template.id === selectedTemplate.id;
        return (
          <button
            key={template.id}
            type="button"
            onClick={() => {
              onChange?.(template.id);
              setOpen(false);
            }}
            className={`flex w-full items-center justify-between gap-3 rounded-xl px-3 py-2 text-left text-xs font-semibold transition-colors ${selected
              ? "bg-accent/10 text-accent font-bold"
              : "text-body hover:bg-muted"
              }`}
          >
            <span>{template.label}</span>
            {selected ? <Check size={14} className="text-accent shrink-0" strokeWidth={2.5} /> : null}
          </button>
        );
      })}
    </WorkspaceOverflowMenu>
  );
}

function ProcessingModeMenu({ mode, onChange, disabled = false }) {
  const [open, setOpen] = useState(false);
  const targetMode = mode === "transcript" ? "summary" : "transcript";
  const targetLabel = targetMode === "transcript" ? "字幕模式" : "概括模式";

  return (
    <WorkspaceOverflowMenu
      open={open}
      onOpenChange={setOpen}
      disabled={disabled}
      label="切换处理模式"
      menuClassName="min-w-[148px]"
    >
      <ProcessingModeMenuItem
        mode={targetMode}
        label={targetLabel}
        onSelect={() => {
          onChange?.(targetMode);
          setOpen(false);
        }}
      />
    </WorkspaceOverflowMenu>
  );
}

function ProcessingModeMenuItem({ mode, label, onSelect }) {
  const Icon = mode === "transcript" ? Captions : Sparkles;
  return (
    <button
      type="button"
      onClick={onSelect}
      className="flex w-full items-center gap-2 rounded-xl px-3 py-2 text-left text-xs font-semibold text-body transition-colors hover:bg-muted"
    >
      <Icon size={15} className="text-accent" />
      {label}
    </button>
  );
}

function VideoIndexBadge({ state, rebuilding, onRebuild }) {
  const labels = { missing: "索引缺失", stale: "索引已过期", failed: "索引不可用" };
  if (!labels[state]) return null;
  return (
    <span className="inline-flex items-center gap-1">
      <span className="inline-flex items-center gap-1 rounded-md border border-warning-border bg-warning-subtle px-2 py-0.5 text-xs font-bold text-warning">
        <AlertTriangle size={12} />
        {labels[state]}
      </span>
      <button type="button" onClick={(event) => { event.stopPropagation(); onRebuild(); }}
        disabled={rebuilding} title={rebuilding ? "正在重建检索索引" : "重建检索索引"}
        aria-label="重建检索索引"
        className="inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-md text-warning transition-colors hover:bg-warning/15 disabled:cursor-wait disabled:opacity-50">
        <RefreshCw size={13} className={rebuilding ? "animate-spin" : ""} />
      </button>
    </span>
  );
}

function VideoBadge({ video }) {
  if (video.status === "source_missing") {
    return (
      <span
        className="inline-flex items-center gap-1 rounded-md border border-warning-border bg-warning-subtle px-2 py-0.5 text-xs font-bold uppercase tracking-wider text-warning"
        title="原始媒体文件当前不可访问，请重新链接媒体。"
      >
        <Link2 size={12} />
        链接丢失
      </span>
    );
  }
  if (!video.processed && (video.isLinked || video.status === "linked")) {
    return (
      <span className="inline-flex items-center gap-1 rounded-md border border-warning-border bg-warning-subtle px-2 py-0.5 text-xs font-bold uppercase tracking-wider text-warning">
        <Link2 size={11} />
        仅链接
      </span>
    );
  }
  if (video.status === "downloading") {
    return (
      <span className="inline-flex items-center gap-1 rounded-md border border-info-border bg-info-subtle px-2 py-0.5 text-xs font-bold uppercase tracking-wider text-info">
        <ArrowDown size={11} className="animate-bounce" />
        下载中
      </span>
    );
  }
  if (video.status === "untranscribable") {
    return (
      <span
        className="inline-flex items-center gap-1 rounded-md border border-warning-border bg-warning-subtle px-2 py-0.5 text-xs font-bold uppercase tracking-wider text-warning"
        title="没有可供转写使用的信息"
      >
        <AlertTriangle size={12} />
        无可转写信息
      </span>
    );
  }
  if (video.processed) {
    return (
      <span className="inline-flex items-center gap-1 rounded-md border border-success-border bg-success-subtle px-2 py-0.5 text-xs font-bold uppercase tracking-wider text-success">
        <CheckCircle2 size={12} />
        已生成概括
      </span>
    );
  }
  if (video.hasTranscript) {
    return (
      <span className="inline-flex items-center gap-1 rounded-md border border-accent/30 bg-accent/10 px-2 py-0.5 text-xs font-bold uppercase tracking-wider text-accent">
        <Captions size={12} />
        已有字幕
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1 text-xs font-bold uppercase tracking-wider px-2 py-0.5 rounded-md bg-soft text-subtle border border-transparent">
      <CircleDashed size={12} />
      未处理
    </span>
  );
}

export function getVideoGenerationButtonState({
  isGeneratingSeries,
  isGeneratingSelectedVideo,
  modelNeedsDownload,
  processed,
  hasTranscript = false,
  processingMode = "summary",
  sourceMissing = false,
}) {
  if (isGeneratingSeries) {
    return {
      disabled: true,
      label: "正在处理整个系列",
      tone: "busy",
    };
  }
  if (isGeneratingSelectedVideo) {
    return {
      disabled: false,
      label: processingMode === "transcript" ? "取消字幕获取" : "取消当前视频生成",
      tone: "danger",
    };
  }
  if (sourceMissing) {
    return {
      disabled: false,
      label: "链接媒体",
      tone: "primary",
    };
  }
  if (modelNeedsDownload) {
    return {
      disabled: false,
      label: "下载语音模型",
      tone: "primary",
    };
  }
  return {
    disabled: false,
    label: processingMode === "transcript"
      ? (hasTranscript ? "重新获取字幕" : "获取字幕文件")
      : (processed ? "重新生成 AI 概括" : "生成 AI 概括"),
    tone: "primary",
  };
}

export function getDeleteButtonState({ isGeneratingSeries, isGeneratingSelectedVideo }) {
  if (isGeneratingSeries || isGeneratingSelectedVideo) {
    return {
      disabled: true,
      label: "处理中",
    };
  }
  return {
    disabled: false,
    label: "删除当前视频",
  };
}

export function getSourceViewLabel(provider) {
  const labels = {
    bilibili: "在 Bilibili 中查看",
    douyin: "在抖音中查看",
    youtube: "在 YouTube 中查看",
  };
  return labels[provider] ?? "查看原媒体";
}

export function getVideoMediaIdentifier(video) {
  return video.sourceId || video.sourceName;
}

function PanelFooter({
  allowSourceRegeneration = true,
  summaryStyleInFooter = true,
  selectedContextType,
  selectedVideo,
  isGeneratingSelectedVideo,
  isGeneratingSeries,
  seriesGenerationQueue,
  downloadingVideoKey,
  activeSeries,
  currentAsrModel,
  ragModels,
  downloadProgress,
  downloadError,
  downloadErrorKey,
  onGenerateVideo,
  onProcessLinkedVideo,
  onRelinkVideo,
  onGenerateSeries,
  onCancelGeneration,
  onDownloadVideo,
  onAddPlaygroundVideo,
  onRequestRenameCurrentVideo,
  onRequestDeleteCurrentVideo,
  onOpenSettings,
  processingMode,
  onChangeProcessingMode,
}) {
  const isPlayground = isPlaygroundSeries(activeSeries);
  const modelNeedsDownload = currentAsrModel != null && !currentAsrModel.downloaded;
  const embeddingModel = ragModels?.find((model) => model.key === "embedding") ?? null;
  const embeddingNeedsDownload = embeddingModel != null && !embeddingModel.downloaded;
  const selectedVideoIsDownloading =
    activeSeries?.id && selectedVideo?.id && downloadingVideoKey === buildVideoKey(activeSeries.id, selectedVideo.id);
  const sourceViewLabel = getSourceViewLabel(selectedVideo?.provider);
  const hasSelectedVideoDownloadError =
    activeSeries?.id && selectedVideo?.id && downloadErrorKey === buildVideoKey(activeSeries.id, selectedVideo.id);
  const [footerOverflowOpen, setFooterOverflowOpen] = useState(false);
  const [aiSummaryTemplate, setAiSummaryTemplate] = useState("general");

  if (selectedContextType === "playground" || (isPlayground && !selectedVideo)) {
    return (
      <div className="workspace-toolbar-surface p-4 pr-6 border-t border-line/80 flex-shrink-0">
        <div className="mb-1">

          <h3 className="text-sm font-bold text-body">Playground Workspace</h3>
        </div>
        <p className="text-xs leading-relaxed text-subtle">
          添加或选择一个视频
        </p>
      </div>
    );
  }

  if (selectedContextType === "series") {
    const queueIsActive =
      seriesGenerationQueue != null &&
      seriesGenerationQueue.seriesId === activeSeries?.id &&
      (seriesGenerationQueue.status === "running" || seriesGenerationQueue.status === "cancelling");
    const queueLabel = queueIsActive
      ? `已完成 ${seriesGenerationQueue.completed}/${seriesGenerationQueue.total}`
      : null;
    const seriesVideos = activeSeries?.videos ?? [];
    const seriesComplete = seriesVideos.length > 0 && seriesVideos.every((video) =>
      processingMode === "transcript" ? video.hasTranscript : video.processed);
    return (
      <div className="workspace-toolbar-surface p-4 pr-6 border-t border-line/80 flex-shrink-0">
        <div className="mb-1">
          <h3 className="text-sm font-bold text-body">当前范围：整个系列</h3>
        </div>
        <p className="text-xs leading-relaxed text-subtle">
          {embeddingNeedsDownload
            ? "检索模型还没下载，下载后才能针对整个系列提问。"
            : `在对话栏里可以直接问「${activeSeries?.title}」整个系列的内容。`}
        </p>
        <div className="mt-3">
          {queueIsActive ? (
            <div className="mb-3 rounded-2xl border border-accent/20 bg-accent/8 px-3 py-2 text-xs text-subtle">
              <div className="flex items-center justify-between gap-2 font-semibold text-accent">
                <span>{seriesGenerationQueue.status === "cancelling" ? "正在取消全部处理" : processingMode === "transcript" ? "正在获取全部字幕" : "正在处理全部视频"}</span>
                <span>{queueLabel}</span>
              </div>
            </div>
          ) : null}
          {embeddingNeedsDownload ? (
            <button
              type="button"
              onClick={onOpenSettings}
              className="mb-2 w-full inline-flex items-center justify-center gap-2 rounded-2xl border border-warning-border/80 bg-warning-subtle/80 px-4 py-2.5 text-sm font-semibold text-warning transition-colors hover:bg-warning/15"
            >
              <ArrowDown size={16} strokeWidth={2.5} />
              下载 RAG 向量模型
            </button>
          ) : null}
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={isGeneratingSeries ? onCancelGeneration : onGenerateSeries}
              disabled={isGeneratingSeries ? !onCancelGeneration : seriesComplete}
              className={`min-w-0 flex-1 inline-flex items-center justify-center gap-2 rounded-xl px-4 py-2 text-sm font-semibold transition-all ${isGeneratingSeries
                ? "btn-danger-ghost border border-danger-border text-danger"
                : seriesComplete
                  ? "cursor-default border border-line text-faint"
                  : "border border-accent/40 bg-accent/8 text-accent hover:bg-accent/14 hover:border-accent/60"
                }`}
            >
              {isGeneratingSeries ? (
                <>
                  <LoaderCircle size={16} className="animate-spin" />
                  {onCancelGeneration ? "取消处理整个系列" : "正在处理整个系列"}
                </>
              ) : (
                <>
                  {seriesComplete ? <Check size={16} strokeWidth={2.5} /> : processingMode === "transcript" ? <Captions size={16} strokeWidth={2.5} /> : <Sparkles size={16} strokeWidth={2.5} />}
                  {seriesComplete
                    ? (processingMode === "transcript" ? "全部字幕已获取" : "系列已全部生成")
                    : processingMode === "transcript" ? "获取全部视频字幕" : "处理全部系列视频"}
                </>
              )}
            </button>
            {onChangeProcessingMode ? <ProcessingModeMenu mode={processingMode} onChange={onChangeProcessingMode} disabled={isGeneratingSeries} /> : null}
          </div>
        </div>
      </div>
    );
  }

  if (!selectedVideo) {
    return (
      <div className="workspace-toolbar-surface p-4 pr-6 border-t border-line/80 flex justify-center items-center h-[98px]">
        <p className="text-xs text-faint font-medium">可选择整个系列，或点某个视频进入视频工具</p>
      </div>
    );
  }

  if (selectedVideo.status === "downloading") {
    const hasDownloadProgress = typeof downloadProgress === "number" && Number.isFinite(downloadProgress) && downloadProgress > 0;
    const pct = hasDownloadProgress ? Math.max(0, Math.min(100, downloadProgress)) : null;
    return (
      <div className="workspace-toolbar-surface p-4 pr-6 border-t border-line/80 flex-shrink-0">
        <div className="mb-3">
          <p className="text-xs font-bold text-subtle tracking-wider uppercase mb-1 drop-shadow-sm">下载中</p>
          <h3 className="text-sm font-bold text-body truncate">{selectedVideo.title}</h3>
        </div>
        <div className="relative w-full overflow-hidden rounded-full bg-softer h-2.5 mb-1.5">
          {hasDownloadProgress ? (
            <div
              className="bg-accent h-2.5 rounded-full transition-all duration-300"
              style={{ width: `${pct}%` }}
            />
          ) : (
            <motion.div
              className="absolute inset-y-0 left-0 w-1/3 rounded-full bg-accent"
              initial={{ x: "-120%" }}
              animate={{ x: "320%" }}
              transition={{ duration: 1.1, repeat: Infinity, ease: "easeInOut" }}
            />
          )}
        </div>
        <p className="text-xs text-subtle font-medium">
          {hasDownloadProgress ? `${pct.toFixed(0)}% 完成` : "下载中"}
        </p>
        <button
          type="button"
          onClick={() => onDownloadVideo?.(selectedVideo)}
          className="btn-danger-ghost mt-3 inline-flex w-full items-center justify-center gap-2 rounded-2xl px-4 py-2.5 text-sm font-semibold"
        >
          <X size={15} />
          取消下载
        </button>
      </div>
    );
  }

  if (!selectedVideo.processed && (selectedVideo.isLinked || selectedVideo.status === "linked")) {
    return (
      <div className="workspace-toolbar-surface p-4 pr-6 border-t border-line/80 flex-shrink-0">
        <div className="mb-2">
          <div className="flex items-center justify-between gap-2">
            <p className="text-xs font-bold text-subtle tracking-wider uppercase drop-shadow-sm">当前视频</p>
            <div className="flex shrink-0 items-center gap-1">
            <button type="button" onClick={onRequestRenameCurrentVideo} className="inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-lg text-faint transition-colors hover:bg-soft hover:text-accent" title="重命名视频" aria-label="重命名视频"><Pencil size={14} /></button>
            <WorkspaceOverflowMenu
              open={footerOverflowOpen}
              onOpenChange={setFooterOverflowOpen}
              placement="bottom"
              menuClassName="min-w-[160px]"
            >
                  {onChangeProcessingMode && <ProcessingModeMenuItem
                    mode={processingMode === "transcript" ? "summary" : "transcript"}
                    label={processingMode === "transcript" ? "概括模式" : "字幕模式"}
                    onSelect={() => {
                      onChangeProcessingMode?.(processingMode === "transcript" ? "summary" : "transcript");
                      setFooterOverflowOpen(false);
                    }}
                  />}
                  {selectedVideo.sourceUrl && selectedVideo.provider !== "chaoxing" ? (
                    <a
                      href={selectedVideo.sourceUrl}
                      target="_blank"
                      rel="noopener noreferrer"
                      onClick={() => setFooterOverflowOpen(false)}
                      className="flex w-full items-center gap-2 px-4 py-2.5 text-xs font-medium text-body hover:bg-muted"
                      title={sourceViewLabel}
                    >
                      <ExternalLink size={14} />
                      {sourceViewLabel}
                    </a>
                  ) : null}
                  <button
                    type="button"
                    onClick={() => {
                      setFooterOverflowOpen(false);
                      onRequestDeleteCurrentVideo?.();
                    }}
                    className="flex w-full items-center gap-2 px-4 py-2.5 text-xs font-medium text-danger hover:bg-danger-subtle"
                  >
                    <Trash2 size={14} />
                    删除当前视频
                  </button>
            </WorkspaceOverflowMenu>
            </div>
          </div>
          <h3 className="mt-1 line-clamp-2 text-sm font-bold leading-snug text-body" title={selectedVideo.title}>{selectedVideo.title}</h3>
        </div>
        <button
          type="button"
          className={`w-full inline-flex items-center justify-center gap-2 rounded-2xl px-4 py-2.5 text-sm font-semibold transition-colors ${selectedVideoIsDownloading || isGeneratingSelectedVideo
              ? "btn-danger-ghost border border-danger-border text-danger"
              : "border border-accent/40 bg-accent/8 text-accent hover:bg-accent/14 hover:border-accent/60"
            }`}
          onClick={isGeneratingSelectedVideo
            ? onCancelGeneration
            : () => onDownloadVideo?.(selectedVideo)}
          disabled={isGeneratingSelectedVideo && !onCancelGeneration}
        >
          {isGeneratingSelectedVideo || selectedVideoIsDownloading ? <X size={16} strokeWidth={2.5} /> : <ArrowDown size={16} strokeWidth={2.5} />}
          {isGeneratingSelectedVideo ? (onCancelGeneration ? "取消当前处理" : "正在处理") : selectedVideoIsDownloading ? "取消下载" : "下载视频"}
        </button>
        {hasSelectedVideoDownloadError && downloadError ? (
          <div role="alert" className="mt-3 rounded-xl border border-danger-border bg-danger-subtle px-3 py-2.5 text-xs leading-5 text-danger">
            <p className="font-semibold">下载失败</p>
            <p className="mt-0.5">{downloadError}</p>
          </div>
        ) : null}
      </div>
    );
  }

  const videoGenerationButton = getVideoGenerationButtonState({
    isGeneratingSeries,
    isGeneratingSelectedVideo,
    modelNeedsDownload,
    processed: selectedVideo.processed,
    hasTranscript: selectedVideo.hasTranscript,
    processingMode,
    sourceMissing: selectedVideo.status === "source_missing",
  });
  const regenerationLocked = !allowSourceRegeneration && selectedVideo.processed && !isGeneratingSelectedVideo;
  if (regenerationLocked) {
    videoGenerationButton.disabled = true;
    videoGenerationButton.label = '产物已生成';
  }
  const deleteButton = getDeleteButtonState({
    isGeneratingSeries,
    isGeneratingSelectedVideo,
  });

  // Hosts that ask before generating (Cloud) choose the style in that confirmation instead.
  const showAiSummaryTemplateMenu = summaryStyleInFooter && processingMode === "summary" && selectedVideo.status !== "source_missing" && !regenerationLocked;
  const generationControlClass = videoGenerationButton.tone === "danger"
    ? "btn-danger-ghost border border-danger-border text-danger"
    : videoGenerationButton.tone === "busy"
      ? "motion-busy-button bg-softer text-subtle"
      : "border border-accent/40 bg-accent/8 text-accent";

  return (
    <div className="workspace-toolbar-surface p-4 pr-6 border-t border-line/80 flex-shrink-0">
      <div className="mb-2">
        <div className="flex items-center justify-between gap-2">
          <p className="text-xs font-bold text-subtle tracking-wider uppercase drop-shadow-sm">当前视频</p>
          <div className="flex shrink-0 items-center gap-1">
            <button type="button" onClick={onRequestRenameCurrentVideo} className="inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-lg text-faint transition-colors hover:bg-soft hover:text-accent" title="重命名视频" aria-label="重命名视频"><Pencil size={14} /></button>
            <WorkspaceOverflowMenu
              open={footerOverflowOpen}
              onOpenChange={setFooterOverflowOpen}
              placement="bottom"
              menuClassName="min-w-[160px]"
            >
              {onChangeProcessingMode && <ProcessingModeMenuItem
                mode={processingMode === "transcript" ? "summary" : "transcript"}
                label={processingMode === "transcript" ? "概括模式" : "字幕模式"}
                onSelect={() => {
                  onChangeProcessingMode?.(processingMode === "transcript" ? "summary" : "transcript");
                  setFooterOverflowOpen(false);
                }}
              />}
              {selectedVideo.sourceUrl && selectedVideo.provider !== "chaoxing" ? (
                <a
                  href={selectedVideo.sourceUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  onClick={() => setFooterOverflowOpen(false)}
                  className="flex w-full items-center gap-2 px-4 py-2.5 text-xs font-medium text-body hover:bg-muted"
                  title={sourceViewLabel}
                >
                  <ExternalLink size={14} />
                  {sourceViewLabel}
                </a>
              ) : null}
              <button
                type="button"
                disabled={deleteButton.disabled}
                onClick={() => {
                  setFooterOverflowOpen(false);
                  onRequestDeleteCurrentVideo?.();
                }}
                className="flex w-full items-center gap-2 px-4 py-2.5 text-xs font-medium text-danger hover:bg-danger-subtle disabled:cursor-not-allowed disabled:opacity-50"
              >
                <Trash2 size={14} />
                {deleteButton.disabled ? deleteButton.label : "删除当前视频"}
              </button>
            </WorkspaceOverflowMenu>
          </div>
        </div>
        <h3 className="mt-1 line-clamp-2 text-sm font-bold leading-snug text-body" title={selectedVideo.title}>{selectedVideo.title}</h3>
      </div>
      {modelNeedsDownload ? (
        <div className="mb-3 rounded-2xl border border-warning-border/80 bg-warning-subtle/80 px-4 py-3 text-xs leading-6 text-warning">
          当前语音模型 `{currentAsrModel.label}` 尚未下载，请先到设置中下载后再生成 AI 概括。
        </div>
      ) : null}
      <div className={`flex w-full overflow-hidden rounded-2xl ${generationControlClass}`}>
        <button
          type="button"
          className={`min-w-0 flex-1 inline-flex items-center justify-center gap-2 px-4 py-2.5 text-sm font-semibold transition-colors ${videoGenerationButton.tone === "primary" ? "hover:bg-accent/14 active:scale-[0.98]" : "disabled:cursor-not-allowed"}`}
          onClick={
            videoGenerationButton.tone === "danger"
              ? onCancelGeneration
              : modelNeedsDownload
                ? onOpenSettings
                : selectedVideo.status === "source_missing"
                  ? onRelinkVideo
                  : () => onGenerateVideo?.(aiSummaryTemplate)
          }
          disabled={videoGenerationButton.disabled || (isGeneratingSelectedVideo && !onCancelGeneration)}
        >
          {videoGenerationButton.tone === "danger" || videoGenerationButton.tone === "busy" ? (
            <>
              <LoaderCircle size={16} strokeWidth={2.5} className="animate-spin" />
              {isGeneratingSelectedVideo && !onCancelGeneration ? "正在处理" : videoGenerationButton.label}
            </>
          ) : modelNeedsDownload ? (
            <>
              <ArrowDown size={16} strokeWidth={2.5} />
              {videoGenerationButton.label}
            </>
          ) : (
            <>
              {selectedVideo.status === "source_missing" ? <Link2 size={16} strokeWidth={2.5} /> : <Sparkles size={16} strokeWidth={2.5} />}
              {videoGenerationButton.label}
            </>
          )}
        </button>
        {showAiSummaryTemplateMenu ? (
          <AiSummaryTemplateMenu
            value={aiSummaryTemplate}
            onChange={setAiSummaryTemplate}
            disabled={videoGenerationButton.disabled || modelNeedsDownload}
          />
        ) : null}
      </div>
      {processingMode === "transcript" || showAiSummaryTemplateMenu ? (
        <p className="mt-1.5 text-xs text-faint">
          {processingMode === "transcript"
            ? "仅获取字幕"
            : `将直接生成风格为“${getAiSummaryTemplate(aiSummaryTemplate).label}”的概括`}
        </p>
      ) : null}
    </div>
  );
}
export function WorkspaceLibraryPanel({
  allowSourceRegeneration = true,
  summaryStyleInFooter = true,
  activeSeries,
  indexSnapshot = null,
  selectedContextType,
  selectedVideo,
  isGeneratingSelectedVideo,
  isGeneratingSeries,
  seriesGenerationQueue,
  downloadingVideoKey,
  currentAsrModel,
  ragModels,
  onEnterLibraryHome,
  onSelectSeriesContext,
  onSelectVideo,
  onGenerateVideo,
  onProcessLinkedVideo,
  onGenerateSeries,
  onCancelGeneration,
  onDownloadVideo,
  onAddPlaygroundVideo,
  onAddSeriesVideo,
  onDeleteSeries,
  onRequestRenameSeries,
  onRequestRenameCurrentVideo,
  onRequestDeleteCurrentVideo,
  onRequestDeleteSeries,
  onRequestBulkDelete,
  seriesHasActiveWork = false,
  activeWorkSummary = "",
  bulkDeleteResult = null,
  downloadProgress,
  downloadError,
  downloadErrorKey,
  onOpenSettings,
  processingMode = "summary",
  onChangeProcessingMode,
}) {
 const {api}=useWorkspaceRuntime();
  const [indexRebuildPending, setIndexRebuildPending] = useState(false);
  const [indexRebuildError, setIndexRebuildError] = useState(null);
  useEffect(() => { setIndexRebuildPending(false); }, [indexSnapshot]);
  const rebuildIndex = async () => {
    setIndexRebuildPending(true);
    setIndexRebuildError(null);
    try {
      await api.fetchJson("/api/workspace/index/refresh", { method: "POST" });
    } catch (error) {
      setIndexRebuildPending(false);
      setIndexRebuildError(error instanceof Error ? error.message : "提交重建任务失败");
    }
  };
  const videos = activeSeries?.videos ?? [];
  const isPlayground = isPlaygroundSeries(activeSeries);
  const isBilibiliInbox = isBilibiliInboxSeries(activeSeries);
  const isLinkedSeries = Boolean(activeSeries?.isLinked);
  const [filterText, setFilterText] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");
  const [selectedVideoIds, setSelectedVideoIds] = useState([]);
  const [overflowOpen, setOverflowOpen] = useState(false);
  const [seriesExportOpen, setSeriesExportOpen] = useState(false);
  const [seriesExportScope, setSeriesExportScope] = useState("all");
  useEffect(() => {
    const existingIds = new Set(videos.map((video) => video.id));
    setSelectedVideoIds((current) => current.filter((videoId) => existingIds.has(videoId)));
  }, [videos]);
  const normalizedFilter = filterText.trim().toLowerCase();
  const isVideoCompleteForMode = (video) => processingMode === "transcript" ? video.hasTranscript : video.processed;
  const generatedCount = useMemo(() => videos.filter(isVideoCompleteForMode).length, [processingMode, videos]);
  const pendingCount = useMemo(() => videos.filter((video) => !isVideoCompleteForMode(video)).length, [processingMode, videos]);
  const filteredVideos = useMemo(() => {
    return videos.filter((video) => {
      if (statusFilter === "generated" && !isVideoCompleteForMode(video)) {
        return false;
      }
      if (statusFilter === "pending" && isVideoCompleteForMode(video)) {
        return false;
      }
      if (!normalizedFilter) {
        return true;
      }
      const haystacks = [video.title, video.sourceName, video.sourceUrl, video.coreProblem]
        .filter((value) => typeof value === "string")
        .map((value) => value.toLowerCase());
      return haystacks.some((value) => value.includes(normalizedFilter));
    });
  }, [normalizedFilter, processingMode, statusFilter, videos]);
  const selectedVideoSet = useMemo(() => new Set(selectedVideoIds), [selectedVideoIds]);
  const selectedCount = selectedVideoIds.length;
  const toggleVideoSelection = (videoId) => {
    setSelectedVideoIds((current) => current.includes(videoId)
      ? current.filter((id) => id !== videoId)
      : [...current, videoId]);
  };
  const selectFilteredVideos = () => {
    setSelectedVideoIds(filteredVideos.map((video) => video.id));
  };
  const seriesDeleteButton = getDeleteButtonState({
    isGeneratingSeries,
    isGeneratingSelectedVideo: false,
  });

  return (
    <section className="flex flex-col h-full w-full bg-transparent relative">

      {/* Sidebar Header */}
      <div className="p-5 pb-4 border-b border-line/80 flex-shrink-0">
        <div className="mb-3 flex items-center justify-between gap-2 pr-10 md:pr-0">
          <button
            type="button"
            className="-ml-2 inline-flex h-8 items-center gap-1.5 rounded-xl px-2 text-sm font-semibold text-subtle transition-colors hover:bg-soft hover:text-strong"
            onClick={onEnterLibraryHome}
          >
            <ArrowLeft size={16} />
            首页
          </button>
          <span className="truncate text-xs font-medium text-faint">
            {isPlayground ? "单个视频" : isBilibiliInbox ? "B站导入" : isLinkedSeries ? "链接系列" : "本地文件夹"}
          </span>
        </div>
        <div className="mb-4 flex items-center gap-3">
          {!isPlayground && !isBilibiliInbox ? (
            <div className="h-10 w-[72px] shrink-0 overflow-hidden rounded-lg border border-line/80">
              <WorkspaceCover url={activeSeries?.videos.find((video) => video.coverUrl)?.coverUrl} seed={activeSeries?.id} iconSize={16} />
            </div>
          ) : null}
          <h2 className="min-w-0 text-base font-bold leading-snug text-body line-clamp-2">{activeSeries?.title ?? "未选择系列"}</h2>
        </div>
        {!isPlayground ? (
          <div className="mb-4 flex items-center gap-2">
            <button
              type="button"
              onClick={() => onAddSeriesVideo?.()}
              className="flex-1 inline-flex items-center justify-center gap-2 rounded-2xl border border-accent/40 bg-accent/8 px-3 py-2 text-xs font-semibold text-accent transition-colors hover:bg-accent/14 hover:border-accent/60"
            >
              <ArrowDown size={14} />
              添加视频
            </button>
            <WorkspaceOverflowMenu
              open={overflowOpen}
              onOpenChange={setOverflowOpen}
              placement="bottom"
              menuClassName="min-w-[140px]"
            >
                  <button
                    type="button"
                    onClick={() => {
                      setOverflowOpen(false);
                      onRequestRenameSeries?.();
                    }}
                    className="flex w-full items-center gap-2 px-4 py-2.5 text-xs font-medium text-body hover:bg-muted"
                  >
                    <Pencil size={14} />
                    重命名系列
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      setOverflowOpen(false);
                      setSeriesExportScope("all");
                      setSeriesExportOpen(true);
                    }}
                    className="flex w-full items-center gap-2 px-4 py-2.5 text-xs font-medium text-body hover:bg-muted"
                  >
                    <FileArchive size={14} />
                    批量导出
                  </button>
                  <button
                    type="button"
                    disabled={seriesDeleteButton.disabled}
                    onClick={() => {
                      setOverflowOpen(false);
                      onRequestDeleteSeries?.();
                    }}
                    className="flex w-full items-center gap-2 px-4 py-2.5 text-xs font-medium text-danger hover:bg-danger-subtle disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    <Trash2 size={14} />
                    {seriesDeleteButton.disabled ? seriesDeleteButton.label : "删除整个系列"}
                  </button>
            </WorkspaceOverflowMenu>
          </div>
        ) : onAddPlaygroundVideo ? (
          <div className="mb-4">
            <button
              type="button"
              onClick={onAddPlaygroundVideo}
              className="w-full inline-flex items-center justify-center gap-2 rounded-2xl border border-accent/40 bg-accent/8 px-4 py-3 text-sm font-semibold text-accent shadow-none transition-colors hover:bg-accent/14 hover:border-accent/60"
            >
              <ArrowDown size={16} strokeWidth={2.5} />
              添加 Playground 媒体
            </button>
          </div>
        ) : null}

        {!isPlayground ? (
          <div className="flex flex-col gap-4">
            <div className="relative">
              <Search size={14} className="pointer-events-none absolute left-4 top-1/2 -translate-y-1/2 text-faint" />
              <input
                type="text"
                value={filterText}
                onChange={(event) => setFilterText(event.target.value)}
                placeholder="搜索视频"
                className="w-full rounded-2xl border border-line/80 bg-surface px-10 py-2.5 pr-10 text-sm text-body outline-none transition-colors placeholder:text-ghost focus:border-accent/40"
              />
              {filterText ? (
                <button
                  type="button"
                  onClick={() => setFilterText("")}
                  className="absolute right-3 top-1/2 inline-flex h-7 w-7 -translate-y-1/2 items-center justify-center rounded-full text-faint transition-colors hover:bg-soft hover:text-body"
                  aria-label="清空搜索"
                  title="清空搜索"
                >
                  <X size={14} />
                </button>
              ) : null}
            </div>
            <div className="flex rounded-xl bg-soft p-1" role="group" aria-label="视频状态筛选">
              {[
                ["all", "全部", videos.length],
                ["generated", processingMode === "transcript" ? "已获取" : "已生成", generatedCount],
                ["pending", processingMode === "transcript" ? "未获取" : "未处理", pendingCount],
              ].map(([value, label, count]) => (
                <button
                  key={value}
                  type="button"
                  onClick={() => setStatusFilter(value)}
                  aria-pressed={statusFilter === value}
                  className={`relative flex-1 rounded-lg px-2 py-1.5 text-xs font-semibold transition-all duration-200 ${statusFilter === value
                      ? "bg-surface text-strong shadow-sm"
                      : "text-faint hover:text-body"
                    }`}
                >
                  {label}
                  <span className={`ml-1 inline-flex min-w-[1.1rem] items-center justify-center rounded-full px-1 py-px text-xs font-bold leading-none ${statusFilter === value
                      ? "bg-accent/10 text-accent"
                      : "bg-softer/80 text-faint"
                    }`}>{count}</span>
                </button>
              ))}
            </div>
            {bulkDeleteResult ? (
              <div className="rounded-xl border border-line bg-muted px-3 py-2 text-xs leading-relaxed text-body">
                已删除 {bulkDeleteResult.deleted.length} 项{bulkDeleteResult.failed.length ? `，${bulkDeleteResult.failed.length} 项未删除。` : "。"}
                {bulkDeleteResult.failed.length ? (
                  <ul className="mt-1 list-disc pl-4">
                    {bulkDeleteResult.failed.map((item) => <li key={item.videoId}>{item.title}：{item.error}</li>)}
                  </ul>
                ) : null}
              </div>
            ) : null}
          </div>
        ) : null}

      </div>

      {/* Video / Source List */}
      <div className="relative flex flex-1 flex-col overflow-y-auto" aria-label="视频列表">
        {indexRebuildError ? <p role="alert" className="px-4 pt-3 text-xs text-danger">{indexRebuildError}</p> : null}
        <div className={`p-4 flex flex-col gap-3 ${selectedCount > 0 ? "pb-20" : ""}`}>
          {!isPlayground ? (
            <button
              type="button"
              onClick={onSelectSeriesContext}
              className={`text-left flex flex-col gap-2 p-4 rounded-2xl border transition-all duration-200 outline-none shadow-sm bg-accent/10 border-accent/30 text-strong z-10 relative
              ${selectedContextType === "series"
                  ? "ring-[2px] ring-accent/20"
                  : "hover:bg-accent/15 hover:border-accent/40 hover:-translate-y-0.5 hover:shadow-[0_10px_24px_rgba(15,23,42,0.08)] cursor-pointer"
                }`}
            >
              {/* The card header above already prints the source label + the full
                  series title, so this card used to repeat that title verbatim
                  and then add a sentence explaining what "series scope" means.
                  Both carried no new information: the title was a copy, and the
                  explanation only restated what the user reveals by clicking.

                  What survives is the scope statement itself — `整个系列` — which
                  is the one thing this card is here to distinguish from the
                  per-video cards below it. The badge keeps it scannable next to
                  those video rows without re-printing a title that is already on
                  screen one block above. */}
              <div className="flex items-center justify-between w-full gap-2">
                <span className="inline-flex items-center gap-1.5 text-sm font-semibold text-strong">
                  <FolderKanban size={14} className="text-accent" />
                  整个系列
                </span>
                <span className="inline-flex items-center text-xs font-bold uppercase tracking-wider px-2 py-0.5 rounded-md bg-accent/10 border border-accent/20 text-accent">
                  当前范围
                </span>
              </div>
            </button>
          ) : null}

          {filteredVideos.map((video, index) => {
            const isActive = video.id === selectedVideo?.id && selectedContextType !== "series";
            return (
              <div
                key={video.id}
                role="button"
                tabIndex={0}
                className={`motion-stagger text-left flex flex-col gap-2 p-4 rounded-2xl border transition-all duration-200 outline-none cursor-pointer relative z-10
                ${isActive
                    ? "border-transparent"
                    : "workspace-elevated-panel border-line hover:border-line-strong hover:bg-surface hover:-translate-y-0.5 hover:shadow-[0_8px_20px_rgba(15,23,42,0.06)] dark:hover:shadow-[0_8px_20px_rgba(0,0,0,0.22)]"
                  }`}
                style={{ "--stagger-index": index }}
                onClick={() => onSelectVideo(activeSeries.id, video.id)}
                onKeyDown={(event) => {
                  if (event.key === "Enter" || event.key === " ") {
                    event.preventDefault();
                    onSelectVideo(activeSeries.id, video.id);
                  }
                }}
              >
                {isActive && (
                  <motion.div
                    layoutId="library-bg"
                    className="absolute inset-0 bg-soft/80 border border-line-strong shadow-sm rounded-2xl -z-10"
                    transition={slideTransition}
                  />
                )}
                <div className="flex justify-between items-start w-full gap-2">
                  <div className="flex min-w-0 flex-wrap gap-1.5">
                    <VideoBadge video={video} />
                    <VideoIndexBadge
                      state={indexSnapshot?.seriesId === activeSeries?.id ? indexSnapshot.videoStates?.[video.id] : null}
                      rebuilding={indexRebuildPending || indexSnapshot?.status === "running"}
                      onRebuild={rebuildIndex}
                    />
                  </div>
                  <div className="flex items-center gap-2">
                    {!isPlayground ? (
                      <button
                        type="button"
                        disabled={seriesHasActiveWork}
                        onClick={(event) => {
                          event.stopPropagation();
                          toggleVideoSelection(video.id);
                        }}
                        className={`inline-flex h-7 w-7 items-center justify-center rounded-lg transition-colors disabled:cursor-not-allowed disabled:opacity-50 ${selectedVideoSet.has(video.id)
                            ? "bg-accent/10 text-accent"
                            : "text-faint hover:bg-soft hover:text-subtle"
                          }`}
                        aria-label={selectedVideoSet.has(video.id) ? `取消选择 ${video.title}` : `选择 ${video.title}`}
                      >
                        {selectedVideoSet.has(video.id) ? <CheckSquare size={16} /> : <Square size={16} />}
                      </button>
                    ) : null}
                  </div>
                </div>
                <div className="mt-1 flex gap-3">
                <div className="relative h-[50px] w-[88px] shrink-0 overflow-hidden rounded-lg border border-line/80">
                  <WorkspaceCover url={video.coverUrl} seed={video.id} iconSize={16} className={!video.processed && (video.isLinked || video.status === "linked") ? "opacity-70 grayscale-[0.5]" : ""} />
                  {formatDuration(video.durationSeconds) ? (
                    <span className="absolute bottom-1 right-1 rounded bg-black/70 px-1 text-[10px] font-semibold tabular-nums leading-4 text-white">{formatDuration(video.durationSeconds)}</span>
                  ) : null}
                </div>
                <div className="flex min-w-0 flex-col gap-0.5">
                  <strong className={`text-sm font-semibold line-clamp-2 ${isActive ? "text-strong" : "text-body"}`}>
                    {video.title}
                  </strong>
                  {video.coreProblem ? (
                    <span
                      className="text-xs text-subtle line-clamp-2 leading-snug whitespace-pre-line"
                      title={video.coreProblem}
                    >
                      {video.coreProblem}
                    </span>
                  ) : null}
                  <span className="text-xs text-subtle truncate">
                    {getVideoMediaIdentifier(video)}
                  </span>
                </div>
                </div>
              </div>
            );
          })}
          {!isPlayground && filteredVideos.length === 0 ? (
            <div className="workspace-elevated-panel rounded-2xl border border-dashed border-line/80 px-4 py-8 text-center text-sm text-subtle">
              当前筛选条件下没有匹配的视频。
            </div>
          ) : null}
        </div>

        {/* Bulk action bar: mt-auto parks it at the bottom of a short list; sticky keeps it there while a long one scrolls. */}
        <AnimatePresence>
          {!isPlayground && selectedCount > 0 && (
            <motion.div
              initial={{ y: 16, opacity: 0 }}
              animate={{ y: 0, opacity: 1 }}
              exit={{ y: 16, opacity: 0 }}
              transition={{ type: "spring", stiffness: 400, damping: 28 }}
              className="sticky bottom-3 z-20 mx-4 mb-3 mt-auto"
            >
              <WorkspaceSelectionBar
                surface="raised"
                label="批量选择视频"
                selectedCount={selectedCount}
                selectAllDisabled={seriesHasActiveWork || filteredVideos.length === 0}
                onSelectAll={selectFilteredVideos}
                onClear={() => setSelectedVideoIds([])}
                extra={
                  <button
                    type="button"
                    disabled={seriesHasActiveWork}
                    onClick={() => onRequestBulkDelete?.(selectedVideoIds)}
                    className="inline-flex shrink-0 items-center gap-1.5 rounded-xl bg-danger-subtle px-3 py-1.5 text-xs font-semibold text-danger transition-colors hover:bg-danger/15 disabled:cursor-not-allowed disabled:opacity-50"
                    title={seriesHasActiveWork ? activeWorkSummary || "系列中有任务正在处理，暂不能批量删除" : "删除所选视频"}
                  >
                    <Trash2 size={14} />
                    删除
                  </button>
                }
              />
              {seriesHasActiveWork ? (
                <p className="mt-1.5 px-2 text-xs leading-relaxed text-warning">{activeWorkSummary || "系列中有任务正在处理，暂不能批量删除。"}</p>
              ) : null}
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      <PanelFooter
        allowSourceRegeneration={allowSourceRegeneration}
        summaryStyleInFooter={summaryStyleInFooter}
        selectedContextType={selectedContextType}
        selectedVideo={selectedVideo}
        isGeneratingSelectedVideo={isGeneratingSelectedVideo}
        isGeneratingSeries={isGeneratingSeries}
        seriesGenerationQueue={seriesGenerationQueue}
        downloadingVideoKey={downloadingVideoKey}
        activeSeries={activeSeries}
        currentAsrModel={currentAsrModel}
        ragModels={ragModels}
        downloadProgress={downloadProgress}
        downloadError={downloadError}
        downloadErrorKey={downloadErrorKey}
        onGenerateVideo={onGenerateVideo}
        onProcessLinkedVideo={onProcessLinkedVideo}
        onGenerateSeries={onGenerateSeries}
        onCancelGeneration={onCancelGeneration}
        onDownloadVideo={onDownloadVideo}
        onAddPlaygroundVideo={onAddPlaygroundVideo}
        onRequestRenameCurrentVideo={onRequestRenameCurrentVideo}
        onRequestDeleteCurrentVideo={onRequestDeleteCurrentVideo}
        onOpenSettings={onOpenSettings}
        processingMode={processingMode}
        onChangeProcessingMode={onChangeProcessingMode}
      />
      <SeriesExportPanel
        open={seriesExportOpen}
        seriesId={activeSeries?.id}
        selectedVideoIds={selectedVideoIds}
        videoCount={videos.length}
        scope={seriesExportScope}
        onScopeChange={setSeriesExportScope}
        onClose={() => setSeriesExportOpen(false)}
      />
    </section>
  );
}

function SeriesExportPanel({ open, seriesId, selectedVideoIds, videoCount, scope, onScopeChange, onClose }) {
  const {api}=useWorkspaceRuntime();
  const selectedCount = selectedVideoIds.length;
  const selectedAvailable = selectedCount > 0;
  const useSelected = scope === "selected" && selectedAvailable;
  const query = useSelected
    ? `?video_ids=${encodeURIComponent(selectedVideoIds.join(","))}`
    : "";
  const actions = [
    ["mixed", "AI 概括混合包", "Markdown · 概括、要点与逐字稿", Sparkles, "AI 概括"],
    ["knowledge-cards", "知识卡片", "Markdown · 逐条知识卡片", LayoutGrid, "知识卡片"],
    ["mindmaps", "思维导图", "Markdown · 章节层级导图", Network, "思维导图"],
    ["srt", "SRT 字幕", "SRT · 标准字幕，可直接导入播放器", Captions, "字幕"],
  ];
  // 打开面板或换范围时问后端每类能导出几个；统计失败时按钮照常可点，由后端兜底报错。
  const [availability, setAvailability] = useState({ status: "idle", kinds: null });
  const [confirmKind, setConfirmKind] = useState(null);
  useEffect(() => {
    if (!open || !seriesId) return undefined;
    let cancelled = false;
    setAvailability({ status: "loading", kinds: null });
    setConfirmKind(null);
    api.fetchJson(`/api/series/${encodeURIComponent(seriesId)}/exports/availability${query}`)
      .then((data) => { if (!cancelled) setAvailability({ status: "ready", kinds: data?.kinds ?? null }); })
      .catch(() => { if (!cancelled) setAvailability({ status: "error", kinds: null }); });
    return () => { cancelled = true; };
  }, [api, open, seriesId, query]);
  const exportHref = (kind) => api.resourceUrl(`/api/series/${encodeURIComponent(seriesId)}/exports/${kind}.zip${query}`);
  if (typeof document === "undefined") {
    return null;
  }
  return createPortal(
    <AnimatePresence>
      {open ? (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.2 }}
          className="fixed inset-0 z-[70] flex items-end justify-center bg-black/20 p-4 backdrop-blur-md sm:items-center sm:p-8"
          onClick={onClose}
        >
          <motion.div
            role="dialog"
            aria-modal="true"
            aria-labelledby="series-export-title"
            initial={{ opacity: 0, y: 24, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 16, scale: 0.98 }}
            transition={{ type: "spring", stiffness: 360, damping: 28 }}
            onClick={(event) => event.stopPropagation()}
            className="max-h-[85dvh] w-full max-w-lg overflow-y-auto overscroll-contain rounded-3xl border border-line bg-surface p-5 shadow-2xl sm:p-6"
          >
            <div className="flex items-start justify-between gap-4">
              <div className="min-w-0">
                <h3 id="series-export-title" className="mt-1 text-xl font-bold tracking-tight text-strong">批量导出</h3>
                <p className="mt-1.5 text-sm leading-relaxed text-faint">选好范围后，点击内容包即可开始下载。</p>
              </div>
              <button
                type="button"
                onClick={onClose}
                className="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-lg text-faint transition-colors hover:bg-soft hover:text-subtle focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
                aria-label="关闭批量导出"
              >
                <X size={17} />
              </button>
            </div>

            <section className="mt-6">
              <p className="text-xs font-bold uppercase tracking-[0.14em] text-faint">导出范围</p>
              <div className="mt-2.5 grid grid-cols-2 gap-2.5">
                <ScopeOption
                  selected={scope === "all"}
                  onSelect={() => onScopeChange("all")}
                  label="全部视频"
                  hint={videoCount ? `${videoCount} 个` : null}
                />
                <ScopeOption
                  selected={useSelected}
                  disabled={!selectedAvailable}
                  onSelect={() => onScopeChange("selected")}
                  label="已选视频"
                  hint={selectedAvailable ? `${selectedCount} 个` : null}
                />
              </div>
              {!selectedAvailable ? (
                <p className="mt-2.5 text-xs leading-relaxed text-faint">
                  想按选中项导出，先在左侧列表勾选视频。
                </p>
              ) : null}
            </section>

            <section className="mt-6">
              <p className="text-xs font-bold uppercase tracking-[0.14em] text-faint">导出内容</p>
              <div className="mt-2.5 flex flex-col gap-2.5">
                {actions.map(([kind, label, meta, Icon, noun]) => (
                  <SeriesExportAction
                    key={kind}
                    label={label}
                    meta={meta}
                    Icon={Icon}
                    noun={noun}
                    href={exportHref(kind)}
                    loading={availability.status === "loading"}
                    info={availability.kinds?.[kind] ?? null}
                    confirming={confirmKind === kind}
                    onConfirm={() => setConfirmKind(kind)}
                    onCancelConfirm={() => setConfirmKind(null)}
                    onDownload={onClose}
                  />
                ))}
              </div>
            </section>
          </motion.div>
        </motion.div>
      ) : null}
    </AnimatePresence>,
    document.body,
  );
}

const SERIES_EXPORT_ACTION_CLASS = "group flex w-full items-center gap-3 rounded-2xl border px-3.5 py-2.5 text-left transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent";
const SERIES_EXPORT_MISSING_PREVIEW = 5;

function SeriesExportAction({ label, meta, Icon, noun, href, loading, info, confirming, onConfirm, onCancelConfirm, onDownload }) {
  const available = info?.available ?? null;
  const total = info?.total ?? null;
  const missing = info?.missing ?? [];
  const empty = !loading && available === 0;
  const partial = !loading && available > 0 && missing.length > 0;
  const countText = loading ? null : info ? `${available}/${total}` : null;
  const body = (
    <>
      <span className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-xl ${empty ? "bg-muted text-faint" : "bg-accent/8 text-accent"}`}>
        <Icon size={17} />
      </span>
      <span className="min-w-0 flex-1">
        <span className={`block truncate text-sm font-semibold ${empty ? "text-faint" : "text-body"}`}>{label}</span>
        <span className="mt-0.5 block truncate text-xs text-faint">
          {empty ? `这些视频都还没有${noun}，暂时无法导出` : meta}
        </span>
      </span>
      {countText ? <span className="shrink-0 text-xs tabular-nums text-faint">{countText}</span> : null}
      {loading
        ? <LoaderCircle size={16} className="shrink-0 animate-spin text-faint" />
        : <Download size={16} className={`shrink-0 transition-colors ${empty ? "text-faint" : "text-faint group-hover:text-accent"}`} />}
    </>
  );
  const activeClass = "border-line bg-surface hover:border-accent/40 hover:bg-accent/5 dark:hover:border-accent/40 dark:hover:bg-accent/10";
  if (loading || empty) {
    return (
      <button type="button" disabled className={`${SERIES_EXPORT_ACTION_CLASS} cursor-not-allowed border-dashed border-line bg-muted`}>
        {body}
      </button>
    );
  }
  if (!partial) {
    return (
      <a href={href} download onClick={onDownload} className={`${SERIES_EXPORT_ACTION_CLASS} ${activeClass}`}>
        {body}
      </a>
    );
  }
  const preview = missing.slice(0, SERIES_EXPORT_MISSING_PREVIEW);
  return (
    <div className={`rounded-2xl ${confirming ? "border border-warning-border bg-warning-subtle" : ""}`}>
      <button
        type="button"
        aria-expanded={confirming}
        onClick={confirming ? onCancelConfirm : onConfirm}
        className={`${SERIES_EXPORT_ACTION_CLASS} ${confirming ? "border-transparent" : activeClass}`}
      >
        {body}
      </button>
      {confirming ? (
        <div className="px-3.5 pb-3">
          <p className="flex items-start gap-1.5 text-xs leading-relaxed text-body">
            <AlertTriangle size={14} className="mt-0.5 shrink-0 text-warning" />
            <span>{total} 个视频里有 {missing.length} 个还没有{noun}，导出时会跳过：</span>
          </p>
          <ul className="mt-1.5 space-y-0.5 pl-5 text-xs text-subtle">
            {preview.map((video) => <li key={video.id} className="truncate">{video.title || video.id}</li>)}
            {missing.length > preview.length ? <li>等 {missing.length} 个</li> : null}
          </ul>
          <div className="mt-3 flex justify-end gap-2">
            <button
              type="button"
              onClick={onCancelConfirm}
              className="rounded-xl px-3 py-1.5 text-xs font-semibold text-subtle transition-colors hover:bg-soft"
            >
              取消
            </button>
            <a
              href={href}
              download
              onClick={onDownload}
              className="rounded-xl border border-accent/40 px-3 py-1.5 text-xs font-semibold text-accent transition-colors hover:bg-accent/8"
            >
              导出其余 {available} 个
            </a>
          </div>
        </div>
      ) : null}
    </div>
  );
}

function ScopeOption({ selected, disabled = false, onSelect, label, hint }) {
  const stateClass = disabled
    ? "cursor-not-allowed border-dashed border-line bg-muted"
    : selected
      ? "border-accent/50 bg-accent/8"
      : "border-line bg-surface hover:border-line-strong hover:bg-muted";

  return (
    <button
      type="button"
      aria-pressed={selected}
      disabled={disabled}
      onClick={onSelect}
      className={`flex items-center gap-2.5 rounded-xl border px-3 py-2.5 text-left transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent ${stateClass}`}
    >
      <span
        aria-hidden="true"
        className={`flex h-4 w-4 shrink-0 items-center justify-center rounded-full border ${selected && !disabled ? "border-accent" : "border-line-strong"}`}
      >
        {selected && !disabled ? <span className="h-2 w-2 rounded-full bg-accent" /> : null}
      </span>
      <span className={`min-w-0 flex-1 truncate text-sm font-semibold ${disabled ? "text-faint" : "text-body"}`}>
        {label}
      </span>
      {hint ? (
        <span className="shrink-0 text-xs tabular-nums text-faint">{hint}</span>
      ) : null}
    </button>
  );
}
