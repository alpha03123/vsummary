import { lazy, Suspense, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { Sparkles, Plus, ArrowUp, LoaderCircle, ChevronRight, Wrench, Clock3, BrainCircuit, CheckCircle2, Trash2, FileText, PlayCircle } from "lucide-react";
import { formatRange } from "../../../shared/lib/time";

const WorkspaceMarkdownMessage = lazy(() =>
  import("./shared/WorkspaceMarkdownMessage").then((module) => ({
    default: module.WorkspaceMarkdownMessage,
  })),
);

function describeCurrentTool(selectedToolId) {
  if (selectedToolId === "series-home") {
    return "系列首页";
  }
  if (selectedToolId === "series-overview") {
    return "系列概览";
  }
  if (selectedToolId === "series-progress") {
    return "系列进度";
  }
  if (selectedToolId === "overview") {
    return "AI概况";
  }
  if (selectedToolId === "mindmap") {
    return "思维导图";
  }
  if (selectedToolId === "knowledge-cards" || selectedToolId === "cards") {
    return "知识卡片";
  }
  if (selectedToolId === "notes") {
    return "笔记";
  }
  if (selectedToolId === "preview") {
    return "视频预览";
  }
  return "工具首页";
}

export function WorkspaceChatPanel({
  workspaceTitle,
  activeSeries,
  selectedVideo,
  selectedContextType,
  selectedToolId,
  tools,
  chatMessages = [],
  chatSessions = [],
  activeSessionId = null,
  chatPending = false,
  contextUsage = null,
  contextUsageLoading = false,
  onStartNewChat,
  onSelectChatSession,
  onOpenSeekReference,
  onClearChat,
  onSubmitChat,
}) {
  const [draft, setDraft] = useState("");
  const scopeLabel = selectedContextType === "series"
    ? activeSeries?.title ?? "当前系列"
    : selectedVideo?.title ?? activeSeries?.title ?? workspaceTitle ?? "当前视频";
  const currentPageLabel = describeCurrentTool(selectedToolId);
  const suggestedPrompts = [
    "给我总结一下这个视频的核心结论",
    "帮我记一下这个视频的重点",
    "这个系列主要讲了哪些主题？",
    "某个知识点在视频里的什么时间出现？",
  ];

  function handleSubmit() {
    const trimmed = draft.trim();
    if (!trimmed || chatPending) {
      return;
    }
    onSubmitChat(trimmed);
    setDraft("");
  }

  function renderMessageContent(message, isAssistant) {
    if (message.kind === "thought-trace") {
      return <WorkspaceThoughtTraceMessage message={message} />;
    }

    if (message.kind === "tool-trace") {
      return <WorkspaceToolTraceMessage message={message} />;
    }

    if (message.kind === "seek-reference") {
      return <WorkspaceSeekReferenceMessage message={message} onOpenSeekReference={onOpenSeekReference} />;
    }

    if (!isAssistant) {
      return message.content;
    }

    return (
      <Suspense fallback={<AssistantMessageFallback content={message.content} />}>
        <WorkspaceMarkdownMessage content={message.content} />
      </Suspense>
    );
  }

  return (
    <div className="h-full w-full flex flex-col bg-transparent">
      {/* Header */}
      <div className="workspace-toolbar-surface shrink-0 flex items-center justify-between px-6 py-4 border-b border-stone-200/80 dark:border-stone-800">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-2xl bg-sky-50 dark:bg-sky-950/25 flex items-center justify-center border border-sky-100 dark:border-sky-900/60">
            <Sparkles size={16} className="text-sky-700 dark:text-sky-300" />
          </div>
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <h3 className="text-base font-bold text-stone-800 dark:text-stone-100">NotebookLM 助手</h3>
              <span className="rounded-full border border-stone-200/80 bg-stone-50 px-2.5 py-0.5 text-[11px] font-semibold text-stone-600 dark:border-stone-700 dark:bg-stone-900 dark:text-stone-300">
                {currentPageLabel}
              </span>
            </div>
            <p className="text-xs text-stone-500 dark:text-stone-400">基于《{scopeLabel}》</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            aria-label="新建对话"
            className="inline-flex items-center gap-2 rounded-full border border-stone-200/80 bg-white/80 px-3 py-1.5 text-xs font-semibold text-stone-600 transition hover:border-sky-300 hover:text-sky-700 dark:border-stone-700 dark:bg-stone-950/80 dark:text-stone-300 dark:hover:border-sky-700 dark:hover:text-sky-300"
            title="新建对话"
            onClick={onStartNewChat}
          >
            <Plus size={14} />
            新建对话
          </button>
          <button
            type="button"
            aria-label="清空当前对话"
            className="inline-flex items-center gap-2 rounded-full border border-stone-200/80 bg-white/80 px-3 py-1.5 text-xs font-semibold text-stone-600 transition hover:border-red-300 hover:text-red-700 dark:border-stone-700 dark:bg-stone-950/80 dark:text-stone-300 dark:hover:border-red-700 dark:hover:text-red-300"
            title="清空当前对话"
            onClick={onClearChat}
          >
            <Trash2 size={14} />
            清空
          </button>
        </div>
      </div>

      <WorkspaceContextUsageBanner usage={contextUsage} loading={contextUsageLoading} />

      {/* Chat History Area */}
      <div className="flex-1 overflow-auto p-6 md:p-8 flex flex-col gap-6">
        {chatSessions.length > 1 ? (
          <div className="flex flex-wrap gap-2">
            {chatSessions.map((session) => (
              <button
                key={session.id}
                type="button"
                onClick={() => onSelectChatSession?.(session.id)}
                className={`rounded-full border px-3 py-1.5 text-xs font-medium transition ${
                  session.id === activeSessionId
                    ? "border-sky-300 bg-sky-50 text-sky-700 dark:border-sky-700 dark:bg-sky-950/30 dark:text-sky-300"
                    : "border-stone-200/80 bg-white/80 text-stone-600 hover:border-sky-300 hover:text-sky-700 dark:border-stone-800 dark:bg-stone-950/80 dark:text-stone-300 dark:hover:border-sky-700 dark:hover:text-sky-300"
                }`}
              >
                {session.title}
              </button>
            ))}
          </div>
        ) : null}

        <div className="flex flex-wrap gap-2">
          {suggestedPrompts.map((prompt) => (
            <button
              key={prompt}
              type="button"
              onClick={() => setDraft(prompt)}
              className="rounded-full border border-stone-200/80 bg-white/80 px-3 py-1.5 text-xs font-medium text-stone-600 transition hover:border-[#0070f3]/30 hover:text-[#0070f3] dark:border-stone-800 dark:bg-stone-950/80 dark:text-stone-300 dark:hover:border-[#4da3ff]/30 dark:hover:text-[#4da3ff]"
            >
              {prompt}
            </button>
          ))}
        </div>

        {chatMessages.map((message) => {
          const isAssistant = message.role === "assistant";
          return (
            <div
              key={message.id}
              className={`flex items-start gap-4 max-w-2xl ${isAssistant ? "" : "self-end justify-end"}`}
            >
              {isAssistant ? (
                <div className="w-8 h-8 rounded-2xl bg-[#0070f3] flex items-center justify-center shrink-0 shadow-sm mt-1">
                  <Sparkles size={16} className="text-white" />
                </div>
              ) : null}
              <div className={`flex flex-col gap-2 ${isAssistant ? "" : "items-end"}`}>
                <div
                  className={
                    message.kind === "thought-trace"
                      || message.kind === "tool-trace"
                      || message.kind === "seek-reference"
                      ? "w-full"
                      : isAssistant
                      ? "workspace-elevated-panel markdown-body p-4 rounded-[1.5rem] rounded-tl-sm border text-stone-700 dark:text-stone-200 leading-relaxed"
                      : "px-5 py-3 rounded-[1.5rem] rounded-tr-sm bg-slate-800 dark:bg-slate-800/92 border border-slate-700/80 dark:border-slate-700 text-slate-50 shadow-sm"
                  }
                >
                  {renderMessageContent(message, isAssistant)}
                </div>
                <span className={`text-xs text-stone-400 dark:text-stone-500 ${isAssistant ? "ml-1" : ""}`}>{message.meta}</span>
              </div>
            </div>
          );
        })}

        {chatPending && chatMessages.every((message) => message.kind == null) ? (
          <div className="flex items-start gap-4 max-w-2xl">
            <div className="w-8 h-8 rounded-2xl bg-[#0070f3] flex items-center justify-center shrink-0 shadow-sm mt-1">
              <LoaderCircle size={16} className="animate-spin text-white" />
            </div>
            <div className="workspace-elevated-panel p-4 rounded-[1.5rem] rounded-tl-sm border text-stone-600 dark:text-stone-300">
              正在思考当前工具和上下文...
            </div>
          </div>
        ) : null}
      </div>

      {/* Input Area */}
      <div className="workspace-toolbar-surface shrink-0 p-5 border-t border-stone-200/80 dark:border-stone-800">
        <div className="max-w-4xl mx-auto relative rounded-[1.75rem] border workspace-input-surface group focus-within:border-[#0070f3] focus-within:ring-4 focus-within:ring-[#0070f3]/10 transition-all">
          <textarea 
            placeholder="提问或下达指令..." 
            className="w-full bg-transparent resize-none py-5 pl-6 pr-16 text-base text-stone-800 dark:text-stone-100 outline-none leading-relaxed h-[92px]"
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter" && !event.shiftKey) {
                event.preventDefault();
                handleSubmit();
              }
            }}
            disabled={chatPending}
          />
          <div className="absolute right-3 bottom-3">
             <button
               type="button"
               onClick={handleSubmit}
               disabled={chatPending || !draft.trim()}
               className="flex items-center justify-center w-10 h-10 rounded-full bg-stone-900 dark:bg-white text-white dark:text-black hover:bg-[#0070f3] hover:text-white transition-colors shadow-sm disabled:opacity-50 disabled:cursor-not-allowed"
             >
               {chatPending ? <LoaderCircle size={18} className="animate-spin" /> : <ArrowUp size={20} strokeWidth={2.5} />}
             </button>
          </div>
        </div>
        <p className="text-center text-xs text-stone-400 dark:text-stone-500 mt-4">
          AI 已接入当前工作区上下文，可返回证据卡片与工具联动动作。
        </p>
      </div>
    </div>
  );
}

