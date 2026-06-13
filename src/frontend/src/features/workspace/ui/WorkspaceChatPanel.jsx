import { lazy, Suspense, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { Sparkles, ArrowUp, LoaderCircle, ChevronRight, Wrench, Clock3, BrainCircuit, CheckCircle2, FileText, PlayCircle, Copy } from "lucide-react";
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
  ragModels = [],
  knowledgeMemorySnapshot = null,
  onSelectChatSession,
  onOpenSeekReference,
  onOpenSettings,
  onSubmitChat,
}) {
  const [draft, setDraft] = useState("");
  const [copiedMessageId, setCopiedMessageId] = useState(null);
  const scopeLabel = selectedContextType === "series"
    ? activeSeries?.title ?? "当前系列"
    : selectedVideo?.title ?? activeSeries?.title ?? workspaceTitle ?? "当前视频";
  const currentPageLabel = describeCurrentTool(selectedToolId);
  const overviewGenerated =
    tools?.overview?.generated === true ||
    selectedVideo?.processed === true;
  const overviewMissing =
    tools?.overview?.generated === false ||
    selectedVideo?.processed === false;
  const chatLocked =
    selectedContextType === "video" &&
    selectedVideo != null &&
    overviewMissing &&
    !overviewGenerated;
  const embeddingModel = ragModels.find((model) => model.key === "embedding") ?? null;
  const seriesRagLocked = selectedContextType === "series" && embeddingModel != null && !embeddingModel.downloaded;
  const seriesIndexingLocked =
    selectedContextType === "series" &&
    knowledgeMemorySnapshot?.status === "running";
  const interactionDisabled = chatPending || chatLocked || seriesRagLocked || seriesIndexingLocked;
  const lockedContentClass = chatLocked || seriesRagLocked || seriesIndexingLocked ? "pointer-events-none select-none blur-[2px] opacity-60" : "";
  const suggestedPrompts = [
    { title: "总结核心结论", desc: "给我总结一下这个视频的核心结论", icon: Sparkles },
    { title: "记录重点知识", desc: "帮我记一下这个视频的重点", icon: FileText },
    { title: "提取系列主题", desc: "这个系列主要讲了哪些主题？", icon: BrainCircuit },
    { title: "时间轴定位", desc: "某个知识点在视频里的什么时间出现？", icon: Clock3 },
  ];

  function handleSubmit() {
    const trimmed = draft.trim();
    if (!trimmed || interactionDisabled) {
      return;
    }
    onSubmitChat(trimmed);
    setDraft("");
  }

  async function handleCopyMessage(message) {
    if (typeof message.content !== "string" || !message.content.trim()) {
      return;
    }
    await copyText(message.content);
    setCopiedMessageId(message.id);
    window.setTimeout(() => {
      setCopiedMessageId((currentId) => currentId === message.id ? null : currentId);
    }, 1600);
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
        <WorkspaceMarkdownMessage content={message.content} citations={message.citations} />
      </Suspense>
    );
  }

  return (
    <div className="h-full w-full flex flex-col bg-transparent">
      {/* Header */}
      <div className="workspace-toolbar-surface shrink-0 flex items-center justify-between px-6 py-4 border-b border-stone-200/80 dark:border-stone-800">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-2xl bg-accent/10 dark:bg-accent/10 flex items-center justify-center border border-accent/20 dark:border-accent/20">
            <Sparkles size={16} className="text-accent" />
          </div>
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <h3 className="text-base font-bold text-stone-800 dark:text-stone-100">分析助手</h3>
              <span className="rounded-full border border-stone-200/80 bg-stone-50 px-2.5 py-0.5 text-[11px] font-semibold text-stone-600 dark:border-stone-700 dark:bg-stone-900 dark:text-stone-300">
                {currentPageLabel}
              </span>
            </div>
            <p className="text-xs text-stone-500 dark:text-stone-400">基于《{scopeLabel}》</p>
          </div>
        </div>
        <WorkspaceContextUsageInline usage={contextUsage} loading={contextUsageLoading} />
      </div>


      {chatLocked ? (
        <div className="border-b border-warning/30 bg-warning-subtle px-6 py-3 text-sm text-stone-800 dark:text-stone-100">
          <div className="font-semibold">请先生成 AI 概况后再开始对话</div>
          <p className="mt-1 text-xs text-stone-600 dark:text-stone-300">
            当前视频还没有完成概况处理。先生成 AI 概况，才能基于内容回答问题。
          </p>
        </div>
      ) : null}

      {seriesRagLocked ? (
        <div className="border-b border-amber-200/80 bg-amber-50/90 px-6 py-3 text-sm text-amber-900 dark:border-amber-900/60 dark:bg-amber-950/20 dark:text-amber-100">
          <div className="font-semibold">请先下载 RAG 向量模型</div>
          <div className="mt-2 flex items-center justify-between gap-3">
            <p className="text-xs leading-5 text-amber-800 dark:text-amber-200">
              series依赖rag数据库能力，请先下载相关模型。
            </p>
            <button
              type="button"
              onClick={onOpenSettings}
              className="shrink-0 rounded-xl bg-amber-900 px-3 py-1.5 text-xs font-bold text-white transition hover:bg-amber-950 dark:bg-amber-200 dark:text-amber-950 dark:hover:bg-amber-100"
            >
              去设置下载
            </button>
          </div>
        </div>
      ) : null}

      {seriesIndexingLocked ? (
        <div className="border-b border-blue-200/80 bg-blue-50/90 px-6 py-3 text-sm text-blue-900 dark:border-blue-900/60 dark:bg-blue-950/20 dark:text-blue-100">
          <div className="flex items-center gap-2 font-semibold">
            <LoaderCircle size={15} className="animate-spin" />
            数据库正在整理
          </div>
          <p className="mt-1 text-xs leading-5 text-blue-800 dark:text-blue-200">
            正在重建 RAG 索引，series 问答会在整理完成后恢复。
          </p>
        </div>
      ) : null}



      {/* Chat History Area */}
      <div
        className={`flex-1 overflow-auto p-6 md:p-8 flex flex-col gap-6 transition ${lockedContentClass}`}
      >
        {chatMessages.length === 0 ? (
          <div className="flex-1 flex flex-col items-center justify-center py-10 px-4 mt-8">
            <div className="w-16 h-16 rounded-full bg-accent/10 flex items-center justify-center mb-6 border border-accent/20 shadow-sm">
              <Sparkles size={28} className="text-accent" />
            </div>
            <h2 className="text-xl font-bold text-stone-800 dark:text-stone-100 mb-2">有什么我可以帮您的？</h2>
            <p className="text-sm text-stone-500 dark:text-stone-400 mb-10 max-w-md text-center">您可以直接提问，或者尝试以下快速指令来探索当前上下文。</p>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-3 w-full max-w-2xl">
              {suggestedPrompts.map((prompt, idx) => {
                const Icon = prompt.icon;
                return (
                  <button
                    key={idx}
                    type="button"
                    onClick={() => setDraft(prompt.desc)}
                    disabled={chatLocked || seriesRagLocked || seriesIndexingLocked}
                    className="group flex flex-col items-start gap-2 rounded-2xl border border-stone-200/80 bg-white/60 p-4 text-left transition-all hover:border-accent/40 hover:bg-accent/5 hover:shadow-md disabled:cursor-not-allowed disabled:opacity-50 dark:border-white/5 dark:bg-white/5 dark:hover:border-accent/30 dark:hover:bg-accent/10"
                  >
                    <div className="flex items-center gap-2 text-sm font-bold text-stone-700 dark:text-stone-200 group-hover:text-accent transition-colors">
                      <Icon size={16} />
                      {prompt.title}
                    </div>
                    <div className="text-xs text-stone-500 dark:text-stone-400 font-medium leading-relaxed">
                      {prompt.desc}
                    </div>
                  </button>
                );
              })}
            </div>
          </div>
        ) : null}

        {chatMessages.map((message) => {
          const isAssistant = message.role === "assistant";
          const canCopy = message.kind == null && typeof message.content === "string" && message.content.trim();
          const isCopied = copiedMessageId === message.id;
          return (
            <div
              key={message.id}
              className={`flex items-start gap-4 max-w-2xl ${isAssistant ? "" : "self-end justify-end"}`}
            >
              {isAssistant ? (
                <div className="w-8 h-8 rounded-2xl bg-accent flex items-center justify-center shrink-0 shadow-sm mt-1">
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
                        : "px-5 py-3 rounded-[1.5rem] rounded-tr-sm bg-accent border border-accent/80 text-white shadow-sm"
                  }
                >
                  {renderMessageContent(message, isAssistant)}
                </div>
                <div className={`flex items-center gap-2 text-xs text-stone-400 dark:text-stone-500 ${isAssistant ? "ml-1" : ""}`}>
                  <span>{message.meta}</span>
                  {canCopy ? (
                    <button
                      type="button"
                      onClick={() => handleCopyMessage(message)}
                      className="inline-flex items-center gap-1 rounded-full px-2 py-0.5 font-medium text-stone-400 transition hover:bg-stone-100 hover:text-stone-700 dark:text-stone-500 dark:hover:bg-stone-800 dark:hover:text-stone-200"
                    >
                      <Copy size={12} />
                      {isCopied ? "已复制" : "复制"}
                    </button>
                  ) : null}
                </div>
              </div>
            </div>
          );
        })}

        {chatPending && chatMessages.every((message) => message.kind == null) ? (
          <div className="flex items-start gap-4 max-w-2xl">
            <div className="w-8 h-8 rounded-2xl bg-accent flex items-center justify-center shrink-0 shadow-sm mt-1">
              <LoaderCircle size={16} className="animate-spin text-white" />
            </div>
            <div className="workspace-elevated-panel p-4 rounded-[1.5rem] rounded-tl-sm border text-stone-600 dark:text-stone-300">
              正在思考当前工具和上下文...
            </div>
          </div>
        ) : null}
      </div>

      {/* Floating Composer Area */}
      <div
        className={`shrink-0 p-4 md:px-6 md:pb-6 md:pt-2 bg-transparent transition-all ${lockedContentClass}`}
      >
        <div className="max-w-4xl mx-auto relative rounded-3xl bg-white/90 dark:bg-[#1a1a1a]/90 backdrop-blur-xl border border-stone-200/80 dark:border-white/10 shadow-[0_8px_30px_rgb(0,0,0,0.04)] dark:shadow-[0_8px_30px_rgb(0,0,0,0.2)] focus-within:border-accent/50 focus-within:ring-4 focus-within:ring-accent/10 transition-all group overflow-hidden">
          <textarea
            placeholder={
              chatLocked
                ? "请先生成 AI 概况..."
                : seriesRagLocked
                  ? "请先下载 RAG 向量模型..."
                  : seriesIndexingLocked
                    ? "数据库整理完成后可继续提问..."
                    : "向 AI 助手提问或下达指令..."
            }
            className="w-full bg-transparent resize-none py-5 pl-6 pr-16 text-[15px] text-stone-800 dark:text-stone-100 outline-none leading-relaxed h-[100px] placeholder:text-stone-400 dark:placeholder:text-stone-500"
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter" && !event.shiftKey) {
                event.preventDefault();
                handleSubmit();
              }
            }}
            disabled={interactionDisabled}
          />
          <div className="absolute right-3 bottom-3">
            <button
              type="button"
              onClick={handleSubmit}
              disabled={interactionDisabled || !draft.trim()}
              className="flex items-center justify-center w-10 h-10 rounded-[14px] bg-stone-900 dark:bg-white text-white dark:text-black hover:bg-accent hover:text-white dark:hover:bg-accent transition-all shadow-sm disabled:opacity-50 disabled:cursor-not-allowed group-focus-within:bg-accent group-focus-within:text-white"
            >
              {chatPending ? <LoaderCircle size={18} className="animate-spin" /> : <ArrowUp size={20} strokeWidth={2.5} />}
            </button>
          </div>
        </div>
        <div className="flex items-center justify-center gap-2 mt-4 opacity-70">
          <Sparkles size={12} className="text-stone-400 dark:text-stone-500" />
          <p className="text-xs font-medium text-stone-400 dark:text-stone-500">
            {chatLocked
              ? "概况生成完成后，这里会恢复正常提问"
              : seriesRagLocked
                ? "RAG 向量模型下载完成后，这里会恢复 series 问答"
                : seriesIndexingLocked
                  ? "数据库整理完成后，这里会恢复 series 问答"
                : "AI 已接入当前工作区上下文，可返回证据卡片与工具联动动作"}
          </p>
        </div>
      </div>
    </div>
  );
}

