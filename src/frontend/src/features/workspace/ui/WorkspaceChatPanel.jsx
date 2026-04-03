import { Sparkles, Plus, ArrowUp } from "lucide-react";

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
  if (selectedToolId === "preview") {
    return "视频预览";
  }
  return "工具首页";
}

export function WorkspaceChatPanel({ activeSeries, selectedVideo, selectedContextType, selectedToolId, tools }) {
  if (!activeSeries) {
    return (
      <div className="workspace-muted-panel flex-1 h-full flex items-center justify-center">
        <p className="text-stone-400 dark:text-stone-500 font-medium">请先在左侧选择系列</p>
      </div>
    );
  }

  const scopeLabel = selectedContextType === "series" ? activeSeries.title : selectedVideo?.title ?? activeSeries.title;
  const scopeHint = selectedContextType === "series" ? "当前聚焦整个系列" : "当前聚焦单个视频";

  return (
    <div className="h-full w-full flex flex-col bg-transparent">
      {/* Header */}
      <div className="workspace-toolbar-surface shrink-0 flex items-center justify-between px-6 py-4 border-b border-stone-200/80 dark:border-stone-800">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-2xl bg-sky-50 dark:bg-sky-950/25 flex items-center justify-center border border-sky-100 dark:border-sky-900/60">
            <Sparkles size={16} className="text-sky-700 dark:text-sky-300" />
          </div>
          <div>
            <h3 className="text-base font-bold text-stone-800 dark:text-stone-100">NotebookLM 助手</h3>
            <p className="text-xs text-stone-500 dark:text-stone-400">基于《{scopeLabel}》</p>
          </div>
        </div>
        <button className="text-stone-400 dark:text-stone-500 hover:text-stone-600 dark:hover:text-stone-300 transition-colors" title="新建对话">
          <Plus size={20} />
        </button>
      </div>

      {/* Chat History Area */}
      <div className="flex-1 overflow-auto p-6 md:p-8 flex flex-col gap-6">
        <div className="workspace-muted-panel rounded-[1.5rem] border px-4 py-3 text-sm text-stone-600 dark:text-stone-300">
          当前页面：<span className="font-semibold text-stone-900 dark:text-stone-100">{describeCurrentTool(selectedToolId)}</span>
          <span className="ml-2 text-stone-400 dark:text-stone-500">
            {selectedToolId === "studio" || selectedToolId === "series-home" ? "请在右侧先选择一个工具卡片进入。" : "可在右侧右上角返回工具页。"}
          </span>
        </div>

        <div className="workspace-elevated-panel rounded-[1.5rem] border px-4 py-3 text-sm text-stone-600 dark:text-stone-300">
          当前上下文：<span className="font-semibold text-stone-900 dark:text-stone-100">{scopeHint}</span>
          <span className="ml-2 text-stone-400 dark:text-stone-500">这会影响后续 AI 判断你是在问整个 series，还是只问当前视频。</span>
        </div>
        
        {/* Assistant Welcome Message */}
        <div className="flex items-start gap-4 max-w-2xl">
          <div className="w-8 h-8 rounded-2xl bg-[#0070f3] flex items-center justify-center shrink-0 shadow-sm mt-1">
            <Sparkles size={16} className="text-white" />
          </div>
          <div className="flex flex-col gap-2">
            <div className="workspace-elevated-panel p-4 rounded-[1.5rem] rounded-tl-sm border text-stone-700 dark:text-stone-200 leading-relaxed">
              你好！我已经准备好当前知识库。你可以向我提出任何问题，比如：
              <ul className="mt-3 space-y-2 list-none p-0">
                <li className="text-[#0070f3] dark:text-[#4da3ff] cursor-pointer hover:bg-sky-50 dark:hover:bg-sky-950/20 px-2 py-1 -mx-2 rounded transition-colors text-sm font-medium">✨ 给我一段 5 分钟的口播总结稿？</li>
                <li className="text-[#0070f3] dark:text-[#4da3ff] cursor-pointer hover:bg-sky-50 dark:hover:bg-sky-950/20 px-2 py-1 -mx-2 rounded transition-colors text-sm font-medium">✨ 视频里提到了哪些具体的数据指标？</li>
                <li className="text-[#0070f3] dark:text-[#4da3ff] cursor-pointer hover:bg-sky-50 dark:hover:bg-sky-950/20 px-2 py-1 -mx-2 rounded transition-colors text-sm font-medium">✨ 帮我列出本期视频的所有 Action Items。</li>
              </ul>
            </div>
            <span className="text-xs text-stone-400 dark:text-stone-500 ml-1">Notebook Assistant • Just now</span>
          </div>
        </div>

        <div className="rounded-[1.5rem] border border-amber-200/80 dark:border-amber-900/30 bg-amber-50/80 dark:bg-amber-950/15 px-4 py-3 text-sm text-amber-900 dark:text-amber-100">
          {tools?.aiTodo ?? "TODO: 后续 AI 对话会感知当前工具状态，并可自动切换到“AI概况 / 思维导图 / 视频预览”执行联动操作。"}
        </div>

        {/* Mock User Message */}
        <div className="flex items-start justify-end gap-4 max-w-2xl self-end mt-4">
          <div className="flex flex-col gap-2 items-end">
            <div className="px-5 py-3 rounded-[1.5rem] rounded-tr-sm bg-slate-800 dark:bg-slate-800/92 border border-slate-700/80 dark:border-slate-700 text-slate-50 shadow-sm">
              好的，那我们就从核心结论开始聊吧。
            </div>
          </div>
        </div>
      </div>

      {/* Input Area */}
      <div className="workspace-toolbar-surface shrink-0 p-5 border-t border-stone-200/80 dark:border-stone-800">
        <div className="max-w-4xl mx-auto relative rounded-[1.75rem] border workspace-input-surface group focus-within:border-[#0070f3] focus-within:ring-4 focus-within:ring-[#0070f3]/10 transition-all">
          <textarea 
            placeholder="提问或下达指令..." 
            className="w-full bg-transparent resize-none py-5 pl-6 pr-16 text-base text-stone-800 dark:text-stone-100 outline-none leading-relaxed h-[92px]"
            disabled
          />
          <div className="absolute right-3 bottom-3">
             <button className="flex items-center justify-center w-10 h-10 rounded-full bg-stone-900 dark:bg-white text-white dark:text-black hover:bg-[#0070f3] hover:text-white transition-colors shadow-sm disabled:opacity-50 disabled:cursor-not-allowed">
               <ArrowUp size={20} strokeWidth={2.5} />
             </button>
          </div>
        </div>
        <p className="text-center text-xs text-stone-400 dark:text-stone-500 mt-4">AI 对话系统尚未接入后端 API，当前仅保留工具联动的 TODO 占位。</p>
      </div>
    </div>
  );
}