function AssistantMessageFallback({ content }) {
  return <div className="whitespace-pre-wrap break-words">{content}</div>;
}

function WorkspaceContextUsageBanner({ usage, loading }) {
  if (loading && !usage) {
    return (
      <div className="border-b border-stone-200/70 bg-stone-50/75 px-6 py-3 text-xs text-stone-500 dark:border-stone-800 dark:bg-stone-950/50 dark:text-stone-400">
        正在估算当前上下文预算...
      </div>
    );
  }
  if (!usage) {
    return null;
  }

  const usageLabel = `${formatTokenCount(usage.estimatedTotalTokens)} / ${formatTokenCount(usage.windowTokens)}`;
  const thresholdLabel = usage.level === "blocking"
    ? "已超过阻塞阈值"
    : usage.level === "compact"
      ? "已进入压缩区间"
      : usage.level === "warning"
        ? "接近压缩阈值"
        : "预算充足";
  const progressWidth = `${Math.max(4, Math.min(100, usage.usagePercent))}%`;

  return (
    <div className="border-b border-stone-200/70 bg-stone-50/75 px-6 py-3 dark:border-stone-800 dark:bg-stone-950/50">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <strong className="text-xs font-semibold text-stone-700 dark:text-stone-200">上下文预算</strong>
            <span className={`rounded-full px-2 py-0.5 text-[11px] font-semibold ${resolveUsageToneClass(usage.level)}`}>
              {thresholdLabel}
            </span>
          </div>
          <p className="mt-1 text-xs text-stone-500 dark:text-stone-400">
            已估算 {usageLabel}，保留输出 {formatTokenCount(usage.reservedOutputTokens)}
          </p>
        </div>
        <div className="text-right text-xs text-stone-500 dark:text-stone-400">
          <div>{usage.usagePercent.toFixed(1)}%</div>
          <div>剩余 {formatTokenCount(usage.remainingTokens)}</div>
        </div>
      </div>
      <div className="mt-3 h-2 overflow-hidden rounded-full bg-stone-200/80 dark:bg-stone-800">
        <div
          className={`h-full rounded-full transition-all ${resolveUsageBarClass(usage.level)}`}
          style={{ width: progressWidth }}
        />
      </div>
      <div className="mt-3 flex flex-wrap gap-2">
        {usage.sources.map((source) => (
          <span
            key={source.id}
            className="rounded-full border border-stone-200/80 bg-white/90 px-2.5 py-1 text-[11px] font-medium text-stone-600 dark:border-stone-700 dark:bg-stone-900 dark:text-stone-300"
          >
            {source.label} {formatTokenCount(source.estimatedTokens)}
          </span>
        ))}
      </div>
    </div>
  );
}

