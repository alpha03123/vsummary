import { WorkspaceNotesView } from "@workspace/workspace/ui/views/WorkspaceNotesView";
import { render } from "@src/testing/renderWorkspace";
import { fireEvent, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

const note = {
  id: "note-1",
  title: "待删除笔记",
  content: "笔记内容",
  source: "manual",
  createdAt: "2026-09-27T12:00:00Z",
  updatedAt: "2026-09-27T12:00:00Z",
};

describe("WorkspaceNotesView", () => {
  it("requires confirmation before deleting a manual note", () => {
    const onDeleteNote = vi.fn();
    render(
      <WorkspaceNotesView
        notes={{ notes: [note] }}
        notesLoading={false}
        savingNote={false}
        onCreateNote={vi.fn()}
        onUpdateNote={vi.fn()}
        onDeleteNote={onDeleteNote}
      />,
    );

    fireEvent.click(screen.getByText("待删除笔记"));
    fireEvent.click(screen.getByRole("button", { name: "删除笔记" }));

    expect(screen.getByText("删除这条笔记？")).toBeInTheDocument();
    expect(onDeleteNote).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: "确认删除" }));

    expect(onDeleteNote).toHaveBeenCalledWith("note-1");
  });
});
