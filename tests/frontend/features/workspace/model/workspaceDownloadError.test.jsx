import { fireEvent, render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import { WorkspacePage } from "@workspace/workspace/ui/WorkspacePage";
import { buildWorkspacePageModel } from "@workspace/workspace/ui/workspacePageModel";
import { createInitialWorkspaceState } from "@workspace/workspace/model/workspaceState";
import { workspaceReducer } from "@workspace/workspace/model/workspaceReducer";

vi.mock("@workspace/runtime/WorkspaceProvider", () => ({ useWorkspaceRuntime: () => ({ api: {}, host: {} }) }));
vi.mock("@workspace/workspace/ui/WorkspaceLibraryHomePane", () => ({ WorkspaceLibraryHomePane: () => null }));

it("shows a failed unselected video globally and lets the user dismiss it", () => {
  const initial = { ...createInitialWorkspaceState(), backendReady: true, loading: false,
    library: { workspace: { id: "workspace", title: "Library" }, series: [] } };
  const failed = workspaceReducer(initial, { type: "video_download_failed", seriesId: "series-a",
    videoId: "unselected-video", error: "Platform rejected this session" });
  const refreshed = workspaceReducer(failed, { type: "tools_loaded", tools: null });
  const clear = vi.fn();
  const page = (state) => buildWorkspacePageModel({ state, ui: state.ui, selectedContextType: "library",
    activeSeries: null, onClearError: clear, fasterWhisperModels: [] });
  const { rerender } = render(<WorkspacePage page={page(refreshed)} />);
  expect(screen.getByRole("alert")).toHaveTextContent("Platform rejected this session");
  fireEvent.click(screen.getByRole("button", { name: "关闭错误提示" }));
  expect(clear).toHaveBeenCalledOnce();
  rerender(<WorkspacePage page={page(workspaceReducer(refreshed, { type: "error_cleared" }))} />);
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
});
