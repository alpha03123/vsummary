import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { WorkspaceToolbar } from "@src/features/workspace/ui/WorkspaceToolbar";

vi.mock("@src/features/workspace/model/workspaceApi", () => ({
  loadApplicationUpdateStatus: vi.fn(() => Promise.resolve({
    installationKind: "pack",
    currentVersion: "v0.3.10",
    updateAvailable: false,
  })),
}));

const baseProps = {
  activeSeries: { id: "s1", title: "我的系列" },
  onEnterLibraryHome: vi.fn(),
  settingsOpen: false,
  onToggleSettingsPanel: vi.fn(),
  isSidebarOpen: true,
  onToggleSidebar: vi.fn(),
  onToggleChatDrawer: vi.fn(),
  chatDrawerOpen: false,
};

describe("WorkspaceToolbar chat button", () => {
  it("calls onToggleChatDrawer when the chat button is clicked", () => {
    const onToggleChatDrawer = vi.fn();
    render(<WorkspaceToolbar {...baseProps} onToggleChatDrawer={onToggleChatDrawer} />);
    fireEvent.click(screen.getByRole("button", { name: "打开分析助手" }));
    expect(onToggleChatDrawer).toHaveBeenCalledTimes(1);
  });

  it("aria-expanded reflects chatDrawerOpen", () => {
    const { rerender } = render(<WorkspaceToolbar {...baseProps} chatDrawerOpen={false} />);
    expect(screen.getByRole("button", { name: "打开分析助手" })).toHaveAttribute("aria-expanded", "false");
    rerender(<WorkspaceToolbar {...baseProps} chatDrawerOpen={true} />);
    expect(screen.getByRole("button", { name: "打开分析助手" })).toHaveAttribute("aria-expanded", "true");
  });
});
