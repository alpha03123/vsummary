import { act, renderHook } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { useWorkspaceController } from "@src/features/workspace/model/useWorkspaceController";

describe("useWorkspaceController.onSeekToTime", () => {
  it("dispatches player_seek_requested with the provided payload", () => {
    const { result } = renderHook(() => useWorkspaceController());
    act(() => {
      result.current.onSeekToTime({ seconds: 42.5, endSeconds: 50, chapterTitle: "Intro" });
    });
    expect(result.current.playerSeekRequest).toMatchObject({
      seconds: 42.5,
      endSeconds: 50,
      chapterTitle: "Intro",
    });
    expect(typeof result.current.playerSeekRequest.requestId).toBe("number");
  });

  it("defaults endSeconds to null and chapterTitle to empty string", () => {
    const { result } = renderHook(() => useWorkspaceController());
    act(() => {
      result.current.onSeekToTime({ seconds: 10 });
    });
    expect(result.current.playerSeekRequest).toMatchObject({
      seconds: 10,
      endSeconds: null,
      chapterTitle: "",
    });
  });

  it("early-returns on non-finite seconds", () => {
    const { result } = renderHook(() => useWorkspaceController());
    act(() => {
      result.current.onSeekToTime({ seconds: NaN });
    });
    expect(result.current.playerSeekRequest).toBeNull();
  });

  it("early-returns when called with no argument", () => {
    const { result } = renderHook(() => useWorkspaceController());
    act(() => {
      result.current.onSeekToTime();
    });
    expect(result.current.playerSeekRequest).toBeNull();
  });
});

describe("useWorkspaceController chat-drawer actions", () => {
  it("onToggleChatDrawer flips chatDrawerOpen", () => {
    const { result } = renderHook(() => useWorkspaceController());
    expect(result.current.chatDrawerOpen).toBe(false);
    act(() => result.current.onToggleChatDrawer());
    expect(result.current.chatDrawerOpen).toBe(true);
    act(() => result.current.onToggleChatDrawer());
    expect(result.current.chatDrawerOpen).toBe(false);
  });

  it("onOpenChatDrawer and onCloseChatDrawer set the field", () => {
    const { result } = renderHook(() => useWorkspaceController());
    act(() => result.current.onOpenChatDrawer());
    expect(result.current.chatDrawerOpen).toBe(true);
    act(() => result.current.onCloseChatDrawer());
    expect(result.current.chatDrawerOpen).toBe(false);
  });
});
