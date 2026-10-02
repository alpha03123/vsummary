import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { WorkspaceVideoScopePane } from "@src/features/workspace/ui/WorkspaceVideoScopePane";

vi.mock("@src/features/workspace/ui/WorkspaceReadingPane", () => ({
  WorkspaceReadingPane: ({ onSeek, onOpenCitationReference }) => (
    <>
      <button type="button" onClick={() => onSeek({ seconds: 12, endSeconds: 15, chapterTitle: "逐字稿" })}>逐字稿跳转</button>
      <button type="button" onClick={() => onOpenCitationReference({ seconds: 42, endSeconds: 45, chapterTitle: "AI 引用" })}>引用跳转</button>
    </>
  ),
}));

function renderPane(onExternalSeek = vi.fn()) {
  const openCitationReference = vi.fn();
  const page = {
    shell: {
      selectedVideo: { id: "video-1" },
      player: { seekToTime: vi.fn() },
      state: {},
    },
    generation: {},
    actions: {},
    chat: { openCitationReference },
  };
  render(<WorkspaceVideoScopePane page={page} onExternalSeek={onExternalSeek} />);
  return { openCitationReference, onExternalSeek };
}

describe("WorkspaceVideoScopePane external seeks", () => {
  it("forwards transcript segment clicks to the Bilibili player", () => {
    const { openCitationReference, onExternalSeek } = renderPane();

    fireEvent.click(screen.getByRole("button", { name: "逐字稿跳转" }));

    expect(openCitationReference).toHaveBeenCalledWith({
      videoId: "video-1",
      seconds: 12,
      endSeconds: 15,
      chapterTitle: "逐字稿",
    });
    expect(onExternalSeek).toHaveBeenCalledWith(expect.objectContaining({ seconds: 12 }));
  });

  it("forwards AI citation and image references to the Bilibili player", () => {
    const { openCitationReference, onExternalSeek } = renderPane();

    fireEvent.click(screen.getByRole("button", { name: "引用跳转" }));

    expect(openCitationReference).toHaveBeenCalledWith({ seconds: 42, endSeconds: 45, chapterTitle: "AI 引用" });
    expect(onExternalSeek).toHaveBeenCalledWith({ seconds: 42, endSeconds: 45, chapterTitle: "AI 引用" });
  });

});