async function copyText(text) {
  if (navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(text);
    return;
  }
  const textarea = document.createElement("textarea");
  textarea.value = text;
  textarea.setAttribute("readonly", "");
  textarea.style.position = "fixed";
  textarea.style.left = "-9999px";
  document.body.appendChild(textarea);
  textarea.select();
  document.execCommand("copy");
  document.body.removeChild(textarea);
}

function AssistantMessageFallback({ content }) {
  return <div className="whitespace-pre-wrap break-words">{content}</div>;
}

function WorkspaceContextUsageInline({ usage, loading }) {
  if ((loading && !usage) || !usage) {
    return null;
  }

  const thresholdLabel = usage.level === "blocking"
    ? "已超过阻塞阈值"
    : usage.level === "compact"
      ? "压缩区间"
      : usage.level === "warning"
        ? "接近阈值"
        : "预算充足";
  const usageLabel = `${formatTokenCount(usage.estimatedTotalTokens)} / ${formatTokenCount(usage.windowTokens)}`;

  return (
    <div className="relative group">
      <div className={`inline-flex shrink-0 items-center gap-1.5 whitespace-nowrap rounded-full px-2.5 py-1 text-[11px] font-semibold cursor-default transition-colors ${resolveUsageToneClass(usage.level)}`}>
        {thresholdLabel}
        <span className="opacity-60">{usage.usagePercent.toFixed(1)}%</span>
      </div>
      <div className="absolute right-0 top-full mt-2 z-50 invisible opacity-0 group-hover:visible group-hover:opacity-100 transition-all duration-150 w-72">
        <div className="rounded-2xl border border-stone-200/80 bg-white/95 p-4 shadow-xl backdrop-blur-lg dark:border-stone-700 dark:bg-stone-900/95">
          <div className="flex items-center justify-between mb-2">
            <strong className="text-xs font-semibold text-stone-700 dark:text-stone-200">上下文预算</strong>
            <span className="text-xs text-stone-500 dark:text-stone-400">剩余 {formatTokenCount(usage.remainingTokens)}</span>
          </div>
          <p className="text-[11px] text-stone-500 dark:text-stone-400 mb-3">
            已估算 {usageLabel}，保留输出 {formatTokenCount(usage.reservedOutputTokens)}
          </p>
          <div className="h-1.5 overflow-hidden rounded-full bg-stone-200/80 dark:bg-stone-800 mb-3">
            <div
              className={`h-full rounded-full transition-all ${resolveUsageBarClass(usage.level)}`}
              style={{ width: `${Math.max(4, Math.min(100, usage.usagePercent))}%` }}
            />
          </div>
          <div className="flex flex-wrap gap-1.5">
            {usage.sources.map((source) => (
              <span
                key={source.id}
                className="rounded-full border border-stone-200/80 bg-stone-50 px-2 py-0.5 text-[10px] font-medium text-stone-600 dark:border-stone-700 dark:bg-stone-800 dark:text-stone-300"
              >
                {source.label} {formatTokenCount(source.estimatedTokens)}
              </span>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

function WorkspaceToolTraceMessage({ message }) {
  const steps = Array.isArray(message.toolTrace?.steps) ? message.toolTrace.steps : [];
  const durationLabel = formatDurationLabel(message.toolTrace?.durationMs);
  const isRunning = message.toolTrace?.status === "running";
  const isIdle = message.toolTrace?.status === "idle";
  const isFailed = message.toolTrace?.status === "failed";

  return (
    <details className="group rounded-[1.35rem] border border-stone-200/80 bg-white/90 shadow-sm dark:border-stone-800 dark:bg-neutral-900">
      <summary className="list-none cursor-pointer px-4 py-3.5">
        <div className="flex items-center gap-3 text-stone-700 dark:text-stone-200">
          <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-2xl bg-warning-subtle text-warning">
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
                <span className="inline-flex items-center gap-1 rounded-full bg-warning-subtle px-2 py-0.5 text-[11px] font-medium text-warning">
                  <LoaderCircle size={12} className="animate-spin" />
                  调用中
                </span>
              ) : isFailed ? (
                <span className="inline-flex items-center gap-1 rounded-full bg-danger-subtle px-2 py-0.5 text-[11px] font-medium text-danger">
                  失败
                </span>
              ) : null}
            </div>
            <p className="mt-1 text-xs text-stone-500 dark:text-stone-400">
              {isRunning
                ? "工具正在执行中"
                : isFailed
                  ? "工具调用过程中发生错误"
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
                <span className={`rounded-full px-2 py-0.5 text-[11px] font-medium ${step.status === "running"
                  ? "bg-warning-subtle text-warning"
                  : step.status === "failed"
                    ? "bg-danger-subtle text-danger"
                    : "bg-success-subtle text-success"
                  }`}>
                  {step.status === "running" ? "进行中" : step.status === "failed" ? "失败" : "已完成"}
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
    <details className="group rounded-[1.35rem] border border-info/20 bg-info-subtle shadow-sm dark:border-info/10 dark:bg-info-subtle">
      <summary className="list-none cursor-pointer px-4 py-3.5">
        <div className="flex items-center gap-3 text-stone-800 dark:text-stone-100">
          <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-2xl bg-white/80 text-accent dark:bg-accent/10 dark:text-accent">
            <FileText size={16} />
          </div>
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2">
              <strong className="text-[15px] font-semibold">{title}</strong>
            </div>
            <p className="mt-1 text-xs text-stone-500 dark:text-stone-400">
              展开查看命中的转写片段，再决定是否跳到视频。
            </p>
          </div>
          <ChevronRight size={18} className="shrink-0 text-stone-400 transition-transform group-open:rotate-90" />
        </div>
      </summary>

      <div className="border-t border-info/20 px-4 py-4 dark:border-info/10">
        {reference.query ? (
          <p className="text-xs font-medium text-stone-500 dark:text-stone-400">
            检索问题：{reference.query}
          </p>
        ) : null}
        {reference.matchedText ? (
          <blockquote className="mt-3 rounded-2xl border border-stone-200/60 bg-white/80 px-4 py-3 text-sm leading-6 text-stone-800 dark:border-stone-700/60 dark:bg-stone-900 dark:text-stone-100">
            {reference.matchedText}
          </blockquote>
        ) : (
          <p className="mt-3 text-sm text-stone-700 dark:text-stone-300">
            当前没有返回完整命中原文，但已经定位到对应时间点。
          </p>
        )}
        <div className="mt-4 flex flex-wrap gap-2">
          <button
            type="button"
            onClick={() => onOpenSeekReference?.(reference)}
            className="inline-flex items-center gap-2 rounded-full border border-accent/30 bg-white/90 px-3 py-1.5 text-xs font-semibold text-accent transition hover:border-accent/50 hover:bg-accent/5 dark:hover:bg-accent/10"
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
  const isFailed = message.thoughtTrace?.status === "failed";
  const durationLabel = formatDurationLabel(message.thoughtTrace?.durationMs);
  const summary = typeof message.thoughtTrace?.summary === "string" ? message.thoughtTrace.summary : "";
  const stages = Array.isArray(message.thoughtTrace?.stages) ? message.thoughtTrace.stages : [];
  const hasStages = stages.length > 0;
  const displaySummary = summary || (isRunning ? "正在思考中..." : "本轮未返回思路摘要。");

  if (hasStages) {
    return (
      <details className="group rounded-[1.35rem] border border-stone-200/80 bg-white/90 shadow-sm dark:border-stone-800 dark:bg-neutral-900">
        <summary className="list-none cursor-pointer px-4 py-3.5">
          <div className="flex items-center gap-3 text-stone-700 dark:text-stone-200">
            <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-2xl bg-accent/10 text-accent">
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
                {isRunning ? "当前按图节点顺序执行中" : isFailed ? "本轮图节点执行失败" : "本轮图节点执行已完成"}
              </p>
            </div>
            <ChevronRight size={18} className="shrink-0 text-stone-400 transition-transform group-open:rotate-90" />
          </div>
        </summary>

        <div className="border-t border-stone-200/80 px-4 py-4 dark:border-stone-800">
          <div className="flex flex-col gap-3">
            <AnimatePresence initial={false}>
              {stages.map((stage) => {
                const stageRunning = stage.status === "running";
                const stageFailed = stage.status === "failed";
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
                        <div className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-2xl ${stageRunning
                          ? "bg-info-subtle text-info"
                          : stageFailed
                            ? "bg-danger-subtle text-danger"
                            : "bg-success-subtle text-success"
                          }`}>
                          {stageRunning ? <LoaderCircle size={15} className="animate-spin" /> : <CheckCircle2 size={15} />}
                        </div>
                        <div className="min-w-0">
                          <div className="text-sm font-semibold text-stone-800 dark:text-stone-100">{stage.label}</div>
                          <div className="mt-0.5 text-xs text-stone-500 dark:text-stone-400">{stage.nodeId}</div>
                        </div>
                      </div>
                      <div className="flex shrink-0 items-center gap-2">
                        <span className={`rounded-full px-2 py-0.5 text-[11px] font-medium ${stageRunning
                          ? "bg-info-subtle text-info"
                          : stageFailed
                            ? "bg-danger-subtle text-danger"
                            : "bg-success-subtle text-success"
                          }`}>
                          {stageRunning ? "执行中" : stageFailed ? "失败" : "已完成"}
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
      </details>
    );
  }

  return (
    <details className="group rounded-[1.35rem] border border-stone-200/80 bg-white/90 shadow-sm dark:border-stone-800 dark:bg-neutral-900">
      <summary className="list-none cursor-pointer px-4 py-3.5">
        <div className="flex items-center gap-3 text-stone-700 dark:text-stone-200">
          <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-2xl bg-accent/10 text-accent">
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
              {isRunning ? "正在分析当前问题与上下文，思路会实时展开" : isFailed ? "本轮思路执行失败，展开查看错误摘要" : "展开查看本轮对问题的思路摘要"}
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
    return "bg-danger-subtle text-danger";
  }
  if (level === "compact") {
    return "bg-warning-subtle text-warning";
  }
  if (level === "warning") {
    return "bg-warning-subtle text-warning-muted";
  }
  return "bg-success-subtle text-success";
}

function resolveUsageBarClass(level) {
  if (level === "blocking") {
    return "bg-danger-muted";
  }
  if (level === "compact") {
    return "bg-warning-muted";
  }
  if (level === "warning") {
    return "bg-warning";
  }
  return "bg-success-muted";
}
