import { useState } from "react";
import { LoaderCircle, PencilLine, Trash2, Plus, ChevronLeft, Calendar, Sparkles } from "lucide-react";

import { WorkspaceStateBlock } from "../shared/WorkspaceStateBlock";
import { WorkspaceMarkdownMessage } from "../shared/WorkspaceMarkdownMessage";
import { WorkspaceProviderSelect } from "../shared/WorkspaceSettingsControls";

const AI_NOTE_TEMPLATE_OPTIONS = [
  { id: "general", label: "通用" },
  { id: "short", label: "短笔记" },
  { id: "long", label: "长笔记" },
  { id: "minimal", label: "精简" },
  { id: "detailed", label: "详细" },
  { id: "tutorial", label: "教程" },
  { id: "academic", label: "学术" },
  { id: "xiaohongshu", label: "小红书" },
  { id: "life_journal", label: "生活向" },
  { id: "task_oriented", label: "任务导向" },
  { id: "business", label: "商业风格" },
  { id: "meeting_minutes", label: "会议纪要" },
];

function NoteListItem({ note, onOpen }) {
  const pending = note.pending === true;
  return (
    <article
      onClick={pending ? undefined : () => onOpen(note)}
      className={`group rounded-2xl border border-stone-200/60 bg-white p-5 transition-all dark:border-stone-800/60 dark:bg-stone-950 ${
        pending
          ? "cursor-default"
          : "cursor-pointer hover:border-accent/40 hover:shadow-md hover:shadow-accent/5 dark:hover:border-accent/40"
      }`}
    >
      <div className="flex items-center justify-between gap-4">
        <h3 className="font-bold text-stone-900 line-clamp-1 dark:text-stone-100">{note.title}</h3>
        <span className={`shrink-0 rounded-full px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider ${note.source === "agent" ? "bg-info-subtle text-info" : "bg-stone-100 text-stone-600 dark:bg-stone-800 dark:text-stone-300"}`}>
          {note.source === "agent" ? "AGENT" : "✍️ Manual"}
        </span>
      </div>
      <p className="mt-2 line-clamp-2 text-sm leading-relaxed text-stone-600 dark:text-stone-400">
        {note.content}
      </p>
      <div className="mt-4 flex items-center text-xs font-medium text-stone-500 dark:text-stone-500">
        {pending ? (
          <>
            <LoaderCircle size={12} className="mr-1.5 animate-spin" />
            正在生成
          </>
        ) : (
          <>
            <Calendar size={12} className="mr-1.5" />
            {note.createdAt.replace("T", " ").substring(0, 16)}
          </>
        )}
      </div>
    </article>
  );
}

