import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { WorkspaceChatPanel } from "@src/features/workspace/ui/WorkspaceChatPanel";

describe("WorkspaceChatPanel", () => {
  it("allows chat for a video before its AI overview is generated", () => {
    const onSubmitChat = vi.fn();
    render(
      <WorkspaceChatPanel
        workspaceTitle="我的工作台"
        activeSeries={{ id: "series-1", title: "课程" }}
        selectedVideo={{ id: "video-2", title: "第二讲", processed: false }}
        selectedContextType="video"
        selectedToolId="studio"
        chatMessages={[]}
        onSubmitChat={onSubmitChat}
      />,
    );

    const composer = screen.getByPlaceholderText("向 AI 助手提问或下达指令...");
    expect(composer).toBeEnabled();
    fireEvent.change(composer, { target: { value: "当前视频处理到哪一步了？" } });
    fireEvent.keyDown(composer, { key: "Enter" });

    expect(onSubmitChat).toHaveBeenCalledWith("当前视频处理到哪一步了？");
  });
});

describe("WorkspaceChatPanel composer", () => {
  const composerProps = {
    workspaceTitle: "我的工作台",
    activeSeries: { id: "series-1", title: "课程" },
    selectedVideo: { id: "video-2", title: "第二讲", processed: true },
    selectedContextType: "video",
    selectedToolId: "studio",
    chatMessages: [],
    onSubmitChat: vi.fn(),
  };

  it("starts compact and grows with the draft", () => {
    const onDraftChange = vi.fn();
    const { rerender } = render(
      <WorkspaceChatPanel {...composerProps} draft="" onDraftChange={onDraftChange} />,
    );

    const composer = screen.getByPlaceholderText("向 AI 助手提问或下达指令...");
    // Fixed 100px used to be reserved even when empty; it is now content-driven.
    expect(composer.className).toContain("min-h-[44px]");
    expect(composer.className).toContain("max-h-40");
    expect(composer.className).not.toContain("h-[100px]");
    expect(composer).toHaveValue("");

    rerender(
      <WorkspaceChatPanel
        {...composerProps}
        draft={"第一行\n第二行\n第三行"}
        onDraftChange={onDraftChange}
      />,
    );

    expect(screen.getByPlaceholderText("向 AI 助手提问或下达指令...")).toHaveValue(
      "第一行\n第二行\n第三行",
    );
  });

  it("drops the idle hint row but keeps locked-state explanations", () => {
    const { rerender } = render(<WorkspaceChatPanel {...composerProps} />);

    expect(
      screen.queryByText("AI 已接入当前工作区上下文，可返回证据卡片与工具联动动作"),
    ).not.toBeInTheDocument();

    rerender(<WorkspaceChatPanel {...composerProps} summaryLocked />);

    expect(screen.getByText("生成 AI 概况后，这里会恢复对话")).toBeInTheDocument();
  });

  it("disables the composer and swaps the placeholder while locked", () => {
    render(<WorkspaceChatPanel {...composerProps} summaryLocked />);

    const composer = screen.getByPlaceholderText("请先生成 AI 概况...");
    expect(composer).toBeDisabled();
  });
});

describe("WorkspaceChatPanel session switcher", () => {
  const baseProps = {
    workspaceTitle: "我的工作台",
    activeSeries: { id: "series-1", title: "课程" },
    selectedVideo: { id: "video-2", title: "第二讲", processed: true },
    selectedContextType: "video",
    selectedToolId: "studio",
    chatMessages: [],
    onSubmitChat: vi.fn(),
  };

  it("groups the session switcher and the new-chat action together", () => {
    const onStartNewChat = vi.fn();
    render(
      <WorkspaceChatPanel
        {...baseProps}
        chatSessions={[
          { id: "session-1", title: "当前对话" },
          { id: "session-2", title: "新对话 2" },
        ]}
        activeSessionId="session-1"
        onSelectChatSession={vi.fn()}
        onStartNewChat={onStartNewChat}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "新建话题" }));

    expect(onStartNewChat).toHaveBeenCalledTimes(1);
  });

  it("switches sessions from the dropdown", () => {
    const onSelectChatSession = vi.fn();
    render(
      <WorkspaceChatPanel
        {...baseProps}
        chatSessions={[
          { id: "session-1", title: "当前对话" },
          { id: "session-2", title: "新对话 2" },
        ]}
        activeSessionId="session-1"
        onSelectChatSession={onSelectChatSession}
        onStartNewChat={vi.fn()}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "切换对话" }));
    fireEvent.click(screen.getByRole("option", { name: "新对话 2" }));

    expect(onSelectChatSession).toHaveBeenCalledWith("session-2");
  });

  it("opens the session list without the segmented shell clipping it", () => {
    render(
      <WorkspaceChatPanel
        {...baseProps}
        chatSessions={[
          { id: "session-1", title: "帮我生成一份笔记" },
          { id: "session-2", title: "新对话 2" },
        ]}
        activeSessionId="session-1"
        onSelectChatSession={vi.fn()}
        onStartNewChat={vi.fn()}
      />,
    );

    // The shortcut menu must be reachable: an `overflow-hidden` wrapper around
    // the switcher would clip this absolutely positioned list.
    expect(screen.queryByRole("listbox")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "切换对话" }));

    const listbox = screen.getByRole("listbox");
    expect(listbox).toBeInTheDocument();
    expect(screen.getAllByRole("option")).toHaveLength(2);
    expect(screen.getByRole("option", { name: "帮我生成一份笔记" })).toHaveAttribute(
      "aria-selected",
      "true",
    );
    expect(listbox.closest(".overflow-hidden")).toBeNull();
  });

  it("closes the session list when clicking outside", () => {
    render(
      <WorkspaceChatPanel
        {...baseProps}
        chatSessions={[
          { id: "session-1", title: "当前对话" },
          { id: "session-2", title: "新对话 2" },
        ]}
        activeSessionId="session-1"
        onSelectChatSession={vi.fn()}
        onStartNewChat={vi.fn()}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "切换对话" }));
    expect(screen.getByRole("listbox")).toBeInTheDocument();

    // The shared hook only closes when a gesture both starts AND ends outside.
    fireEvent.pointerDown(document.body);
    fireEvent.pointerUp(document.body);

    expect(screen.queryByRole("listbox")).not.toBeInTheDocument();
  });

  it("shows the active session title on the trigger", () => {
    render(
      <WorkspaceChatPanel
        {...baseProps}
        chatSessions={[
          { id: "session-1", title: "帮我生成一份笔记" },
          { id: "session-2", title: "新对话 2" },
        ]}
        activeSessionId="session-1"
        onSelectChatSession={vi.fn()}
        onStartNewChat={vi.fn()}
      />,
    );

    expect(screen.getByRole("button", { name: "切换对话" })).toHaveTextContent("帮我生成一份笔记");
  });

  it("offers a labelled new-chat button when there is no session list yet", () => {
    const onStartNewChat = vi.fn();
    render(
      <WorkspaceChatPanel
        {...baseProps}
        chatSessions={[]}
        activeSessionId={null}
        onStartNewChat={onStartNewChat}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "新对话" }));

    expect(onStartNewChat).toHaveBeenCalledTimes(1);
  });
});