function WorkspaceToolTraceMessage({ message }) {
  const steps = Array.isArray(message.toolTrace?.steps) ? message.toolTrace.steps : [];
  const durationLabel = formatDurationLabel(message.toolTrace?.durationMs);
  const isRunning = message.toolTrace?.status === "running";
  const isIdle = message.toolTrace?.status === "idle";

  return (
    <details open={isRunning} className="group rounded-[1.35rem] border border-stone-200/80 bg-white/90 shadow-sm dark:border-stone-800 dark:bg-[#151516]">
      <summary className="list-none cursor-pointer px-4 py-3.5">
        <div className="flex items-center gap-3 text-stone-700 dark:text-stone-200">
          <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-2xl bg-amber-50 text-amber-700 dark:bg-amber-950/30 dark:text-amber-300">
            <Wrench size={16} />
          </div>
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2">
              <strong className="text-[15px] font-semibold">{message.content}</strong>
              {durationLabel ? (
                <span className="inline-flex items-center gap-1 rounded-full bg-stone-100 px-2 py-0.5 text-[11px] font-medium text-stone-500 dark:bg-stone-800 dark:text-stone-400">
                  <Clock3 size={12} />
                  用时 {durationLabel}
                </span>
              ) : null}
              {isRunning ? (
                <span className="inline-flex items-center gap-1 rounded-full bg-amber-100 px-2 py-0.5 text-[11px] font-medium text-amber-700 dark:bg-amber-950/40 dark:text-amber-300">
                  <LoaderCircle size={12} className="animate-spin" />
                  调用中
                </span>
              ) : null}
            </div>
            <p className="mt-1 text-xs text-stone-500 dark:text-stone-400">
              {isRunning
                ? "工具正在执行中"
                : isIdle
                  ? "当前这一步已完成，等待下一步规划"
                  : "展开查看本轮实际调用的工具名和步骤说明"}
            </p>
          </div>
          <ChevronRight size={18} className="shrink-0 text-stone-400 transition-transform group-open:rotate-90" />
        </div>
      </summary>

      <div className="border-t border-stone-200/80 px-4 py-3 dark:border-stone-800">
        <div className="flex flex-col gap-2.5">
          {steps.map((step, index) => (
            <div
              key={`${step.toolName}-${index}`}
              className="rounded-2xl border border-stone-200/70 bg-stone-50/80 px-3 py-3 dark:border-stone-800 dark:bg-stone-900/70"
            >
              <div className="flex flex-wrap items-center gap-2">
                <code className="rounded-md bg-stone-200/80 px-2 py-0.5 text-[11px] font-semibold text-stone-700 dark:bg-stone-800 dark:text-stone-200">
                  {step.toolName}
                </code>
                <span className="text-sm font-medium text-stone-700 dark:text-stone-200">{step.label}</span>
                <span className={`rounded-full px-2 py-0.5 text-[11px] font-medium ${
                  step.status === "running"
                    ? "bg-amber-100 text-amber-700 dark:bg-amber-950/40 dark:text-amber-300"
                    : "bg-emerald-100 text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-300"
                }`}>
                  {step.status === "running" ? "进行中" : "已完成"}
                </span>
                {step.target ? (
                  <span className="truncate text-xs text-stone-500 dark:text-stone-400">({step.target})</span>
                ) : null}
                {shouldShowDuration(step.durationMs) ? (
                  <span className="text-xs text-stone-400 dark:text-stone-500">用时 {formatDurationLabel(step.durationMs)}</span>
                ) : null}
              </div>
            </div>
          ))}
        </div>
      </div>
    </details>
  );
}

