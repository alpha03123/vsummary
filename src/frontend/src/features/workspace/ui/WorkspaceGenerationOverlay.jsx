import { LoaderCircle, X } from "lucide-react";
import { motion } from "framer-motion";
import { WorkspaceMetricCard } from "./shared/WorkspaceMetricCard";

/**
 * 进度浮层展示给用户的阶段清单（顺序即真实流水线顺序，`isDone` 判定依赖它）。
 *
 * 这里刻意只保留「用户能感知的 5 个阶段」：后端还有 `prepare`、`extract_screenshots`、
 * `load_manual_srt`、`probe_subtitles`、`cancelling` 等细分阶段，它们都通过下面的
 * `STAGE_ALIASES` 归并到相邻阶段，不再各占一行——否则浮层会出现十几行「等待中」，
 * 用户既读不完也看不懂。
 */
const GENERATION_STAGE_ITEMS = [
  { id: "preparing", label: "准备素材" },
  { id: "transcribe", label: "语音转写" },
  { id: "organize", label: "整理文字稿" },
  { id: "summarize", label: "生成概况" },
  { id: "publish", label: "整理并保存" },
  { id: "completed", label: "完成" },
];

/** 后端细分阶段 → 浮层阶段的归并映射（键为后端 `stage` 原文）。 */
const STAGE_ALIASES = {
  prepare: "preparing",
  queued: "preparing",
  batch: "preparing",
  queue: "preparing",
  download: "preparing",
  probe: "preparing",
  probe_subtitles: "preparing",
  extract_audio: "preparing",
  extract_subtitles: "preparing",
  load_manual_srt: "transcribe",
  load_transcript: "transcribe",
  enhance_transcript: "organize",
  extract_screenshots: "summarize",
  enrich_visual_summary: "summarize",
  finalize_ai_summary: "summarize",
};

/** 不落在阶段清单里、但需要单独文案的瞬态阶段。 */
const TRANSIENT_STAGE_LABELS = {
  reconnecting: "同步进度",
  cancelling: "正在取消",
};

/** 字幕模式下「整理文字稿 / 生成概况」不适用，直接隐藏。 */
const TRANSCRIPT_MODE_HIDDEN_STAGES = new Set(["organize", "summarize"]);

/** 把后端 stage 归一化成阶段清单里的 id；无法归类时返回 `null`。 */
const STAGE_IDS = new Set(GENERATION_STAGE_ITEMS.map((item) => item.id));

