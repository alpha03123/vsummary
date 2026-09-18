import { lazy, Suspense, useEffect, useMemo, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { Sparkles, ArrowUp, LoaderCircle, Square, ChevronRight, Wrench, Clock3, BrainCircuit, CheckCircle2, FileText, PlayCircle, Plus, MessagesSquare } from "lucide-react";
import { formatRange } from "../../../shared/lib/time";

import { CopyToClipboardButton } from "./shared/CopyToClipboardButton";
import { WorkspaceProviderSelect } from "./shared/WorkspaceSettingsControls";

const WorkspaceMarkdownMessage = lazy(() =>
  import("./shared/WorkspaceMarkdownMessage").then((module) => ({
    default: module.WorkspaceMarkdownMessage,
  })),
);

export function WorkspaceChatPanel({
  workspaceTitle,
  activeSeries,
  selectedVideo,
  selectedContextType,
  chatMessages = [],
  chatSessions = [],
  activeSessionId = null,
  chatPending = false,
  contextUsage = null,
  contextUsageLoading = false,
  ragModels = [],
  knowledgeMemorySnapshot = null,
  draft = "",
  onDraftChange,
  onSelectChatSession,
  onStartNewChat,
  onOpenSeekReference,
  onOpenCitationReference,
  onOpenSettings,
  onSubmitChat,
  onCancelChat,
  summaryLocked = false,
}) {
  const [fallbackDraft, setFallbackDraft] = useState("");
  const currentDraft = onDraftChange ? draft : fallbackDraft;
  const updateDraft = onDraftChange ?? setFallbackDraft;
  const chatHistoryRef = useRef(null);
  const composerRef = useRef(null);
  const threadRef = useRef(null);
  const bottomAlignedSessionRef = useRef(null);
  const visibleSessionRef = useRef(null);
  const embeddingModel = ragModels.find((model) => model.key === "embedding") ?? null;
  const seriesRagLocked = selectedContextType === "series" && embeddingModel != null && !embeddingModel.downloaded;
  const seriesIndexingLocked =
    selectedContextType === "series" &&
    knowledgeMemorySnapshot?.status === "running";
  const interactionDisabled = chatPending || summaryLocked || seriesRagLocked || seriesIndexingLocked;
  // Only surfaced while the composer is blocked — each of these tells the user
  // what to fix. Null in the normal idle state so the row is not rendered.
  const composerHint = summaryLocked
    ? "生成 AI 概况后，这里会恢复对话"
    : seriesRagLocked
      ? "RAG 向量模型下载完成后，这里会恢复 series 问答"
      : seriesIndexingLocked
        ? "数据库整理完成后，这里会恢复 series 问答"
        : null;
  const lockedContentClass = summaryLocked || seriesRagLocked || seriesIndexingLocked ? "pointer-events-none select-none blur-[2px] opacity-60" : "";
  const conversationTurns = useMemo(
    () => chatMessages
      .filter((message) => message.role === "user" && message.kind == null && typeof message.content === "string" && message.content.trim())
      .map((message) => ({ id: message.id, prompt: message.content.trim() })),
    [chatMessages],
  );
  const chatSessionOptions = useMemo(
    () => chatSessions.map((session) => ({ id: session.id, label: session.title || "新话题" })),
    [chatSessions],
  );
  const suggestedPrompts = [
    { title: "总结核心结论", desc: "给我总结一下这个视频的核心结论", icon: Sparkles },
    { title: "记录重点知识", desc: "帮我记一下这个视频的重点", icon: FileText },
    { title: "提取系列主题", desc: "这个系列主要讲了哪些主题？", icon: BrainCircuit },
    { title: "时间轴定位", desc: "某个知识点在视频里的什么时间出现？", icon: Clock3 },
  ];

  useEffect(() => {
    if (!activeSessionId) {
      return undefined;
    }
    if (visibleSessionRef.current !== activeSessionId) {
      visibleSessionRef.current = activeSessionId;
      bottomAlignedSessionRef.current = null;
    }
    if (chatMessages.length === 0 || bottomAlignedSessionRef.current === activeSessionId) {
      return undefined;
    }

    const frameId = window.requestAnimationFrame(() => {
      const chatHistory = chatHistoryRef.current;
      if (!chatHistory) {
        return;
      }
      chatHistory.scrollTop = chatHistory.scrollHeight;
      bottomAlignedSessionRef.current = activeSessionId;
    });
    return () => window.cancelAnimationFrame(frameId);
  }, [activeSessionId, chatMessages.length]);

  // Grow the composer with its content instead of reserving a fixed block.
  // A tall fixed height wasted ~48px of chat space whenever the box was empty,
  // which is the common case. Height is reset to "auto" first so the box can
  // also shrink back down when the draft is shortened or cleared.
  useEffect(() => {
    const composer = composerRef.current;
    if (!composer) {
      return;
    }
    composer.style.height = "auto";
    const nextHeight = composer.scrollHeight;
    composer.style.height = `${nextHeight}px`;
    // Only allow a scrollbar once the box is pinned at its max height, so an
    // empty or single-line draft never shows a scrollbar track.
    const maxHeight = parseFloat(window.getComputedStyle(composer).maxHeight);
    const capped = Number.isFinite(maxHeight) && nextHeight > maxHeight;
    composer.style.overflowY = capped ? "auto" : "hidden";
  }, [currentDraft]);

  function handleSubmit() {
    const trimmed = currentDraft.trim();
    if (!trimmed || interactionDisabled) {
      return;
    }
    onSubmitChat(trimmed);
    updateDraft("");
  }

  function jumpToConversationTurn(messageId) {
    const target = document.getElementById(`chat-message-${messageId}`);
    target?.scrollIntoView?.({ behavior: "smooth", block: "start" });
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
        <WorkspaceMarkdownMessage
          content={message.content}
          citations={message.citations}
          onOpenCitationReference={onOpenCitationReference}
        />
      </Suspense>
    );
  }

  return (
    <div className="@container h-full w-full flex flex-col bg-transparent">
      {/* Header. Two lines were deleted here, both for the same reason — they
          restated information the user can already see elsewhere:

          1. The tool-name badge (`工具首页` / `AI概况` / …). It implied the
             assistant knows which tool page you are on, but the panel-local
             tool choice is intentionally not part of Agent 对话上下文。工具页
             本身已经在自己的标题中展示名称，因此这层 badge 只会重复信息。

          2. The `基于《…》` subtitle. The left rail lists the active series and
             video with full titles; this line repeated the video title and then
             truncated it, so the only thing it ever added was a clipped string.

          The identity column is now a single title. */}
      {/* Padding is symmetric to the composer's, so the inner content sits the
          same distance from the panel's top edge as the composer sits from its
          bottom edge. The header is the outer edge of the card, so it needs the
          *larger* share: this previously ran `pt-3.5 pb-5` (14/20), which put
          the title 28px from the top while leaving the composer 44px from the
          bottom — the bottom gap was more than half again the top and the whole
          panel read as sinking. */}
      {/*
        窄面板（320px 可达）下头部需要换策略，而不是继续挤。

        `flex-wrap` 单独用是不够的：它只保证「放不下就换行」，但不保证换到哪。
        实测宽度不足时，右侧「当前对话」切换器会跟左侧的预算胶囊撞进同一视觉行，
        看起来就是两坨东西糊在一起 —— 比不换行还糟。

        所以这里改成真正的两段式：
          - 窄面板：`flex-col`，左列（胶囊 + 返回）和右列（切换器）各占满一行，互不重叠
          - 宽面板（@[440px] 起）：恢复 `flex-row justify-between` 的左右并排

        切换点取 440px —— 这是按各部件实测宽度算出来的，不是拍的：
          左列 = 图标 36 + gap 12 + max(预算胶囊 94, 返回按钮 90) = 142px
          右列 = 切换器 w-40 (160) + 新建按钮 40 + 边框 1        = 201px
          加上 gap-x-3 (12) 和宽面板内边距 px-6*2 (48)           = 403px
        也就是并排至少要 ~403px 才不挤，取 440px 留约 37px 余量。
        （早先取 520px 过于保守，面板还宽着就提前换行了。） */}
      <div className="workspace-toolbar-surface relative z-30 shrink-0 flex flex-col gap-2.5 px-4 pb-3.5 pt-3.5 border-b border-stone-200/80 dark:border-stone-800 @[440px]:flex-row @[440px]:items-center @[440px]:justify-between @[440px]:gap-x-3 @[440px]:px-5 @[440px]:pb-4 @[440px]:pt-4">
        <div className="flex min-w-0 items-center gap-3">
          <div className="w-9 h-9 shrink-0 rounded-2xl bg-accent/10 dark:bg-accent/10 flex items-center justify-center border border-accent/20 dark:border-accent/20">
            <Sparkles size={16} className="text-accent" />
          </div>
          {/* The budget pill sits above the back button rather than beside the
              switcher: it is passive status, so giving it its own line keeps it
              out of the control row's way, and it reads as a caption for the
              whole panel instead of a label for the switcher.

              The `分析助手` title that used to sit on the second row is gone.
              It restated what the panel already is — the drawer header above
              says `AI 对话`, the input below says `向 AI 助手提问…`, and the
              messages are visibly a conversation. Deleting it also removed the
              row's only flex child, so the back button no longer competes for
              width with a truncating title that carried no information. */}
          <div className="flex min-w-0 flex-col gap-0.5">
            <WorkspaceContextUsageInline usage={contextUsage} loading={contextUsageLoading} />
          </div>
        </div>
        {/* Right column: caption, then the switcher. The budget pill used to
            share the caption row; it now lives above the back button on the left,
            so this column is just the label plus the control it labels.

            窄面板下这一列 left-align 到自己的行上（原来是 items-end 靠右），
            因为它已经独占一行了，再靠右反而和上一行的胶囊错开。 */}
        <div className="flex shrink-0 flex-col items-start gap-1 @[440px]:items-end @[440px]:gap-1.5">
          {chatSessionOptions.length > 0 ? (
            <>
              {/* 「对话管理」只是给切换器加的说明标签，窄面板下没有它切换器依然自明，
                  优先让它消失以腾出横向空间。 */}
              <span className="hidden text-[10px] font-bold uppercase leading-none tracking-widest text-stone-400 dark:text-stone-500 @[440px]:block">
                对话管理
              </span>
              {/* Switcher + "new chat" share one bordered shell with an inset
                  divider so they read as a single unit. No `overflow-hidden` —
                  it would clip the switcher's absolutely positioned menu. */}
              <div className="inline-flex items-stretch rounded-xl border border-stone-200 bg-white transition-colors focus-within:border-accent/40 dark:border-stone-700 dark:bg-stone-900">
                <WorkspaceProviderSelect
                  value={activeSessionId}
                  options={chatSessionOptions}
                  onChange={onSelectChatSession}
                  ariaLabel="切换对话"
                  hideGroupLabels
                  align="end"
                  menuClassName="min-w-[14rem]"
                  className="w-40 rounded-l-xl @[440px]:w-48"
                  triggerVariant="bare"
                  leading={<MessagesSquare size={14} />}
                />
                {onStartNewChat ? (
                  <button
                    type="button"
                    onClick={onStartNewChat}
                    className="inline-flex w-10 shrink-0 items-center justify-center rounded-r-xl border-l border-stone-200 text-stone-500 transition-colors hover:bg-accent/10 hover:text-accent dark:border-stone-700 dark:text-stone-400"
                    title="新建话题"
                    aria-label="新建话题"
                  >
                    <Plus size={16} />
                  </button>
                ) : null}
              </div>
            </>
          ) : (
            <>
              {onStartNewChat ? (
                <button
                  type="button"
                  onClick={onStartNewChat}
                  className="inline-flex h-9 items-center gap-1.5 rounded-xl border border-stone-200 bg-white px-3 text-sm font-medium text-stone-600 transition-colors hover:border-accent/50 hover:text-accent dark:border-stone-700 dark:bg-stone-900 dark:text-stone-300"
                  title="新建话题"
                >
                  <Plus size={16} />
                  新对话
                </button>
              ) : null}
            </>
          )}
        </div>
      </div>

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

      {summaryLocked ? (
        <div className="border-b border-red-200/80 bg-red-50/90 px-6 py-3 text-sm text-red-800 dark:border-red-900/60 dark:bg-red-950/20 dark:text-red-200" role="alert">
          <div className="font-semibold">尚未生成 AI 概况</div>
          <p className="mt-1 text-xs leading-5">请先生成当前范围的 AI 概况，再开始对话。</p>
        </div>
      ) : null}

      {seriesIndexingLocked ? (
        <div className="border-b border-blue-200/80 bg-blue-50/90 px-6 py-3 text-sm text-blue-900 dark:border-blue-900/60 dark:bg-blue-950/20 dark:text-blue-100">
          <div className="flex items-center gap-2 font-semibold">
            <LoaderCircle size={15} className="animate-spin" />
            知识库正在构建
          </div>
          <p className="mt-1 text-xs leading-5 text-blue-800 dark:text-blue-200">
            正在扫描视频并建立关联索引，系列问答将在构建完成后恢复。
          </p>
        </div>
      ) : null}



      {/* Chat History Area.
          The thread sits in a centered column whose width matches the composer
          (`max-w-4xl`), so the two zones line up. Earlier the scroll container
          used an asymmetric `pl-14 md:pl-16` to clear the jump rail parked at
          `left-2`; that produced a 56px left gutter against a 32px right one and
          the whole thread read as shifted off-centre. The rail is now anchored to
          this container instead, and vertical space was freed at the top (the
          header lost a line) to offset the gutter it needs. */}
      <div className={`relative z-0 min-h-0 flex-1 transition ${lockedContentClass}`}>
        <div ref={chatHistoryRef} className="h-full overflow-auto px-4 py-4 @[440px]:px-6 @[440px]:py-5 md:@[440px]:px-8">
          <div ref={threadRef} className="mx-auto flex w-full max-w-4xl flex-col gap-4 @[440px]:gap-6">
            {chatMessages.length === 0 ? (
              <div className="flex-1 flex flex-col items-center justify-center py-10 px-4 mt-8">
            <div className="w-16 h-16 rounded-full bg-accent/10 flex items-center justify-center mb-6 border border-accent/20 shadow-sm">
              <Sparkles size={28} className="text-accent" />
            </div>
            <h2 className="text-xl font-bold text-stone-800 dark:text-stone-100 mb-2">有什么我可以帮您的？</h2>
            <p className="text-sm text-stone-600 dark:text-stone-400 mb-10 max-w-md text-center">您可以直接提问，或者尝试以下快速指令来探索当前上下文。</p>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-3 w-full max-w-2xl">
              {suggestedPrompts.map((prompt, idx) => {
                const Icon = prompt.icon;
                return (
                  <button
                    key={idx}
                    type="button"
                    onClick={() => updateDraft(prompt.desc)}
                    disabled={summaryLocked || seriesRagLocked || seriesIndexingLocked}
                    className="group flex flex-col items-start gap-2 rounded-2xl border border-stone-200/80 bg-white/60 p-4 text-left transition-all hover:border-accent/40 hover:bg-accent/5 hover:shadow-md disabled:cursor-not-allowed disabled:opacity-50 dark:border-white/5 dark:bg-white/5 dark:hover:border-accent/30 dark:hover:bg-accent/10"
                  >
                    <div className="flex items-center gap-2 text-sm font-bold text-stone-700 dark:text-stone-200 group-hover:text-accent transition-colors">
                      <Icon size={16} />
                      {prompt.title}
                    </div>
                    <div className="text-xs text-stone-600 dark:text-stone-400 font-medium leading-relaxed">
                      {prompt.desc}
                    </div>
                  </button>
                );
              })}
            </div>
          </div>
        ) : null}

            {chatMessages.map((message) => (
              <ConversationMessage
                key={message.id}
                message={message}
                renderMessageContent={renderMessageContent}
              />
            ))}

            {chatPending && chatMessages.every((message) => message.kind == null) ? (
              <div className="flex items-start gap-4 max-w-2xl">
                <div className="w-8 h-8 rounded-2xl bg-accent flex items-center justify-center shrink-0 shadow-sm mt-1">
                  <LoaderCircle size={16} className="animate-spin text-white" />
                </div>
                <div className="workspace-elevated-panel p-4 rounded-[1.5rem] rounded-tl-sm border text-stone-600 dark:text-stone-300">
                  正在分析您的问题...
                </div>
              </div>
            ) : null}
          </div>
        </div>
        <ConversationJumpRail turns={conversationTurns} onJump={jumpToConversationTurn} anchorRef={threadRef} />
      </div>

      {/* Floating Composer Area.
          Padding mirrors the header's asymmetry (`pt-3` / `pb-5`): the thread
          scrolls directly above, so a tight top gap keeps the last message
          visually attached to the composer, while the larger bottom gap gives
          the card room to sit inside the panel's rounded corner instead of
          hugging it. Header and composer now bracket the thread with the same
          optical rhythm. */}
      <div
        className={`shrink-0 p-3 @[440px]:p-4 md:@[440px]:px-6 md:@[440px]:pb-5 md:@[440px]:pt-3 bg-transparent transition-all ${lockedContentClass}`}
      >
        <div className="max-w-4xl mx-auto relative flex items-end rounded-3xl bg-white/90 dark:bg-[#1a1a1a]/90 backdrop-blur-xl border border-stone-200/80 dark:border-white/10 shadow-[0_8px_30px_rgb(0,0,0,0.04)] dark:shadow-[0_8px_30px_rgb(0,0,0,0.2)] focus-within:border-accent/50 focus-within:ring-4 focus-within:ring-accent/10 transition-all group overflow-hidden">
          <textarea
            ref={composerRef}
            placeholder={
              summaryLocked
                ? "请先生成 AI 概况..."
                : seriesRagLocked
                  ? "请先下载 RAG 向量模型..."
                  : seriesIndexingLocked
                    ? "数据库整理完成后可继续提问..."
                    : "向 AI 助手提问或下达指令..."
            }
            /* `overflow-y-auto` draws a permanent scrollbar track in some
               browsers even at one line, so the box scrolls only once it is
               actually capped by `max-h-40`. */
            className="block max-h-40 min-h-[44px] w-full resize-none overflow-y-hidden bg-transparent px-4 py-3 text-[15px] leading-relaxed text-stone-800 outline-none placeholder:text-stone-400 dark:text-stone-100 dark:placeholder:text-stone-500 @[440px]:px-5"
          rows={1}
            value={currentDraft}
            onChange={(event) => updateDraft(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter" && !event.shiftKey) {
                event.preventDefault();
                handleSubmit();
              }
            }}
            disabled={interactionDisabled}
          />
          {/* In-flow rather than absolute: `items-end` keeps the button aligned
              to the last line as the box grows, and it can no longer overlap
              the text or collide with the composer edge. */}
          <div className="p-2 pr-2.5">
            <button
              type="button"
              onClick={chatPending ? onCancelChat : handleSubmit}
              disabled={chatPending ? false : interactionDisabled || !currentDraft.trim()}
              aria-label={chatPending ? "中断对话" : "发送消息"}
              title={chatPending ? "中断对话" : "发送消息"}
              className="flex h-9 w-9 shrink-0 items-center justify-center rounded-[12px] bg-stone-900 text-white shadow-sm transition-all hover:bg-accent disabled:cursor-not-allowed disabled:opacity-40 dark:bg-white dark:text-black dark:hover:bg-accent dark:hover:text-white group-focus-within:bg-accent group-focus-within:text-white"
            >
              {chatPending ? <Square size={15} fill="currentColor" /> : <ArrowUp size={18} strokeWidth={2.5} />}
            </button>
          </div>
        </div>
        {/* The idle hint ("AI 已接入当前工作区上下文…") was removed: it cost a
            full 28px row of chat height while carrying no actionable info. The
            locked-state messages stay, because those do explain why the composer
            is unusable and how to recover. */}
        {composerHint ? (
          <div className="mt-3 flex items-center justify-center gap-2 opacity-70">
            <Sparkles size={12} className="text-stone-500 dark:text-stone-500" />
            <p className="text-xs font-medium text-stone-500 dark:text-stone-500">{composerHint}</p>
          </div>
        ) : null}
      </div>
    </div>
  );
}