function WorkspaceSeekReferenceMessage({ message, onOpenSeekReference }) {
  const reference = message.seekReference ?? {};
  const hasRange = typeof reference.seconds === "number";
  const title = hasRange
    ? `已定位到 ${formatRange(reference.seconds, reference.endSeconds ?? reference.seconds)}${reference.chapterTitle ? ` · ${reference.chapterTitle}` : ""}`
    : "已找到相关转写片段";

  return (
    <details className="group rounded-[1.35rem] border border-sky-200/80 bg-sky-50/85 shadow-sm dark:border-sky-900/60 dark:bg-sky-950/20">
      <summary className="list-none cursor-pointer px-4 py-3.5">
        <div className="flex items-center gap-3 text-sky-950 dark:text-sky-100">
          <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-2xl bg-white/80 text-sky-700 dark:bg-sky-950/50 dark:text-sky-300">
            <FileText size={16} />
          </div>
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2">
              <strong className="text-[15px] font-semibold">{title}</strong>
            </div>
            <p className="mt-1 text-xs text-sky-800/80 dark:text-sky-200/80">
              展开查看命中的转写片段，再决定是否跳到视频。
            </p>
          </div>
          <ChevronRight size={18} className="shrink-0 text-sky-500 transition-transform group-open:rotate-90" />
        </div>
      </summary>

      <div className="border-t border-sky-200/80 px-4 py-4 dark:border-sky-900/60">
        {reference.query ? (
          <p className="text-xs font-medium text-sky-800/90 dark:text-sky-200/90">
            检索问题：{reference.query}
          </p>
        ) : null}
        {reference.matchedText ? (
          <blockquote className="mt-3 rounded-2xl border border-sky-200/80 bg-white/80 px-4 py-3 text-sm leading-6 text-sky-950 dark:border-sky-900/60 dark:bg-sky-950/40 dark:text-sky-100">
            {reference.matchedText}
          </blockquote>
        ) : (
          <p className="mt-3 text-sm text-sky-900/80 dark:text-sky-100/80">
            当前没有返回完整命中原文，但已经定位到对应时间点。
          </p>
        )}
        <div className="mt-4 flex flex-wrap gap-2">
          <button
            type="button"
            onClick={() => onOpenSeekReference?.(reference)}
            className="inline-flex items-center gap-2 rounded-full border border-sky-300 bg-white/90 px-3 py-1.5 text-xs font-semibold text-sky-800 transition hover:border-sky-400 hover:bg-sky-100 dark:border-sky-700 dark:bg-sky-950/50 dark:text-sky-200 dark:hover:border-sky-600 dark:hover:bg-sky-900/50"
          >
            <PlayCircle size={14} />
            跳到视频定位
          </button>
        </div>
      </div>
    </details>
  );
}

