import { MessageSquare, Plus, Trash2, Clock3 } from "lucide-react";

export function WorkspaceChatManagementView({ chat }) {
  if (!chat) return null;

  const { sessions = [], activeSessionId, startNewChat, selectChatSession, clearChat } = chat;

  return (
    <div className="flex h-full w-full flex-col gap-8 pb-10 animate-in fade-in slide-in-from-bottom-4 duration-500">
      <div className="flex items-center justify-between mb-2 border-b border-stone-200/80 pb-6 dark:border-stone-800">
        <div>
          <h2 className="text-xl font-bold text-stone-800 dark:text-stone-100 flex items-center gap-2">
            <MessageSquare size={20} className="text-accent" />
            对话与历史管理
          </h2>
        </div>
        <div className="flex gap-3">
          <button
            type="button"
            onClick={startNewChat}
            className="inline-flex items-center gap-2 rounded-xl border border-accent/30 bg-accent/10 px-4 py-2 text-sm font-semibold text-accent transition hover:bg-accent/15 shadow-sm"
          >
            <Plus size={16} />
            新建话题
          </button>
          <button
            type="button"
            onClick={clearChat}
            className="btn-danger-ghost inline-flex items-center gap-2 rounded-xl px-4 py-2 text-sm font-semibold shadow-sm"
          >
            <Trash2 size={16} />
            清空当前对话
          </button>
        </div>
      </div>

      <div>
        <h3 className="text-sm font-bold uppercase tracking-widest text-stone-400 dark:text-stone-500 mb-5 flex items-center gap-2">
          <Clock3 size={16} /> 历史记录 ({sessions.length})
        </h3>
        {sessions.length === 0 ? (
          <div className="rounded-3xl border border-dashed border-stone-200/80 bg-stone-50/50 p-12 text-center dark:border-stone-800 dark:bg-stone-950/30">
            <MessageSquare size={32} className="mx-auto mb-3 text-stone-300 dark:text-stone-700" />
            <p className="text-stone-500 dark:text-stone-400 font-medium">暂无历史对话记录</p>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 2xl:grid-cols-3 gap-4">
            {sessions.map((session) => (
              <button
                key={session.id}
                type="button"
                onClick={() => selectChatSession?.(session.id)}
                className={`group relative flex flex-col items-start gap-4 rounded-3xl border p-5 text-left transition-all ${session.id === activeSessionId
                    ? "border-accent/40 bg-accent/5 dark:border-accent/30 dark:bg-accent/10 shadow-sm ring-1 ring-accent/20"
                    : "border-stone-200/80 bg-white hover:border-stone-300 hover:shadow-md dark:border-white/5 dark:bg-[#1a1a1a] dark:hover:border-white/10"
                  }`}
              >
                <div className="flex items-center justify-between w-full">
                  <div className={`flex h-10 w-10 items-center justify-center rounded-2xl ${session.id === activeSessionId
                      ? "bg-accent/15 text-accent"
                      : "bg-stone-100 text-stone-500 dark:bg-stone-800 dark:text-stone-400 group-hover:bg-accent/10 group-hover:text-accent"
                    } transition-colors`}>
                    <MessageSquare size={18} />
                  </div>
                  {session.id === activeSessionId && (
                    <span className="rounded-full bg-accent/10 px-2.5 py-1 text-[11px] font-bold text-accent">当前对话</span>
                  )}
                </div>
                <h4 className={`text-[15px] font-bold leading-snug line-clamp-2 ${session.id === activeSessionId
                    ? "text-stone-900 dark:text-stone-100"
                    : "text-stone-700 dark:text-stone-200 group-hover:text-stone-900 dark:group-hover:text-white"
                  }`}>
                  {session.title || "新话题"}
                </h4>
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
