import { FileText, Network, PlaySquare, Sparkles, Plus, ArrowUp } from "lucide-react";

const TOOL_META = {
  overview: { label: "AI概况", icon: FileText },
  mindmap: { label: "思维导图", icon: Network },
  preview: { label: "视频预览", icon: PlaySquare },
};

function describeToolState(toolId, toolState) {
  if (!toolState) {
    return "读取中";
  }
  if (toolId === "preview") {
    return "随时可查看";
  }
  if (toolState.generated) {
    return "已可用";
  }
  if (toolState.available === false) {
    return "需先生成概况";
  }
  return "待生成";
}

export function WorkspaceChatPanel({ selectedVideo, selectedToolId, tools, onSelectTool }) {
  if (!selectedVideo) {
    return (
      <div className="flex-1 h-full flex items-center justify-center bg-stone-50/50">
        <p className="text-stone-400 font-medium">请先在左侧选择视频</p>
      </div>
    );
  }

  return (
    <div className="h-full w-full flex flex-col bg-white">
      {/* Header */}
      <div className="shrink-0 flex items-center justify-between px-6 py-4 border-b border-stone-100">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-full bg-teal-50 flex items-center justify-center">
            <Sparkles size={16} className="text-teal-600" />
          </div>
          <div>
            <h3 className="text-base font-bold text-stone-800">NotebookLM 助手</h3>
            <p className="text-xs text-stone-500">基于《{selectedVideo.title}》</p>
          </div>
        </div>
        <button className="text-stone-400 hover:text-stone-600 transition-colors" title="新建对话">
          <Plus size={20} />
        </button>
      </div>

      {/* Chat History Area */}
      <div className="flex-1 overflow-auto p-6 md:p-8 flex flex-col gap-6">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          {Object.entries(TOOL_META).map(([toolId, meta]) => {
            const Icon = meta.icon;
            const toolState = tools?.[toolId];
            return (
              <button
                key={toolId}
                type="button"
                onClick={() => onSelectTool(toolId)}
                disabled={toolState?.available === false}
                className={`flex items-center gap-3 rounded-2xl border px-4 py-3 text-left transition-all ${
                  selectedToolId === toolId
                    ? "border-teal-300 bg-teal-50 text-teal-900"
                    : "border-stone-200 bg-white text-stone-700 hover:border-stone-300"
                } ${toolState?.available === false ? "opacity-50 cursor-not-allowed" : ""}`}
              >
                <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-stone-100">
                  <Icon size={18} className={selectedToolId === toolId ? "text-teal-600" : "text-stone-500"} />
                </span>
                <span className="flex flex-col">
                  <span className="text-sm font-semibold">{meta.label}</span>
                  <span className="text-xs text-stone-500">
                    {describeToolState(toolId, toolState)}
                  </span>
                </span>
              </button>
            );
          })}
        </div>
        
        {/* Assistant Welcome Message */}
        <div className="flex items-start gap-4 max-w-2xl">
          <div className="w-8 h-8 rounded-full bg-teal-500 flex items-center justify-center shrink-0 shadow-sm mt-1">
            <Sparkles size={16} className="text-white" />
          </div>
          <div className="flex flex-col gap-2">
            <div className="p-4 rounded-2xl rounded-tl-sm bg-stone-50 border border-stone-200 text-stone-700 leading-relaxed">
              你好！我已经准备好当前视频的知识库。你可以向我提出任何问题，比如：
              <ul className="mt-3 space-y-2 list-none p-0">
                <li className="text-teal-700 cursor-pointer hover:bg-teal-50 px-2 py-1 -mx-2 rounded transition-colors text-sm font-medium">✨ 给我一段 5 分钟的口播总结稿？</li>
                <li className="text-teal-700 cursor-pointer hover:bg-teal-50 px-2 py-1 -mx-2 rounded transition-colors text-sm font-medium">✨ 视频里提到了哪些具体的数据指标？</li>
                <li className="text-teal-700 cursor-pointer hover:bg-teal-50 px-2 py-1 -mx-2 rounded transition-colors text-sm font-medium">✨ 帮我列出本期视频的所有 Action Items。</li>
              </ul>
            </div>
            <span className="text-xs text-stone-400 ml-1">Notebook Assistant • Just now</span>
          </div>
        </div>

        <div className="rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
          {tools?.aiTodo ?? "TODO: 后续 AI 对话会感知当前工具状态，并可自动切换到“AI概况 / 思维导图 / 视频预览”执行联动操作。"}
        </div>

        {/* Mock User Message */}
        <div className="flex items-start justify-end gap-4 max-w-2xl self-end mt-4">
          <div className="flex flex-col gap-2 items-end">
            <div className="px-5 py-3 rounded-2xl rounded-tr-sm bg-stone-800 text-stone-50 shadow-sm">
              好的，那我们就从核心结论开始聊吧。
            </div>
          </div>
        </div>
      </div>

      {/* Input Area */}
      <div className="shrink-0 p-4 bg-white border-t border-stone-100">
        <div className="max-w-4xl mx-auto relative rounded-3xl border border-stone-200 bg-stone-50 group focus-within:border-teal-400 focus-within:ring-4 focus-within:ring-teal-500/10 transition-all">
          <textarea 
            placeholder="提问或下达指令..." 
            className="w-full bg-transparent resize-none py-4 pl-6 pr-16 text-base text-stone-800 outline-none leading-relaxed h-[80px]"
            disabled
          />
          <div className="absolute right-3 bottom-3">
             <button className="flex items-center justify-center w-10 h-10 rounded-full bg-stone-800 text-white hover:bg-teal-600 transition-colors shadow-sm disabled:opacity-50 disabled:cursor-not-allowed">
               <ArrowUp size={20} strokeWidth={2.5} />
             </button>
          </div>
        </div>
        <p className="text-center text-xs text-stone-400 mt-3">AI 对话系统尚未接入后端 API，当前仅保留工具联动的 TODO 占位。</p>
      </div>
    </div>
  );
}
