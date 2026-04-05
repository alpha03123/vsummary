import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { WorkspaceChatPanel } from "./WorkspaceChatPanel";

describe("WorkspaceChatPanel", () => {
  it("renders assistant messages as markdown", async () => {
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

    expect(await screen.findByRole("heading", { name: "标题" })).toBeInTheDocument();
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

  it("renders tool traces as a collapsed expandable block with actual tool names", async () => {
    render(
      <WorkspaceChatPanel
        workspaceTitle="Video Include"
        activeSeries={{ id: "series-a", title: "Series A" }}
        selectedVideo={null}
        selectedContextType="series"
        selectedToolId="series-home"
        tools={null}
        chatMessages={[
          {
            id: "tool-trace-1",
            role: "assistant",
            kind: "tool-trace",
            content: "已调用 2 个工具",
            toolTrace: {
              durationMs: 1200,
              steps: [
                {
                  toolName: "list_series_videos",
                  label: "读取系列视频列表",
                  target: "Series A",
                },
                {
                  toolName: "get_video_summary",
                  label: "读取视频概况",
                  target: "Video 1",
                },
              ],
            },
            meta: "Notebook Assistant • Tool Chain",
          },
        ]}
        chatPending={false}
        onSubmitChat={() => {}}
      />,
    );

    expect(screen.getByText("已调用 2 个工具")).toBeInTheDocument();
    expect(screen.getByText("用时 1.2秒")).toBeInTheDocument();

    fireEvent.click(screen.getByText("已调用 2 个工具"));

    expect(await screen.findByText("list_series_videos")).toBeInTheDocument();
    expect(screen.getByText("get_video_summary")).toBeInTheDocument();
    expect(screen.getByText("读取系列视频列表")).toBeInTheDocument();
    expect(screen.getByText("读取视频概况")).toBeInTheDocument();
  });
});
