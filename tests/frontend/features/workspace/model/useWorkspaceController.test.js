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
    expect(typeof result.current.playerSeekRequest.requestId).toBe("string");
    expect(result.current.playerSeekRequest.requestId).toMatch(/^\d+-\d+(\.\d+)?$/);
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

  it("seeks the video when a mindmap node is focused", () => {
    const { result } = renderHook(() => useWorkspaceController());
    act(() => {
      result.current.onFocusNode({
        id: "mindmap-node",
        title: "接口创建",
        start_seconds: 42.5,
        end_seconds: 55,
      });
    });

    expect(result.current.playerSeekRequest).toMatchObject({
      seconds: 42.5,
      endSeconds: 55,
      chapterTitle: "接口创建",
    });
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

describe("useWorkspaceController external import actions", () => {
  it("exposes Bilibili cookie initialization to the page model", () => {
    const { result } = renderHook(() => useWorkspaceController());

    expect(typeof result.current.onInitBilibiliCookie).toBe("function");
  });
});
