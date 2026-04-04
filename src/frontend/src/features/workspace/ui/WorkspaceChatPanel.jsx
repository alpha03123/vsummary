import { useState } from "react";
import { Sparkles, Plus, ArrowUp, LoaderCircle } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

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
  chatPending = false,
  onSubmitChat,
}) {
  const [draft, setDraft] = useState("");
  const scopeLabel = selectedContextType === "library"
    ? workspaceTitle ?? "整个知识库"
    : selectedContextType === "series"
      ? activeSeries?.title ?? "当前系列"
      : selectedVideo?.title ?? activeSeries?.title ?? "当前视频";
  const currentPageLabel = describeCurrentTool(selectedToolId);
  const suggestedPrompts = selectedContextType === "library"
    ? [
        "这个知识库主要覆盖了哪些主题？",
        "帮我找一下和 API Key 相关的视频",
        "最近适合先看的入门视频有哪些？",
        "帮我按主题整理一下整个库的学习路径",
      ]
    : [
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
    if (!isAssistant) {
      return message.content;
    }

    return (
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          a: ({ node, ...props }) => <a {...props} target="_blank" rel="noreferrer" />,
        }}
      >
        {message.content}
      </ReactMarkdown>
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
        <button className="text-stone-400 dark:text-stone-500 hover:text-stone-600 dark:hover:text-stone-300 transition-colors" title="新建对话">
          <Plus size={20} />
        </button>
      </div>

      {/* Chat History Area */}
      <div className="flex-1 overflow-auto p-6 md:p-8 flex flex-col gap-6">
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
                    isAssistant
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

        {chatPending ? (
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
          AI 已接入当前工作区上下文，可返回工具联动动作并自动切换右侧工具页。
        </p>
      </div>
    </div>
  );
}