function resolveStageId(stage) {
  if (typeof stage !== "string" || !stage) {
    return null;
  }
  if (STAGE_IDS.has(stage)) {
    return stage;
  }
  const alias = STAGE_ALIASES[stage];
  return typeof alias === "string" && STAGE_IDS.has(alias) ? alias : null;
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

export function WorkspaceGenerationOverlay({
  generationProgress,
  generationSnapshot,
  title = "正在生成 AI 概况",
  mode = "summary",
  onCancel,
  cancelLabel = "取消",
}) {
  const isTranscriptMode = mode === "transcript";
  const hasRealGenerationProgress = typeof generationProgress === "number";
  const generationProgressLabel = hasRealGenerationProgress ? `${Math.round(generationProgress)}%` : "处理中";
  const rawStageId = generationSnapshot?.status === "completed" ? "completed" : generationSnapshot?.stage;
  const activeStageId = resolveStageId(rawStageId);
  const activeStageLabel =
    GENERATION_STAGE_ITEMS.find((item) => item.id === activeStageId)?.label ?? TRANSIENT_STAGE_LABELS[rawStageId] ?? "处理中";
  const elapsedLabel = formatDurationLabel(generationSnapshot?.elapsedSeconds);
  const estimatedTotalLabel = formatDurationLabel(generationSnapshot?.estimatedTotalSeconds);
  const remainingLabel = formatDurationLabel(generationSnapshot?.remainingSeconds);

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      transition={{ duration: 0.2 }}
      className="absolute inset-0 z-50 flex items-center justify-center bg-white/40 backdrop-blur-[4px] pointer-events-auto dark:bg-neutral-950/50"
    >
      <motion.div
        initial={{ scale: 0.9, y: 10 }}
        animate={{ scale: 1, y: 0 }}
        exit={{ scale: 0.9 }}
        transition={{ type: "spring", damping: 25, stiffness: 350 }}
        className="flex w-[340px] flex-col items-center gap-5 rounded-3xl border border-stone-200/60 bg-white/90 px-10 py-8 text-center shadow-2xl dark:border-white/10 dark:bg-stone-900/90"
      >
        <LoaderCircle size={36} className="animate-spin text-accent" strokeWidth={2.5} />
        <div className="w-full">
          <h3 className="mb-1.5 text-base font-bold text-stone-900 dark:text-stone-100">{title}</h3>
          <p className="mb-2 text-[13px] font-medium text-stone-600 dark:text-stone-400">
            {generationSnapshot?.detail ?? "正在阅读视频并提炼核心内容..."}
          </p>
          <p className="mb-3 text-xs font-bold text-accent">
            {activeStageLabel} · {generationProgressLabel}
          </p>
          <div className="relative h-1.5 w-full overflow-hidden rounded-full bg-stone-200/60 dark:bg-stone-800">
            {hasRealGenerationProgress ? (
              <motion.div
                className="absolute inset-y-0 left-0 bg-accent"
                initial={{ width: "0%" }}
                animate={{ width: `${generationProgress}%` }}
                transition={{ duration: 0.2, ease: "easeOut" }}
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
          <div className="mt-4 grid grid-cols-3 gap-2 text-left">
            <WorkspaceMetricCard label="已耗时" value={elapsedLabel} className="rounded-2xl px-3 py-2" labelClassName="text-[10px] text-stone-500 dark:text-stone-500" valueClassName="mt-1 text-sm" />
            <WorkspaceMetricCard label="预计总时长" value={estimatedTotalLabel} className="rounded-2xl px-3 py-2" labelClassName="text-[10px] text-stone-500 dark:text-stone-500" valueClassName="mt-1 text-sm" />
            <WorkspaceMetricCard label="预计剩余" value={remainingLabel} className="rounded-2xl px-3 py-2" labelClassName="text-[10px] text-stone-500 dark:text-stone-500" valueClassName="mt-1 text-sm" />
          </div>
          <div className="mt-4 flex flex-col gap-2">
            {GENERATION_STAGE_ITEMS.filter((item) => {
              if (item.id === "completed") {
                return generationSnapshot?.status === "completed";
              }
              if (isTranscriptMode && TRANSCRIPT_MODE_HIDDEN_STAGES.has(item.id)) {
                return false;
              }
              return true;
            }).map((item) => {
              const activeIndex = GENERATION_STAGE_ITEMS.findIndex((stage) => stage.id === activeStageId);
              const itemIndex = GENERATION_STAGE_ITEMS.findIndex((stage) => stage.id === item.id);
              const isCurrent = item.id === activeStageId;
              const isDone = activeIndex > -1 && itemIndex < activeIndex;
              // 未开始的阶段只留一个中性的等待点，不再逐行重复「等待中」。
              const statusLabel = isCurrent ? "进行中" : isDone ? "已完成" : "等待";
              return (
                <div
                  key={item.id}
                  className={`flex items-center justify-between rounded-2xl border px-3 py-2 text-left transition-colors ${
                    isCurrent
                      ? "border-accent/30 bg-accent/8"
                      : isDone
                        ? "border-success/30 bg-success-subtle"
                        : "border-stone-200/70 bg-stone-50/70 dark:border-white/8 dark:bg-white/[0.03]"
                  }`}
                >
                  <span className="text-xs font-medium text-stone-700 dark:text-stone-300">{item.label}</span>
                  <span
                    className={`text-[11px] font-semibold ${
                      isCurrent
                        ? "text-accent"
                        : isDone
                          ? "text-success"
                          : "text-stone-400 dark:text-stone-600"
                    }`}
                  >
                    {statusLabel}
                  </span>
                </div>
              );
            })}
          </div>
          {typeof onCancel === "function" && (generationSnapshot?.status === "running" || generationSnapshot?.status === "cancelling") ? (
            <button
              type="button"
              onClick={onCancel}
              disabled={generationSnapshot?.status === "cancelling"}
              className="mt-4 inline-flex w-full items-center justify-center gap-2 rounded-2xl border border-red-200 bg-white px-4 py-2.5 text-sm font-semibold text-red-600 transition-colors hover:bg-red-50 disabled:opacity-50 disabled:cursor-not-allowed dark:border-red-900/70 dark:bg-stone-900 dark:text-red-300 dark:hover:bg-red-950/30"
            >
              <X size={16} />
              {generationSnapshot?.status === "cancelling" ? "正在停止..." : cancelLabel}
            </button>
          ) : null}
        </div>
      </motion.div>
    </motion.div>
  );
}