function WorkspaceThoughtTraceMessage({ message }) {
  const isRunning = message.thoughtTrace?.status === "running";
  const durationLabel = formatDurationLabel(message.thoughtTrace?.durationMs);
  const summary = typeof message.thoughtTrace?.summary === "string" ? message.thoughtTrace.summary : "";
  const stages = Array.isArray(message.thoughtTrace?.stages) ? message.thoughtTrace.stages : [];
  const hasStages = stages.length > 0;
  const displaySummary = summary || (isRunning ? "正在思考中..." : "本轮未返回思路摘要。");

  if (hasStages) {
    return (
      <div className="rounded-[1.35rem] border border-stone-200/80 bg-white/90 shadow-sm dark:border-stone-800 dark:bg-[#151516]">
        <div className="px-4 py-3.5">
          <div className="flex items-center gap-3 text-stone-700 dark:text-stone-200">
            <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-2xl bg-sky-50 text-sky-700 dark:bg-sky-950/30 dark:text-sky-300">
              {isRunning ? <LoaderCircle size={16} className="animate-spin" /> : <BrainCircuit size={16} />}
            </div>
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-center gap-2">
                <strong className="text-[15px] font-semibold">{message.content}</strong>
                {durationLabel ? (
                  <span className="inline-flex items-center gap-1 rounded-full bg-stone-100 px-2 py-0.5 text-[11px] font-medium text-stone-500 dark:bg-stone-800 dark:text-stone-400">
                    <Clock3 size={12} />
                    用时 {durationLabel}
                  </span>
                ) : null}
              </div>
              <p className="mt-1 text-xs text-stone-500 dark:text-stone-400">
                {isRunning ? "当前按图节点顺序执行中" : "本轮图节点执行已完成"}
              </p>
            </div>
          </div>
        </div>

        <div className="border-t border-stone-200/80 px-4 py-4 dark:border-stone-800">
          <div className="flex flex-col gap-3">
            <AnimatePresence initial={false}>
              {stages.map((stage) => {
                const stageRunning = stage.status === "running";
                const stageDurationLabel = formatDurationLabel(stage.durationMs);
                return (
                  <motion.div
                    key={stage.id}
                    initial={{ opacity: 0, y: 8 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, y: -4 }}
                    transition={{ duration: 0.18, ease: "easeOut" }}
                    className="rounded-2xl border border-stone-200/70 bg-stone-50/80 px-3.5 py-3 dark:border-stone-800 dark:bg-stone-900/70"
                  >
                    <div className="flex items-center justify-between gap-3">
                      <div className="flex min-w-0 items-center gap-3">
                        <div className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-2xl ${
                          stageRunning
                            ? "bg-sky-100 text-sky-700 dark:bg-sky-950/40 dark:text-sky-300"
                            : "bg-emerald-100 text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-300"
                        }`}>
                          {stageRunning ? <LoaderCircle size={15} className="animate-spin" /> : <CheckCircle2 size={15} />}
                        </div>
                        <div className="min-w-0">
                          <div className="text-sm font-semibold text-stone-800 dark:text-stone-100">{stage.label}</div>
                          <div className="mt-0.5 text-xs text-stone-500 dark:text-stone-400">{stage.nodeId}</div>
                        </div>
                      </div>
                      <div className="flex shrink-0 items-center gap-2">
                        <span className={`rounded-full px-2 py-0.5 text-[11px] font-medium ${
                          stageRunning
                            ? "bg-sky-100 text-sky-700 dark:bg-sky-950/40 dark:text-sky-300"
                            : "bg-emerald-100 text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-300"
                        }`}>
                          {stageRunning ? "执行中" : "已完成"}
                        </span>
                        {stageDurationLabel ? (
                          <span className="text-xs text-stone-400 dark:text-stone-500">用时 {stageDurationLabel}</span>
                        ) : null}
                      </div>
                    </div>
                  </motion.div>
                );
              })}
            </AnimatePresence>
          </div>
        </div>
      </div>
    );
  }

  return (
    <details open={isRunning} className="group rounded-[1.35rem] border border-stone-200/80 bg-white/90 shadow-sm dark:border-stone-800 dark:bg-[#151516]">
      <summary className="list-none cursor-pointer px-4 py-3.5">
        <div className="flex items-center gap-3 text-stone-700 dark:text-stone-200">
          <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-2xl bg-sky-50 text-sky-700 dark:bg-sky-950/30 dark:text-sky-300">
            {isRunning ? <LoaderCircle size={16} className="animate-spin" /> : <BrainCircuit size={16} />}
          </div>
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2">
              <strong className="text-[15px] font-semibold">{message.content}</strong>
              {durationLabel ? (
                <span className="inline-flex items-center gap-1 rounded-full bg-stone-100 px-2 py-0.5 text-[11px] font-medium text-stone-500 dark:bg-stone-800 dark:text-stone-400">
                  <Clock3 size={12} />
                  用时 {durationLabel}
                </span>
              ) : null}
            </div>
            <p className="mt-1 text-xs text-stone-500 dark:text-stone-400">
              {isRunning ? "正在分析当前问题与上下文，思路会实时展开" : "展开查看本轮对问题的思路摘要"}
            </p>
          </div>
          <ChevronRight size={18} className="shrink-0 text-stone-400 transition-transform group-open:rotate-90" />
        </div>
      </summary>

      <div className="border-t border-stone-200/80 px-4 py-3 text-sm leading-6 text-stone-600 dark:border-stone-800 dark:text-stone-300">
        {displaySummary}
      </div>
    </details>
  );
}

function shouldShowDuration(durationMs) {
  return typeof durationMs === "number" && durationMs > 0;
}

function formatDurationLabel(durationMs) {
  if (typeof durationMs !== "number" || Number.isNaN(durationMs) || durationMs < 0) {
    return "";
  }
  if (durationMs < 1000) {
    return `${durationMs}ms`;
  }
  return `${(durationMs / 1000).toFixed(1)}秒`;
}

function formatTokenCount(value) {
  if (typeof value !== "number" || Number.isNaN(value) || value < 0) {
    return "0";
  }
  if (value >= 1000) {
    return `${(value / 1000).toFixed(1)}k`;
  }
  return `${Math.round(value)}`;
}

function resolveUsageToneClass(level) {
  if (level === "blocking") {
    return "bg-red-100 text-red-700 dark:bg-red-950/40 dark:text-red-300";
  }
  if (level === "compact") {
    return "bg-amber-100 text-amber-700 dark:bg-amber-950/40 dark:text-amber-300";
  }
  if (level === "warning") {
    return "bg-orange-100 text-orange-700 dark:bg-orange-950/40 dark:text-orange-300";
  }
  return "bg-emerald-100 text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-300";
}

function resolveUsageBarClass(level) {
  if (level === "blocking") {
    return "bg-red-500";
  }
  if (level === "compact") {
    return "bg-amber-500";
  }
  if (level === "warning") {
    return "bg-orange-500";
  }
  return "bg-emerald-500";
}
