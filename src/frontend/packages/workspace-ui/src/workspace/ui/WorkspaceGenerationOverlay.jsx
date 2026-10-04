import { useEffect, useRef, useState } from "react";
import { LoaderCircle, X } from "lucide-react";
import { motion } from "framer-motion";

import { generationStageLabel, visibleGenerationSteps } from "../model/generationSteps";

function formatDurationLabel(value, fallback = "计算中") {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    return fallback;
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
  const [liveElapsedSeconds, setLiveElapsedSeconds] = useState(0);
  const localStartedAtRef = useRef(null);
  const stepsRef = useRef(null);
  const steps = visibleGenerationSteps(generationSnapshot, mode);
  const runningCount = steps.filter((step) => step.status === "running").length;
  const isPreparing = ["queued", "claimed", "prepare", "preparing", "initialize"].includes(generationSnapshot?.stage);
  const hasRealGenerationProgress = typeof generationProgress === "number" && generationProgress > 0 && !isPreparing;
  const generationProgressLabel = hasRealGenerationProgress ? `${Math.round(generationProgress)}%` : "准备中";
  const activeStageLabel = generationStageLabel(generationSnapshot?.stage);
  useEffect(() => {
    if (stepsRef.current) stepsRef.current.scrollTop = stepsRef.current.scrollHeight;
  }, [generationSnapshot?.stage]);
  useEffect(() => {
    if (!["running", "cancelling"].includes(generationSnapshot?.status)) {
      localStartedAtRef.current = null;
      setLiveElapsedSeconds(0);
      return undefined;
    }
    if (localStartedAtRef.current === null) {
      localStartedAtRef.current = Date.now() / 1000;
    }
    const updateElapsed = () => {
      const snapshotElapsed = Number(generationSnapshot.elapsedSeconds) || 0;
      const startedAt = generationSnapshot.startedAt;
      const clockElapsed = typeof startedAt === "number" && Number.isFinite(startedAt) && startedAt > 0
        ? Math.max(0, Date.now() / 1000 - startedAt)
        : Math.max(0, Date.now() / 1000 - localStartedAtRef.current);
      setLiveElapsedSeconds(Math.max(snapshotElapsed, clockElapsed));
    };
    updateElapsed();
    const timer = window.setInterval(updateElapsed, 1000);
    return () => window.clearInterval(timer);
  }, [generationSnapshot]);

  const elapsedLabel = formatDurationLabel(liveElapsedSeconds, "0秒");
  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      transition={{ duration: 0.2 }}
      className="absolute inset-0 z-50 flex items-center justify-center bg-white/40 p-3 backdrop-blur-[4px] pointer-events-auto dark:bg-neutral-950/50"
    >
      <motion.div
        initial={{ scale: 0.9, y: 10 }}
        animate={{ scale: 1, y: 0 }}
        exit={{ scale: 0.9 }}
        transition={{ type: "spring", damping: 25, stiffness: 350 }}
        role="dialog" aria-modal="true" aria-label={title}
        className="flex max-h-full w-[380px] max-w-full flex-col items-center gap-3 overflow-hidden rounded-3xl border border-stone-200/60 bg-white/95 p-6 text-center shadow-2xl dark:border-white/10 dark:bg-stone-900/95"
      >
        <LoaderCircle size={30} className="shrink-0 animate-spin text-accent" strokeWidth={2.5} />
        <div className="flex min-h-0 w-full flex-col">
          <h3 className="mb-1.5 text-base font-bold text-stone-900 dark:text-stone-100">{title}</h3>
          <p aria-live="polite" className="mb-2 text-[13px] font-medium text-stone-600 dark:text-stone-400">
            {generationSnapshot?.detail ?? "任务已提交，正在准备处理视频"}
          </p>
          <p className="mb-3 text-xs font-bold text-accent">
            {activeStageLabel} · {generationProgressLabel}
          </p>
          <div role="progressbar" aria-label="生成流程进度" aria-valuemin={0} aria-valuemax={100} aria-valuenow={hasRealGenerationProgress ? generationProgress : undefined} aria-valuetext={activeStageLabel} className="relative shrink-0 h-1.5 w-full overflow-hidden rounded-full bg-stone-200/60 dark:bg-stone-800">
            {hasRealGenerationProgress ? (
              <motion.div
                key="determinate"
                className="absolute inset-y-0 left-0 bg-accent"
                initial={{ width: "0%" }}
                animate={{ width: `${generationProgress}%` }}
                transition={{ duration: 0.2, ease: "easeOut" }}
              />
            ) : (
              <motion.div
                key="indeterminate"
                className="absolute inset-y-0 left-0 w-1/3 rounded-full bg-accent"
                initial={{ x: "-100%" }}
                animate={{ x: "300%" }}
                transition={{ duration: 1.1, repeat: Infinity, ease: "linear" }}
              />
            )}
          </div>
          <div className="mt-3 flex shrink-0 items-center justify-between text-xs text-stone-500">
            <span><span>已耗时</span> {elapsedLabel}</span>
            {runningCount > 1 && <span>有 {runningCount} 项同时进行</span>}
          </div>
          <p className="mt-2 shrink-0 text-left text-[11px] leading-relaxed text-stone-500">进度随处理步骤更新，AI 阅读和生成内容时可能需要等待。</p>
          <ol ref={stepsRef} aria-label="处理步骤" className="mt-3 flex min-h-0 flex-col gap-1.5 overflow-y-auto overscroll-contain">
            {steps.map((item) => {
              const isCurrent = item.status === "running";
              const isDone = item.status === "completed";
              const statusLabel = { running: "进行中", completed: "已完成", pending: "待处理", failed: "未完成", cancelled: "已停止" }[item.status];
              return (
                <li key={item.id} className={`shrink-0 rounded-xl border px-3 py-2 text-left ${isCurrent ? "border-accent/30 bg-accent/8" : isDone ? "border-success/30 bg-success-subtle" : "border-stone-200/70 bg-stone-50/70 dark:border-white/8 dark:bg-white/[0.03]"}`}>
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-xs font-medium text-stone-700 dark:text-stone-300">{item.label}</span>
                    <span className={`shrink-0 text-[11px] font-semibold ${isCurrent ? "text-accent" : isDone ? "text-success" : "text-stone-400"}`}>{statusLabel}</span>
                  </div>
                  {isCurrent && item.detail && <p className="mt-1 text-[11px] leading-relaxed text-stone-500 dark:text-stone-400">{item.detail}</p>}
                </li>
              );
            })}
          </ol>
          {typeof onCancel === "function" && ["queued", "retrying", "running", "cancelling"].includes(generationSnapshot?.status) ? (
            <button
              type="button"
              onClick={onCancel}
              disabled={generationSnapshot?.status === "cancelling"}
              className="mt-4 shrink-0 inline-flex w-full items-center justify-center gap-2 rounded-2xl border border-red-200 bg-white px-4 py-2.5 text-sm font-semibold text-red-600 transition-colors hover:bg-red-50 disabled:opacity-50 disabled:cursor-not-allowed dark:border-red-900/70 dark:bg-stone-900 dark:text-red-300 dark:hover:bg-red-950/30"
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
