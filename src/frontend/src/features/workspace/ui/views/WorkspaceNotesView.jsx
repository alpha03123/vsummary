import { useState } from "react";
import { LoaderCircle, PencilLine, Trash2 } from "lucide-react";

import { WorkspaceStateBlock } from "../shared/WorkspaceStateBlock";

export function WorkspaceNotesView({
  notes,
  notesLoading,
  savingNote,
  onCreateNote,
  onUpdateNote,
  onDeleteNote,
}) {
  const [draftTitle, setDraftTitle] = useState("");
  const [draftContent, setDraftContent] = useState("");
  const [editingNoteId, setEditingNoteId] = useState(null);
  const [editingTitle, setEditingTitle] = useState("");
  const [editingContent, setEditingContent] = useState("");

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
  }

  function handleStartEdit(note) {
    setEditingNoteId(note.id);
    setEditingTitle(note.title);
    setEditingContent(note.content);
  }

  function handleCancelEdit() {
    setEditingNoteId(null);
    setEditingTitle("");
    setEditingContent("");
  }

  function handleSaveEdit() {
    if (!editingNoteId || !editingTitle.trim() || !editingContent.trim() || savingNote) {
      return;
    }
    onUpdateNote(editingNoteId, {
      title: editingTitle,
      content: editingContent,
    });
    handleCancelEdit();
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

  return (
    <div className="grid grid-cols-1 gap-5 xl:grid-cols-[0.92fr_1.08fr]">
      <section className="workspace-muted-panel rounded-[2rem] border p-6">
        <p className="text-xs font-bold uppercase tracking-widest text-stone-500 dark:text-stone-400">New Note</p>
        <h3 className="mt-3 text-2xl font-bold text-stone-900 dark:text-stone-100">手动记一条笔记</h3>
        <p className="mt-2 text-sm leading-relaxed text-stone-500 dark:text-stone-400">
          你可以自己记，也可以在左侧对话里直接让 Agent “帮我记一下”，它会自动落到这里。
        </p>
        <div className="mt-6 flex flex-col gap-4">
          <input
            value={draftTitle}
            onChange={(event) => setDraftTitle(event.target.value)}
            placeholder="笔记标题"
            className="rounded-2xl border border-stone-200/80 bg-white px-4 py-3 text-sm text-stone-900 outline-none transition focus:border-[#0070f3] dark:border-stone-800 dark:bg-stone-950 dark:text-stone-100"
          />
          <textarea
            value={draftContent}
            onChange={(event) => setDraftContent(event.target.value)}
            placeholder="记录要点、结论或待办..."
            className="min-h-[180px] rounded-3xl border border-stone-200/80 bg-white px-4 py-4 text-sm leading-relaxed text-stone-900 outline-none transition focus:border-[#0070f3] dark:border-stone-800 dark:bg-stone-950 dark:text-stone-100"
          />
          <button
            type="button"
            onClick={handleCreateNote}
            disabled={savingNote || !draftTitle.trim() || !draftContent.trim()}
            className="inline-flex items-center justify-center gap-2 rounded-2xl bg-stone-900 px-5 py-3 text-sm font-semibold text-white transition hover:bg-[#0070f3] disabled:cursor-not-allowed disabled:opacity-60 dark:bg-white dark:text-black"
          >
            {savingNote ? <LoaderCircle size={16} className="animate-spin" /> : <PencilLine size={16} />}
            保存笔记
          </button>
        </div>
      </section>

      <section className="flex flex-col gap-4">
        {(notes?.notes ?? []).length ? (
          notes.notes.map((note) => {
            const isEditing = editingNoteId === note.id;
            return (
              <article key={note.id} className="workspace-elevated-panel rounded-[2rem] border p-6">
                <div className="flex items-start justify-between gap-4">
                  <div>
                    <p className="text-[10px] font-bold uppercase tracking-widest text-stone-500 dark:text-stone-400">
                      {note.source === "agent" ? "Agent Note" : "Manual Note"}
                    </p>
                    {isEditing ? (
                      <input
                        value={editingTitle}
                        onChange={(event) => setEditingTitle(event.target.value)}
                        className="mt-2 w-full rounded-2xl border border-stone-200/80 bg-white px-4 py-3 text-base font-semibold text-stone-900 outline-none transition focus:border-[#0070f3] dark:border-stone-800 dark:bg-stone-950 dark:text-stone-100"
                      />
                    ) : (
                      <h3 className="mt-2 text-lg font-bold text-stone-900 dark:text-stone-100">{note.title}</h3>
                    )}
                    <p className="mt-2 text-xs text-stone-500 dark:text-stone-400">
                      创建于 {note.createdAt.replace("T", " ").replace("Z", "")}
                      {note.updatedAt !== note.createdAt ? ` · 更新于 ${note.updatedAt.replace("T", " ").replace("Z", "")}` : ""}
                    </p>
                  </div>
                  <div className="flex items-center gap-2">
                    {isEditing ? (
                      <>
                        <button
                          type="button"
                          onClick={handleSaveEdit}
                          disabled={savingNote || !editingTitle.trim() || !editingContent.trim()}
                          className="rounded-2xl bg-stone-900 px-3 py-2 text-xs font-semibold text-white transition hover:bg-[#0070f3] disabled:cursor-not-allowed disabled:opacity-60 dark:bg-white dark:text-black"
                        >
                          保存
                        </button>
                        <button
                          type="button"
                          onClick={handleCancelEdit}
                          className="rounded-2xl border border-stone-200/80 px-3 py-2 text-xs font-semibold text-stone-600 transition hover:bg-stone-50 dark:border-stone-800 dark:text-stone-300 dark:hover:bg-stone-900"
                        >
                          取消
                        </button>
                      </>
                    ) : (
                      <>
                        <button
                          type="button"
                          onClick={() => handleStartEdit(note)}
                          className="rounded-2xl border border-stone-200/80 px-3 py-2 text-xs font-semibold text-stone-600 transition hover:bg-stone-50 dark:border-stone-800 dark:text-stone-300 dark:hover:bg-stone-900"
                        >
                          编辑
                        </button>
                        <button
                          type="button"
                          onClick={() => onDeleteNote(note.id)}
                          disabled={savingNote}
                          className="rounded-2xl border border-red-200/80 px-3 py-2 text-xs font-semibold text-red-700 transition hover:bg-red-50 disabled:cursor-not-allowed disabled:opacity-60 dark:border-red-900/70 dark:text-red-300 dark:hover:bg-red-950/30"
                        >
                          <Trash2 size={14} />
                        </button>
                      </>
                    )}
                  </div>
                </div>

                {isEditing ? (
                  <textarea
                    value={editingContent}
                    onChange={(event) => setEditingContent(event.target.value)}
                    className="mt-4 min-h-[160px] w-full rounded-3xl border border-stone-200/80 bg-white px-4 py-4 text-sm leading-relaxed text-stone-900 outline-none transition focus:border-[#0070f3] dark:border-stone-800 dark:bg-stone-950 dark:text-stone-100"
                  />
                ) : (
                  <p className="mt-4 whitespace-pre-wrap text-sm leading-relaxed text-stone-700 dark:text-stone-300">{note.content}</p>
                )}
              </article>
            );
          })
        ) : (
          <WorkspaceStateBlock
            eyebrow="Notes"
            title="这里还没有笔记"
            description="可以手动新增，也可以直接对 Agent 说“帮我记一下这个视频的重点”。"
            dashed
          />
        )}
      </section>
    </div>
  );
}
