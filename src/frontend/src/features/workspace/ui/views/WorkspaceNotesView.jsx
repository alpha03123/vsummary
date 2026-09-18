import { useState } from "react";
import { LoaderCircle, PencilLine, Trash2, Plus, Calendar } from "lucide-react";

import { WorkspaceStateBlock } from "../shared/WorkspaceStateBlock";
import { WorkspaceBackButton } from "../shared/WorkspaceBackButton";
import { WorkspaceMarkdownMessage } from "../shared/WorkspaceMarkdownMessage";

// 笔记时间戳由后端以 UTC 存储（形如 2026-09-17T11:30:16.056886Z），
// 这里统一转换为浏览器本地时区后再展示，避免直接截断字符串导致显示成 UTC 时间。
function formatNoteTimestamp(value) {
  if (!value) {
    return "";
  }
  const normalized = String(value).replace(/(\.\d{3})\d+/, "$1");
  const date = new Date(normalized);
  if (Number.isNaN(date.getTime())) {
    return String(value).replace("T", " ").replace("Z", "").substring(0, 16);
  }
  const pad = (number) => String(number).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

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
            {formatNoteTimestamp(note.createdAt)}
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
  onCreateNote,
  onUpdateNote,
  onDeleteNote,
  noteImageContext = null,
  onSeek,
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
          <WorkspaceBackButton
            onClick={() => setViewState("list")}
            label="返回列表"
            variant="chevron"
            className="text-sm"
          />
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
          <WorkspaceBackButton
            onClick={() => { setViewState("list"); setIsEditing(false); }}
            label="返回列表"
            variant="chevron"
            className="text-sm"
          />
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
                  {formatNoteTimestamp(selectedNote.createdAt)}
                  {selectedNote.updatedAt !== selectedNote.createdAt && " (已编辑)"}
                </span>
              </div>
              <h1 className="mt-4 text-2xl font-bold text-stone-900 dark:text-stone-100">{selectedNote.title}</h1>
              <div className="my-5 h-px w-full bg-stone-100 dark:bg-stone-800/60" />
              <div className="markdown-body mt-2 text-sm text-stone-700 dark:text-stone-300">
                <WorkspaceMarkdownMessage content={selectedNote.content} noteImageContext={noteImageContext} onSeek={onSeek} />
              </div>
            </>
          )}
        </article>
      </div>
    );
  }

  // ========== 列表视图 (默认) ==========
  return (
    <div className="flex h-full flex-col gap-3 animate-in fade-in slide-in-from-left-4 duration-300 @[480px]:gap-5">
      <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2 px-2">
        <div className="min-w-[7rem] flex-1">
          <h2 className="text-lg font-bold text-stone-900 dark:text-stone-100">全部笔记</h2>
          <p className="mt-0.5 text-xs text-stone-600 dark:text-stone-400">共 {notes?.notes?.length || 0} 条记录</p>
        </div>
        <div className="ml-auto flex max-w-full flex-wrap justify-end gap-2">
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
        {(notes?.notes ?? []).length ? (
          <>
            {(notes?.notes ?? []).map((note) => (
              <NoteListItem key={note.id} note={note} onOpen={openDetail} />
            ))}
          </>
        ) : (
          <div className="mt-4">
            <WorkspaceStateBlock
              eyebrow="Notes"
              title="暂无笔记"
              description="记录个人要点、想法和待办。"
              dashed
            />
          </div>
        )}
      </div>
    </div>
  );
}
