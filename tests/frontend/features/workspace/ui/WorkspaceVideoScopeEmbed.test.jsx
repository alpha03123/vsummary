import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { isVideoScopeMessage, WorkspaceVideoScopeEmbed } from "@src/features/workspace/ui/WorkspaceVideoScopeEmbed";
import { useWorkspaceController } from "@src/features/workspace/model/useWorkspaceController";
import { createInitialWorkspaceState } from "@src/features/workspace/model/workspaceState";

vi.mock("@src/features/workspace/model/useWorkspaceController", () => ({ useWorkspaceController: vi.fn() }));
vi.mock("@src/features/workspace/ui/WorkspaceVideoScopePane", () => ({
  WorkspaceVideoScopePane: () => <div data-testid="video-scope-pane" />,
}));
vi.mock("@src/features/workspace/ui/ChatDrawer", () => ({ ChatDrawer: () => null }));

function selectTarget(part = 1) {
  window.history.replaceState(null, "", `/?embed=video-scope&bilibili_url=${encodeURIComponent(`https://www.bilibili.com/video/BV1example?p=${part}`)}`);
}

function makeController({ linked = true, part = 1 } = {}) {
  const video = { id: "video-1", title: "Current video", sourceId: "BV1example", itemIndex: part, isLinked: linked, status: linked ? "linked" : "ready", processed: !linked };
  const series = { id: "inbox-1", title: "B站导入", kind: "bilibili_inbox", videos: [video] };
  const state = { ...createInitialWorkspaceState(), library: { workspace: { id: "workspace-1", title: "Workspace" }, series: [series] } };
  const controller = {
    state, activeSeries: series, selectedVideo: video, selectedContextType: "video",
    onSelectVideo: vi.fn(), onResolveBilibiliInboxVideo: vi.fn(), onProcessLinkedVideo: vi.fn(), onCancelGeneration: vi.fn(),
  };
  useWorkspaceController.mockReturnValue(controller);
  return controller;
}

beforeEach(() => {
  vi.clearAllMocks();
  selectTarget();
});

afterEach(() => window.history.replaceState(null, "", "/"));

describe("WorkspaceVideoScopeEmbed", () => {
  it.each([1, 2])("opens a linked video at part %i with a processing action", (part) => {
    selectTarget(part);
    const controller = makeController({ part });
    render(<WorkspaceVideoScopeEmbed />);

    fireEvent.click(screen.getByRole("button", { name: "下载并生成" }));

    expect(controller.onSelectVideo).toHaveBeenCalledWith("inbox-1", "video-1");
    expect(controller.onResolveBilibiliInboxVideo).not.toHaveBeenCalled();
    expect(controller.onProcessLinkedVideo).toHaveBeenCalledOnce();
    expect(screen.queryByTestId("video-scope-pane")).not.toBeInTheDocument();
  });

  it("disables another processing request while the durable job is active", () => {
    const controller = makeController();
    controller.currentGenerationTask = { snapshot: { status: "running", stage: "download", progress: 10 } };
    render(<WorkspaceVideoScopeEmbed />);

    expect(screen.getByRole("button", { name: "正在处理视频" })).toBeDisabled();
    expect(controller.onProcessLinkedVideo).not.toHaveBeenCalled();
  });

  it("shows processing failures instead of leaving an inactive loading state", () => {
    const controller = makeController();
    controller.state.error = "Injected download failure";
    render(<WorkspaceVideoScopeEmbed />);

    expect(screen.getByRole("alert")).toHaveTextContent("Injected download failure");
    expect(screen.getByRole("button", { name: "下载并生成" })).toBeEnabled();
  });

  it("opens the tool workspace after the linked video becomes local", () => {
    const controller = makeController();
    const { rerender } = render(<WorkspaceVideoScopeEmbed />);
    const downloaded = { ...controller.selectedVideo, isLinked: false, status: "ready", processed: true };
    useWorkspaceController.mockReturnValue({ ...controller, selectedVideo: downloaded, activeSeries: { ...controller.activeSeries, videos: [downloaded] } });
    rerender(<WorkspaceVideoScopeEmbed />);

    expect(screen.getByTestId("video-scope-pane")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "下载并生成" })).not.toBeInTheDocument();
  });
});

describe("isVideoScopeMessage", () => {
  it("accepts context updates and seek results from the embedding extension", () => {
    const parentWindow = window.parent;

    expect(isVideoScopeMessage({
      source: parentWindow,
      origin: "chrome-extension://extension-id",
      data: { type: "vsummary:set-video-context" },
    })).toBe(true);
    expect(isVideoScopeMessage({
      source: parentWindow,
      origin: "chrome-extension://extension-id",
      data: { type: "vsummary:seek-result", ok: false },
    })).toBe(true);
  });

  it("rejects messages that do not originate from the embedding extension", () => {
    expect(isVideoScopeMessage({
      source: window,
      origin: "http://127.0.0.1:4173",
      data: { type: "vsummary:seek-result" },
    })).toBe(false);
  });
});