function AssistantMessageFallback({ content }) {
  return <div className="whitespace-pre-wrap break-words">{content}</div>;
}

// Hoisted out of `WorkspaceChatPanel`: the composer resizes on every keystroke,
// and rendering the list inline recreated this element 60 times a second. As a
// module-level function it stays reference-equal between renders, so the thread
// is cheap to re-render while typing.
function ConversationMessage({ message, renderMessageContent }) {
  const isAssistant = message.role === "assistant";
  const canCopy = message.kind == null && typeof message.content === "string" && message.content.trim();

  return (
    <div
      id={`chat-message-${message.id}`}
      className={`flex items-start gap-3 max-w-2xl @[440px]:gap-4 ${isAssistant ? "" : "self-end justify-end"}`}
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
                : "px-4 py-3 rounded-[1.5rem] rounded-tr-sm bg-accent border border-accent/80 text-white shadow-sm @[440px]:px-5"
          }
        >
          {renderMessageContent(message, isAssistant)}
        </div>
        {/* 窄面板下这一行会被压到宽度不足，`复制` 按钮里的两个字被折成竖排
            （复 / 制 各占一行），而 meta 文本也折成两行。两者都禁止换行：
            文本允许截断，按钮整体不参与收缩。 */}
        <div className={`flex items-center gap-2 text-xs text-stone-500 dark:text-stone-500 ${isAssistant ? "ml-1" : ""}`}>
          <span className="min-w-0 truncate">{message.meta}</span>
          {canCopy ? (
            <CopyToClipboardButton
              text={message.content}
              iconSize={12}
              className="shrink-0 whitespace-nowrap gap-1 rounded-full bg-transparent px-2 py-0.5 font-medium text-stone-500 hover:bg-stone-100 hover:text-stone-700 dark:bg-transparent dark:text-stone-500 dark:hover:bg-stone-800 dark:hover:text-stone-200"
            />
          ) : null}
        </div>
      </div>
    </div>
  );
}