export function WorkspaceNotesView({
  notes,
  notesLoading,
  savingNote,
  generatingAiNote,
  onGenerateAiNote,
  onCreateNote,
  onUpdateNote,
  onDeleteNote,
}) {
  const [viewState, setViewState] = useState("list"); // "list" | "create" | "detail"
  const [selectedNoteId, setSelectedNoteId] = useState(null);

  // 新建笔记状态
  const [draftTitle, setDraftTitle] = useState("");
  const [draftContent, setDraftContent] = useState("");

  // 编辑笔记状态 (在详情页内编辑)
  const [isEditing, setIsEditing] = useState(false);
  const [editingTitle, setEditingTitle] = useState("");
  const [editingContent, setEditingContent] = useState("");
  const [aiTemplate, setAiTemplate] = useState("general");

  const selectedNote = notes?.notes?.find((n) => n.id === selectedNoteId);

  function handleCreateNote() {
    if (!draftTitle.trim() || !draftContent.trim() || savingNote) {
      return;
    }
    onCreateNote({
      title: draftTitle,
      content: draftContent,
      source: "manual",
    });
    setDraftTitle("");
    setDraftContent("");
    setViewState("list");
  }

  function openDetail(note) {
    setSelectedNoteId(note.id);
    setViewState("detail");
    setIsEditing(false);
  }

  function handleStartEdit() {
    if (!selectedNote) return;
    setIsEditing(true);
    setEditingTitle(selectedNote.title);
    setEditingContent(selectedNote.content);
  }

  function handleCancelEdit() {
    setIsEditing(false);
    setEditingTitle("");
    setEditingContent("");
  }

  function handleSaveEdit() {
    if (!selectedNoteId || !editingTitle.trim() || !editingContent.trim() || savingNote) {
      return;
    }
    onUpdateNote(selectedNoteId, {
      title: editingTitle,
      content: editingContent,
    });
    setIsEditing(false);
  }

  function handleDeleteNote(id) {
    onDeleteNote(id);
    if (viewState === "detail" && selectedNoteId === id) {
      setViewState("list");
      setSelectedNoteId(null);
    }
  }

  if (notesLoading) {
    return (
      <WorkspaceStateBlock
        eyebrow="Notes"
        title="载入笔记"
        description="正在读取当前视频的笔记。"
        loading
      />
    );
  }

  // ========== 新建视图 ==========
  if (viewState === "create") {
    return (
      <div className="flex h-full flex-col gap-4 animate-in fade-in slide-in-from-right-4 duration-300">
        <div className="flex items-center justify-between px-2">
          <button 
            onClick={() => setViewState("list")} 
            className="inline-flex items-center gap-1.5 rounded-full px-3 py-1.5 text-sm font-semibold text-stone-600 transition hover:bg-stone-100 dark:text-stone-300 dark:hover:bg-stone-800"
          >
            <ChevronLeft size={16} /> 返回列表
          </button>
          <h2 className="text-sm font-bold tracking-widest text-stone-500 uppercase dark:text-stone-500">新建笔记</h2>
          <div className="w-[88px]" /> {/* 占位符以居中标题 */}
        </div>
        
        <section className="rounded-3xl border border-stone-200/80 bg-white p-6 shadow-sm dark:border-stone-800 dark:bg-stone-950">
          <input
            value={draftTitle}
            onChange={(event) => setDraftTitle(event.target.value)}
            placeholder="输入标题..."
            className="w-full bg-transparent text-xl font-bold text-stone-900 placeholder:text-stone-300 outline-none transition focus:placeholder:text-stone-400 dark:text-stone-100 dark:placeholder:text-stone-700"
          />
          <div className="my-4 h-px w-full bg-stone-100 dark:bg-stone-800/60" />
          <textarea
            value={draftContent}
            onChange={(event) => setDraftContent(event.target.value)}
            placeholder="记录重要细节、结论或待办事项..."
            className="min-h-[240px] w-full resize-none bg-transparent text-sm leading-relaxed text-stone-700 placeholder:text-stone-400/80 outline-none dark:text-stone-300 dark:placeholder:text-stone-600"
          />
          <div className="mt-6 flex justify-end">
            <button
              type="button"
              onClick={handleCreateNote}
              disabled={savingNote || !draftTitle.trim() || !draftContent.trim()}
              className="inline-flex items-center justify-center gap-2 rounded-full bg-stone-900 px-6 py-2.5 text-sm font-semibold text-white transition hover:bg-accent hover:shadow-md hover:shadow-accent/20 disabled:cursor-not-allowed disabled:opacity-40 dark:bg-white dark:text-black dark:hover:bg-accent dark:hover:text-white"
            >
              {savingNote ? <LoaderCircle size={16} className="animate-spin" /> : <PencilLine size={16} />}
              保存笔记
            </button>
          </div>
        </section>
      </div>
    );
  }

  // ========== 详情/编辑视图 ==========
  if (viewState === "detail" && selectedNote) {
    return (
      <div className="flex h-full flex-col gap-4 animate-in fade-in slide-in-from-right-4 duration-300">
        <div className="flex items-center justify-between px-2">
          <button 
            onClick={() => { setViewState("list"); setIsEditing(false); }} 
            className="inline-flex items-center gap-1.5 rounded-full px-3 py-1.5 text-sm font-semibold text-stone-600 transition hover:bg-stone-100 dark:text-stone-300 dark:hover:bg-stone-800"
          >
            <ChevronLeft size={16} /> 返回列表
          </button>
          <div className="flex items-center gap-2">
            {isEditing ? (
              <>
                <button
                  onClick={handleCancelEdit}
                  className="rounded-full border border-stone-200 px-4 py-1.5 text-xs font-bold text-stone-600 transition hover:bg-stone-50 dark:border-stone-700 dark:text-stone-300 dark:hover:bg-stone-800"
                >
                  取消
                </button>
                <button
                  onClick={handleSaveEdit}
                  disabled={savingNote || !editingTitle.trim() || !editingContent.trim()}
                  className="rounded-full bg-stone-900 px-4 py-1.5 text-xs font-bold text-white transition hover:bg-accent disabled:cursor-not-allowed disabled:opacity-50 dark:bg-white dark:text-black"
                >
                  保存修改
                </button>
              </>
            ) : (
              <>
                <button
                  onClick={handleStartEdit}
                  className="flex h-8 w-8 items-center justify-center rounded-full text-stone-600 hover:bg-stone-100 hover:text-stone-900 dark:text-stone-400 dark:hover:bg-stone-800 dark:hover:text-stone-100"
                  title="编辑"
                >
                  <PencilLine size={15} />
                </button>
                <button
                  onClick={() => handleDeleteNote(selectedNote.id)}
                  disabled={savingNote}
                  className="flex h-8 w-8 items-center justify-center rounded-full text-stone-600 hover:bg-danger-subtle hover:text-danger dark:text-stone-400"
                  title="删除"
                >
                  <Trash2 size={15} />
                </button>
              </>
            )}
          </div>
        </div>

        <article className="rounded-3xl border border-stone-200/80 bg-white p-6 shadow-sm dark:border-stone-800 dark:bg-stone-950">
          {isEditing ? (
            <div className="flex flex-col gap-4">
              <input
                value={editingTitle}
                onChange={(e) => setEditingTitle(e.target.value)}
                placeholder="笔记标题"
                className="w-full rounded-xl border border-stone-200 bg-stone-50 px-4 py-3 text-lg font-bold text-stone-900 outline-none focus:border-accent focus:bg-white dark:border-stone-800 dark:bg-stone-900 dark:text-stone-100 dark:focus:bg-stone-950"
              />
              <textarea
                value={editingContent}
                onChange={(e) => setEditingContent(e.target.value)}
                placeholder="笔记内容"
                className="min-h-[240px] w-full rounded-xl border border-stone-200 bg-stone-50 px-4 py-3 text-sm leading-relaxed text-stone-900 outline-none focus:border-accent focus:bg-white dark:border-stone-800 dark:bg-stone-900 dark:text-stone-100 dark:focus:bg-stone-950"
              />
            </div>
          ) : (
            <>
              <div className="flex items-center gap-3">
                <span className={`inline-flex items-center rounded-full px-2.5 py-1 text-[10px] font-bold uppercase tracking-wider ${selectedNote.source === "agent" ? "bg-info-subtle text-info" : "bg-stone-100 text-stone-600 dark:bg-stone-800 dark:text-stone-300"}`}>
                  {selectedNote.source === "agent" ? "Agent Note" : "✍️ Manual Note"}
                </span>
                <span className="text-xs font-medium text-stone-500 dark:text-stone-500">
                  {selectedNote.createdAt.replace("T", " ").replace("Z", "").substring(0, 16)}
                  {selectedNote.updatedAt !== selectedNote.createdAt && " (已编辑)"}
                </span>
              </div>
              <h1 className="mt-4 text-2xl font-bold text-stone-900 dark:text-stone-100">{selectedNote.title}</h1>
              <div className="my-5 h-px w-full bg-stone-100 dark:bg-stone-800/60" />
              <div className="markdown-body mt-2 text-sm text-stone-700 dark:text-stone-300">
                <WorkspaceMarkdownMessage content={selectedNote.content} />
              </div>
            </>
          )}
        </article>
      </div>
    );
  }

  // ========== 列表视图 (默认) ==========
  return (
    <div className="flex h-full flex-col gap-5 animate-in fade-in slide-in-from-left-4 duration-300">
      <div className="flex flex-wrap items-center justify-between gap-4 px-2">
        <div className="min-w-[7rem] flex-1">
          <h2 className="text-lg font-bold text-stone-900 dark:text-stone-100">全部笔记</h2>
          <p className="mt-0.5 text-xs text-stone-600 dark:text-stone-400">共 {notes?.notes?.length || 0} 条记录</p>
        </div>
        <div className="ml-auto flex max-w-full flex-wrap justify-end gap-2">
          <WorkspaceProviderSelect
            value={aiTemplate}
            onChange={setAiTemplate}
            options={AI_NOTE_TEMPLATE_OPTIONS}
            disabled={generatingAiNote}
            ariaLabel="AI 笔记模板"
            hideGroupLabels
            className="w-36"
          />
          <button
            type="button"
            onClick={() => onGenerateAiNote(aiTemplate)}
            disabled={generatingAiNote}
            className="inline-flex shrink-0 items-center gap-2 whitespace-nowrap rounded-full border border-accent/25 bg-accent/10 px-4 py-2 text-sm font-semibold text-accent transition hover:bg-accent hover:text-white hover:shadow-md hover:shadow-accent/20 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/50 focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50 dark:border-accent/30 dark:bg-accent/15 dark:text-accent dark:hover:bg-accent dark:hover:text-white"
          >
            {generatingAiNote ? <LoaderCircle size={16} className="animate-spin" /> : <Sparkles size={16} />}
            {generatingAiNote ? "正在生成" : "AI 笔记"}
          </button>
          <button
            type="button"
            onClick={() => setViewState("create")}
            className="inline-flex shrink-0 items-center gap-2 whitespace-nowrap rounded-full bg-stone-900 px-4 py-2 text-sm font-semibold text-white transition hover:bg-accent hover:shadow-md hover:shadow-accent/20 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/50 focus-visible:ring-offset-2 dark:bg-white dark:text-black dark:hover:bg-accent dark:hover:text-white"
          >
            <Plus size={16} /> 记笔记
          </button>
        </div>
      </div>

      <div className="flex flex-col gap-3">
        {generatingAiNote || (notes?.notes ?? []).length ? (
          <>
            {generatingAiNote ? (
              <NoteListItem
                note={{
                  id: "pending-ai-note",
                  title: "正在生成笔记",
                  content: "正在根据视频转写整理内容，完成后会自动加入列表。",
                  source: "agent",
                  pending: true,
                }}
                onOpen={openDetail}
              />
            ) : null}
            {(notes?.notes ?? []).map((note) => (
              <NoteListItem key={note.id} note={note} onOpen={openDetail} />
            ))}
          </>
        ) : (
          <div className="mt-4">
            <WorkspaceStateBlock
              eyebrow="Notes"
              title="暂无笔记"
              description="点击右上角生成 AI 笔记，或手动记录重要内容。"
              dashed
            />
          </div>
        )}
      </div>
    </div>
  );
}
