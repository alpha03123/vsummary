import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ChatDrawer } from "@src/features/workspace/ui/ChatDrawer";

vi.mock("@src/features/workspace/ui/WorkspaceChatPanel", () => ({
  WorkspaceChatPanel: ({ workspaceTitle }) => <div data-testid="chat-panel">{workspaceTitle}</div>,
}));

describe("ChatDrawer", () => {
  const baseProps = {
    workspaceTitle: "我的工作台",
    onClose: vi.fn(),
  };

  it("renders nothing when closed", () => {
    render(<ChatDrawer isOpen={false} {...baseProps} />);
    expect(screen.queryByTestId("chat-panel")).toBeNull();
  });

  it("renders the chat panel when open and forwards workspaceTitle", () => {
    render(<ChatDrawer isOpen={true} {...baseProps} />);
    expect(screen.getByTestId("chat-panel")).toHaveTextContent("我的工作台");
  });

  it("calls onClose when the backdrop is clicked", () => {
    const onClose = vi.fn();
    render(<ChatDrawer isOpen={true} {...baseProps} onClose={onClose} />);
    // Backdrop is a div with the fixed inset-0 z-30 classes.
    const backdrop = document.querySelector("div.fixed.inset-0.z-30");
    expect(backdrop).toBeTruthy();
    fireEvent.click(backdrop);
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("calls onClose when Esc is pressed", () => {
    const onClose = vi.fn();
    render(<ChatDrawer isOpen={true} {...baseProps} onClose={onClose} />);
    fireEvent.keyDown(window, { key: "Escape" });
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("calls onClose when the ✕ button is clicked", () => {
    const onClose = vi.fn();
    render(<ChatDrawer isOpen={true} {...baseProps} onClose={onClose} />);
    fireEvent.click(screen.getByRole("button", { name: "关闭对话" }));
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("does not register an Esc listener when closed", () => {
    const onClose = vi.fn();
    render(<ChatDrawer isOpen={false} {...baseProps} onClose={onClose} />);
    fireEvent.keyDown(window, { key: "Escape" });
    expect(onClose).not.toHaveBeenCalled();
  });
});
