import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { WorkspaceChatPanel } from "./WorkspaceChatPanel";

describe("WorkspaceChatPanel", () => {
  it("renders assistant messages as markdown", () => {
    render(
      <WorkspaceChatPanel
        activeSeries={{ id: "series-a", title: "Series A" }}
        selectedVideo={{ id: "video-1", title: "Video 1" }}
        selectedContextType="video"
        selectedToolId="overview"
        tools={{ aiTodo: "AI 已接入。" }}
        chatMessages={[
          {
            id: "assistant-1",
            role: "assistant",
            content: "# 标题\n\n- 第一项\n- 第二项\n\n这是 **重点**，还有 [文档](https://example.com)。",
            meta: "Notebook Assistant • Just now",
          },
        ]}
        chatPending={false}
        onSubmitChat={() => {}}
      />,
    );

    expect(screen.getByRole("heading", { name: "标题" })).toBeInTheDocument();
    expect(screen.getByText("第一项")).toBeInTheDocument();
    expect(screen.getByText("重点")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "文档" })).toHaveAttribute("href", "https://example.com");
    expect(screen.getByText("NotebookLM 助手")).toBeInTheDocument();
    expect(screen.getByText("AI概况")).toBeInTheDocument();
    expect(screen.queryByText("上下文：")).not.toBeInTheDocument();
  });

  it("allows library-scope chat without selecting a series", () => {
    const onSubmitChat = vi.fn();

    render(
      <WorkspaceChatPanel
        workspaceTitle="Video Include"
        activeSeries={null}
        selectedVideo={null}
        selectedContextType="library"
        selectedToolId="studio"
        tools={null}
        chatMessages={[
          {
            id: "assistant-1",
            role: "assistant",
            content: "你好，这里是整个知识库。",
            meta: "Notebook Assistant • Just now",
          },
        ]}
        chatPending={false}
        onSubmitChat={onSubmitChat}
      />,
    );

    expect(screen.getByText("NotebookLM 助手")).toBeInTheDocument();
    expect(screen.getByText("工具首页")).toBeInTheDocument();
    expect(screen.getByText("基于《Video Include》")).toBeInTheDocument();

    fireEvent.change(screen.getByPlaceholderText("提问或下达指令..."), {
      target: { value: "帮我找一下入门视频" },
    });
    const buttons = screen.getAllByRole("button");
    fireEvent.click(buttons[buttons.length - 1]);

    expect(onSubmitChat).toHaveBeenCalledWith("帮我找一下入门视频");
  });
});
