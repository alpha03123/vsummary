import { LoaderCircle } from "lucide-react";
import { motion } from "framer-motion";
import { WorkspaceMetricCard } from "./shared/WorkspaceMetricCard";

const GENERATION_STAGE_ITEMS = [
  { id: "probe", label: "分析视频" },
  { id: "extract_audio", label: "MP4 转音频" },
  { id: "transcribe", label: "Whisper 转写" },
  { id: "enhance_transcript", label: "AI 修正文本" },
  { id: "summarize", label: "AI 生成概况" },
  { id: "completed", label: "完成" },
];

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

export function WorkspaceGenerationOverlay({ generationProgress, generationSnapshot }) {
  const hasRealGenerationProgress = typeof generationProgress === "number";
  const generationProgressLabel = hasRealGenerationProgress ? `${Math.round(generationProgress)}%` : "处理中";
  const activeStageId = generationSnapshot?.status === "completed" ? "completed" : generationSnapshot?.stage;
  const activeStageLabel =
    GENERATION_STAGE_ITEMS.find((item) => item.id === activeStageId)?.label ?? "处理中";
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
          <h3 className="mb-1.5 text-base font-bold text-stone-900 dark:text-stone-100">正在生成 AI 概况</h3>
          <p className="mb-2 text-[13px] font-medium text-stone-500 dark:text-stone-400">
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
            <WorkspaceMetricCard label="已耗时" value={elapsedLabel} className="rounded-2xl px-3 py-2" labelClassName="text-[10px] text-stone-400 dark:text-stone-500" valueClassName="mt-1 text-sm" />
            <WorkspaceMetricCard label="预计总时长" value={estimatedTotalLabel} className="rounded-2xl px-3 py-2" labelClassName="text-[10px] text-stone-400 dark:text-stone-500" valueClassName="mt-1 text-sm" />
            <WorkspaceMetricCard label="预计剩余" value={remainingLabel} className="rounded-2xl px-3 py-2" labelClassName="text-[10px] text-stone-400 dark:text-stone-500" valueClassName="mt-1 text-sm" />
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
                      ? "border-accent/30 bg-accent/8"
                      : isDone
                        ? "border-success/30 bg-success-subtle"
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
  );
}