function ConversationJumpRail({ turns, onJump, anchorRef }) {
  const [activeTurnId, setActiveTurnId] = useState(null);
  // Keep the rail just outside the centred thread column instead of pinned to
  // the panel edge. At wide widths the thread is centred, so a `left-2` rail
  // drifted far away from the messages it indexes; at narrow widths the thread
  // fills the panel and the rail clamps back to the gutter.
  const [railLeft, setRailLeft] = useState(8);
  const activeIndex = turns.findIndex((turn) => turn.id === activeTurnId);
  const activeTurn = activeIndex >= 0 ? turns[activeIndex] : null;

  useEffect(() => {
    const anchor = anchorRef?.current;
    if (!anchor || typeof window === "undefined") {
      return undefined;
    }
    function syncRailPosition() {
      const parent = anchor.offsetParent ?? anchor.parentElement;
      if (!parent) {
        return;
      }
      const anchorRect = anchor.getBoundingClientRect();
      const parentRect = parent.getBoundingClientRect();
      setRailLeft(Math.max(8, Math.round(anchorRect.left - parentRect.left) - 36));
    }
    syncRailPosition();
    const observer = new ResizeObserver(syncRailPosition);
    observer.observe(anchor);
    observer.observe(anchor.parentElement ?? anchor);
    return () => observer.disconnect();
  }, [anchorRef, turns.length]);

  if (!turns.length) {
    return null;
  }

  function getNearestTurn(event) {
    const rect = event.currentTarget.getBoundingClientRect();
    const relativePosition = rect.height > 0 ? (event.clientY - rect.top) / rect.height : 0;
    const index = Math.max(0, Math.min(turns.length - 1, Math.round(relativePosition * (turns.length - 1))));
    return turns[index];
  }

  function activateNearestTurn(event, shouldJump = false) {
    const turn = getNearestTurn(event);
    setActiveTurnId(turn.id);
    if (shouldJump) {
      onJump(turn.id);
    }
  }

  return (
    <nav
      aria-label="对话快速跳转"
      onPointerMove={(event) => activateNearestTurn(event)}
      onClick={(event) => activateNearestTurn(event, true)}
      onMouseLeave={() => setActiveTurnId(null)}
      className="absolute top-1/2 z-20 -translate-y-1/2"
      style={{ left: `${railLeft}px` }}
    >
      <div className="relative flex flex-col items-start gap-1.5 py-2">
        {turns.map((turn, index) => {
          const distance = activeIndex < 0 ? null : Math.abs(index - activeIndex);
          const width = distance == null ? 10 : Math.max(10, 34 - distance * 7);
          const selected = index === activeIndex;
          return (
            <button
              key={turn.id}
              type="button"
              aria-label={`跳转到：${turn.prompt}`}
              aria-current={selected ? "true" : undefined}
              onMouseEnter={() => setActiveTurnId(turn.id)}
              onFocus={() => setActiveTurnId(turn.id)}
              onBlur={() => setActiveTurnId(null)}
              onClick={(event) => {
                event.stopPropagation();
                setActiveTurnId(turn.id);
                onJump(turn.id);
              }}
              className={`h-1 rounded-full transition-[width,background-color] duration-200 focus:outline-none focus-visible:ring-2 focus-visible:ring-accent/70 ${
                selected
                  ? "bg-white shadow-[0_0_0_1px_rgba(0,0,0,0.16)] dark:bg-white"
                  : "bg-stone-400/80 hover:bg-stone-500 dark:bg-stone-600 dark:hover:bg-stone-400"
              }`}
              style={{ width: `${width}px` }}
            />
          );
        })}
      </div>
      {activeTurn ? (
        <div className="pointer-events-none absolute left-full top-1/2 ml-3 w-52 -translate-y-1/2 rounded-md border border-stone-200/90 bg-white/95 px-3 py-2 text-xs font-medium leading-5 text-stone-700 shadow-lg backdrop-blur dark:border-stone-700 dark:bg-stone-950/95 dark:text-stone-200">
          {truncateConversationPrompt(activeTurn.prompt)}
        </div>
      ) : null}
    </nav>
  );
}

function truncateConversationPrompt(prompt) {
  const maximumLength = 42;
  return prompt.length > maximumLength ? `${prompt.slice(0, maximumLength).trimEnd()}...` : prompt;
}

function WorkspaceContextUsageInline({ usage, loading }) {
  const [expanded, setExpanded] = useState(false);
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
    <div className="relative">
      <button
        type="button"
        onClick={() => setExpanded((current) => !current)}
        aria-expanded={expanded}
        className={`inline-flex shrink-0 items-center gap-1.5 whitespace-nowrap rounded-full px-2.5 py-1 text-[11px] font-semibold transition-colors ${resolveUsageToneClass(usage.level)}`}
      >
        {thresholdLabel}
        <span className="opacity-60">{usage.usagePercent.toFixed(1)}%</span>
      </button>
      {expanded ? (
      <div className="absolute right-0 top-full z-30 mt-2 w-72 max-w-[calc(100vw-2rem)]">
        <div className="rounded-2xl border border-stone-200/80 bg-white/95 p-4 shadow-xl backdrop-blur-lg dark:border-stone-700 dark:bg-stone-900/95">
          <div className="flex items-center justify-between mb-2">
            <strong className="text-xs font-semibold text-stone-700 dark:text-stone-200">上下文预算</strong>
            <span className="text-xs text-stone-600 dark:text-stone-400">剩余 {formatTokenCount(usage.remainingTokens)}</span>
          </div>
          <p className="text-[11px] text-stone-600 dark:text-stone-400 mb-3">
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
      ) : null}
    </div>
  );
}

function WorkspaceToolTraceMessage({ message }) {
  const steps = Array.isArray(message.toolTrace?.steps) ? message.toolTrace.steps : [];
  const durationLabel = formatDurationLabel(message.toolTrace?.durationMs);
  const isRunning = message.toolTrace?.status === "running";
  const isIdle = message.toolTrace?.status === "idle";
  const isFailed = message.toolTrace?.status === "failed";
  const isCancelled = message.toolTrace?.status === "cancelled";

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
                <span className="inline-flex items-center gap-1 rounded-full bg-stone-100 px-2 py-0.5 text-[11px] font-medium text-stone-600 dark:bg-stone-800 dark:text-stone-400">
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
              ) : isCancelled ? (
                <span className="inline-flex items-center gap-1 rounded-full bg-stone-100 px-2 py-0.5 text-[11px] font-medium text-stone-600 dark:bg-stone-800 dark:text-stone-300">
                  已中断
                </span>
              ) : null}
            </div>
            <p className="mt-1 text-xs text-stone-600 dark:text-stone-400">
              {isRunning
                ? "正在处理后台任务..."
                : isFailed
                  ? "任务执行过程中发生错误"
                  : isCancelled
                    ? "任务已被中断"
                  : isIdle
                    ? "当前步骤已完成，正在准备后续处理"
                    : "展开查看具体的执行步骤说明"}
            </p>
          </div>
          <ChevronRight size={18} className="shrink-0 text-stone-500 transition-transform group-open:rotate-90" />
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
                    : step.status === "cancelled"
                      ? "bg-stone-100 text-stone-600 dark:bg-stone-800 dark:text-stone-300"
                    : "bg-success-subtle text-success"
                  }`}>
                  {step.status === "running" ? "进行中" : step.status === "failed" ? "失败" : step.status === "cancelled" ? "已中断" : "已完成"}
                </span>
                {step.target ? (
                  <span className="truncate text-xs text-stone-600 dark:text-stone-400">({step.target})</span>
                ) : null}
                {shouldShowDuration(step.durationMs) ? (
                  <span className="text-xs text-stone-500 dark:text-stone-500">用时 {formatDurationLabel(step.durationMs)}</span>
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
            <p className="mt-1 text-xs text-stone-600 dark:text-stone-400">
              展开查看命中的转写片段，再决定是否跳到视频。
            </p>
          </div>
          <ChevronRight size={18} className="shrink-0 text-stone-500 transition-transform group-open:rotate-90" />
        </div>
      </summary>

      <div className="border-t border-info/20 px-4 py-4 dark:border-info/10">
        {reference.query ? (
          <p className="text-xs font-medium text-stone-600 dark:text-stone-400">
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
  const isCancelled = message.thoughtTrace?.status === "cancelled";
  const durationLabel = formatDurationLabel(message.thoughtTrace?.durationMs);
  const summary = typeof message.thoughtTrace?.summary === "string" ? message.thoughtTrace.summary : "";
  const stages = Array.isArray(message.thoughtTrace?.stages) ? message.thoughtTrace.stages : [];
  const hasStages = stages.length > 0;
  const displaySummary = summary || (isRunning ? "正在思考中..." : "暂无思考过程摘要。");

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
                  <span className="inline-flex items-center gap-1 rounded-full bg-stone-100 px-2 py-0.5 text-[11px] font-medium text-stone-600 dark:bg-stone-800 dark:text-stone-400">
                    <Clock3 size={12} />
                    用时 {durationLabel}
                  </span>
                ) : null}
              </div>
              <p className="mt-1 text-xs text-stone-600 dark:text-stone-400">
                {isRunning ? "当前按图节点顺序执行中" : isFailed ? "本轮图节点执行失败" : isCancelled ? "本轮图节点执行已中断" : "本轮图节点执行已完成"}
              </p>
            </div>
            <ChevronRight size={18} className="shrink-0 text-stone-500 transition-transform group-open:rotate-90" />
          </div>
        </summary>

        <div className="border-t border-stone-200/80 px-4 py-4 dark:border-stone-800">
          <div className="flex flex-col gap-3">
            <AnimatePresence initial={false}>
              {stages.map((stage) => {
                const stageRunning = stage.status === "running";
                const stageFailed = stage.status === "failed";
                const stageCancelled = stage.status === "cancelled";
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
                            : stageCancelled
                              ? "bg-stone-100 text-stone-600 dark:bg-stone-800 dark:text-stone-300"
                            : "bg-success-subtle text-success"
                          }`}>
                          {stageRunning ? <LoaderCircle size={15} className="animate-spin" /> : <CheckCircle2 size={15} />}
                        </div>
                        <div className="min-w-0">
                          <div className="text-sm font-semibold text-stone-800 dark:text-stone-100">{stage.label}</div>
                          <div className="mt-0.5 text-xs text-stone-600 dark:text-stone-400">{stage.nodeId}</div>
                        </div>
                      </div>
                      <div className="flex shrink-0 items-center gap-2">
                        <span className={`rounded-full px-2 py-0.5 text-[11px] font-medium ${stageRunning
                          ? "bg-info-subtle text-info"
                          : stageFailed
                            ? "bg-danger-subtle text-danger"
                            : stageCancelled
                              ? "bg-stone-100 text-stone-600 dark:bg-stone-800 dark:text-stone-300"
                            : "bg-success-subtle text-success"
                          }`}>
                          {stageRunning ? "执行中" : stageFailed ? "失败" : stageCancelled ? "已中断" : "已完成"}
                        </span>
                        {stageDurationLabel ? (
                          <span className="text-xs text-stone-500 dark:text-stone-500">用时 {stageDurationLabel}</span>
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
                <span className="inline-flex items-center gap-1 rounded-full bg-stone-100 px-2 py-0.5 text-[11px] font-medium text-stone-600 dark:bg-stone-800 dark:text-stone-400">
                  <Clock3 size={12} />
                  用时 {durationLabel}
                </span>
              ) : null}
            </div>
            <p className="mt-1 text-xs text-stone-600 dark:text-stone-400">
              {isRunning ? "正在分析当前问题，思考过程将实时展开" : isFailed ? "思考过程执行失败，展开查看错误摘要" : isCancelled ? "思考过程已中断" : "展开查看对问题的思考过程摘要"}
            </p>
          </div>
          <ChevronRight size={18} className="shrink-0 text-stone-500 transition-transform group-open:rotate-90" />
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
