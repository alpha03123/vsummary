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
        chatSessions={[]}
        activeSessionId={null}
        contextUsage={null}
        contextUsageLoading={false}
        onStartNewChat={() => {}}
        onSelectChatSession={() => {}}
        onOpenSeekReference={() => {}}
        onClearChat={() => {}}
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

  it("allows series-scope chat without selecting a video", () => {
    const onSubmitChat = vi.fn();

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
            id: "assistant-1",
            role: "assistant",
            content: "你好，这里是当前系列。",
            meta: "Notebook Assistant • Just now",
          },
        ]}
        chatPending={false}
        chatSessions={[]}
        activeSessionId={null}
        contextUsage={null}
        contextUsageLoading={false}
        onStartNewChat={() => {}}
        onSelectChatSession={() => {}}
        onOpenSeekReference={() => {}}
        onClearChat={() => {}}
        onSubmitChat={onSubmitChat}
      />,
    );

    expect(screen.getByText("NotebookLM 助手")).toBeInTheDocument();
    expect(screen.getByText("系列首页")).toBeInTheDocument();
    expect(screen.getByText("基于《Series A》")).toBeInTheDocument();

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
        chatSessions={[]}
        activeSessionId={null}
        contextUsage={null}
        contextUsageLoading={false}
        onStartNewChat={() => {}}
        onSelectChatSession={() => {}}
        onOpenSeekReference={() => {}}
        onClearChat={() => {}}
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

  it("renders streaming thought summary and hides the running badge after tool steps settle", async () => {
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
            id: "thought-1",
            role: "assistant",
            kind: "thought-trace",
            content: "思考中",
            thoughtTrace: {
              status: "running",
              summary: "先读取系列视频，再读取视频概况。",
            },
            meta: "Notebook Assistant • 思考中",
          },
          {
            id: "tool-trace-1",
            role: "assistant",
            kind: "tool-trace",
            content: "已调用 1 个工具",
            toolTrace: {
              status: "idle",
              steps: [
                {
                  toolName: "list_series_videos",
                  label: "读取系列视频列表",
                  target: "Series A",
                  status: "completed",
                },
              ],
            },
            meta: "Notebook Assistant • 等待下一步",
          },
        ]}
        chatPending={false}
        chatSessions={[]}
        activeSessionId={null}
        contextUsage={null}
        contextUsageLoading={false}
        onStartNewChat={() => {}}
        onSelectChatSession={() => {}}
        onOpenSeekReference={() => {}}
        onClearChat={() => {}}
        onSubmitChat={() => {}}
      />,
    );

    expect(screen.getByText("思考中")).toBeInTheDocument();
    expect(screen.getByText("先读取系列视频，再读取视频概况。")).toBeInTheDocument();
    expect(screen.getByText("正在分析当前问题与上下文，思路会实时展开")).toBeInTheDocument();
    expect(screen.getByText("当前这一步已完成，等待下一步规划")).toBeInTheDocument();
    expect(screen.queryByText("调用中")).not.toBeInTheDocument();
  });

  it("renders graph stage cards with aliases and per-stage durations", () => {
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
            id: "thought-1",
            role: "assistant",
            kind: "thought-trace",
            content: "执行完成",
            thoughtTrace: {
              status: "completed",
              durationMs: 42,
              stages: [
                {
                  id: "stage-1",
                  nodeId: "decompose",
                  label: "拆解任务",
                  status: "completed",
                  durationMs: 12,
                },
                {
                  id: "stage-2",
                  nodeId: "build_plan",
                  label: "生成计划",
                  status: "completed",
                  durationMs: 30,
                },
              ],
            },
            meta: "Notebook Assistant • 执行用时 42ms",
          },
        ]}
        chatPending={false}
        chatSessions={[]}
        activeSessionId={null}
        contextUsage={null}
        contextUsageLoading={false}
        onStartNewChat={() => {}}
        onSelectChatSession={() => {}}
        onOpenSeekReference={() => {}}
        onClearChat={() => {}}
        onSubmitChat={() => {}}
      />,
    );

    expect(screen.getByText("执行完成")).toBeInTheDocument();
    expect(screen.getByText("拆解任务")).toBeInTheDocument();
    expect(screen.getByText("生成计划")).toBeInTheDocument();
    expect(screen.getAllByText(/用时/).length).toBeGreaterThanOrEqual(2);
    expect(screen.getAllByText("已完成").length).toBeGreaterThanOrEqual(2);
  });

  it("renders context budget with source breakdown", () => {
    render(
      <WorkspaceChatPanel
        workspaceTitle="Video Include"
        activeSeries={{ id: "series-a", title: "Series A" }}
        selectedVideo={{ id: "video-1", title: "Video 1" }}
        selectedContextType="video"
        selectedToolId="overview"
        tools={null}
        chatMessages={[]}
        chatPending={false}
        chatSessions={[]}
        activeSessionId={null}
        contextUsage={{
          sessionId: "video|series-a|video-1|overview",
          scopeType: "video",
          memoryKey: "series|series-a",
          estimatedTotalTokens: 3200,
          windowTokens: 200000,
          reservedOutputTokens: 20000,
          warningThresholdTokens: 120000,
          compactThresholdTokens: 160000,
          blockingThresholdTokens: 184000,
          remainingTokens: 196800,
          usagePercent: 1.6,
          level: "normal",
          sources: [
            { id: "system_prompt", label: "系统指令", estimatedTokens: 2100 },
            { id: "recent_messages", label: "最近消息", estimatedTokens: 400 },
            { id: "tool_results", label: "工具结果", estimatedTokens: 0 },
            { id: "workspace_context", label: "工作区上下文", estimatedTokens: 700 },
          ],
        }}
        contextUsageLoading={false}
        onStartNewChat={() => {}}
        onSelectChatSession={() => {}}
        onOpenSeekReference={() => {}}
        onClearChat={() => {}}
        onSubmitChat={() => {}}
      />,
    );

    expect(screen.getByText("上下文预算")).toBeInTheDocument();
    expect(screen.getByText("预算充足")).toBeInTheDocument();
    expect(screen.getByText("系统指令 2.1k")).toBeInTheDocument();
    expect(screen.getByText("最近消息 400")).toBeInTheDocument();
    expect(screen.getByText("工作区上下文 700")).toBeInTheDocument();
  });

  it("exposes new chat and clear chat actions", () => {
    const onStartNewChat = vi.fn();
    const onClearChat = vi.fn();
    const onSelectChatSession = vi.fn();

    render(
      <WorkspaceChatPanel
        workspaceTitle="Video Include"
        activeSeries={{ id: "series-a", title: "Series A" }}
        selectedVideo={null}
        selectedContextType="series"
        selectedToolId="series-home"
        tools={null}
        chatMessages={[]}
        chatSessions={[]}
        activeSessionId={null}
        chatPending={false}
        contextUsage={null}
        contextUsageLoading={false}
        onStartNewChat={onStartNewChat}
        onSelectChatSession={onSelectChatSession}
        onOpenSeekReference={() => {}}
        onClearChat={onClearChat}
        onSubmitChat={() => {}}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "新建对话" }));
    fireEvent.click(screen.getByRole("button", { name: "清空当前对话" }));

    expect(onStartNewChat).toHaveBeenCalled();
    expect(onClearChat).toHaveBeenCalled();
    expect(onSelectChatSession).not.toHaveBeenCalled();
  });

  it("renders session chips and allows switching sessions", () => {
    const onSelectChatSession = vi.fn();

    render(
      <WorkspaceChatPanel
        workspaceTitle="Video Include"
        activeSeries={{ id: "series-a", title: "Series A" }}
        selectedVideo={null}
        selectedContextType="series"
        selectedToolId="series-home"
        tools={null}
        chatMessages={[]}
        chatSessions={[
          { id: "series|series-a|series-home", title: "当前对话" },
          { id: "series|series-a|series-home::2", title: "JManus 是啥？" },
        ]}
        activeSessionId="series|series-a|series-home::2"
        chatPending={false}
        contextUsage={null}
        contextUsageLoading={false}
        onStartNewChat={() => {}}
        onSelectChatSession={onSelectChatSession}
        onOpenSeekReference={() => {}}
        onClearChat={() => {}}
        onSubmitChat={() => {}}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "当前对话" }));
    expect(onSelectChatSession).toHaveBeenCalledWith("series|series-a|series-home");
    expect(screen.getByRole("button", { name: "JManus 是啥？" })).toBeInTheDocument();
  });

  it("renders a collapsible seek evidence card and opens preview on demand", () => {
    const onOpenSeekReference = vi.fn();

    render(
      <WorkspaceChatPanel
        workspaceTitle="Video Include"
        activeSeries={{ id: "series-a", title: "Series A" }}
        selectedVideo={{ id: "video-1", title: "Video 1" }}
        selectedContextType="video"
        selectedToolId="studio"
        tools={null}
        chatMessages={[
          {
            id: "seek-reference-1",
            role: "assistant",
            kind: "seek-reference",
            content: "已找到相关视频片段",
            seekReference: {
              seconds: 377,
              endSeconds: 392,
              query: "文中提到的 SLF4J 是什么东西，再哪里被提到了",
              matchedText: "AgentScope 它的日志采用的是 SLF4J 这个接口。",
              chapterTitle: "AgentScope 依赖与日志接口",
            },
            meta: "Notebook Assistant • 证据定位",
          },
        ]}
        chatSessions={[]}
        activeSessionId={null}
        chatPending={false}
        contextUsage={null}
        contextUsageLoading={false}
        onStartNewChat={() => {}}
        onSelectChatSession={() => {}}
        onOpenSeekReference={onOpenSeekReference}
        onClearChat={() => {}}
        onSubmitChat={() => {}}
      />,
    );

    expect(screen.getByText("已定位到 06:17 - 06:32 · AgentScope 依赖与日志接口")).toBeInTheDocument();
    fireEvent.click(screen.getByText("已定位到 06:17 - 06:32 · AgentScope 依赖与日志接口"));
    expect(screen.getByText("AgentScope 它的日志采用的是 SLF4J 这个接口。")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "跳到视频定位" }));
    expect(onOpenSeekReference).toHaveBeenCalledWith(
      expect.objectContaining({
        seconds: 377,
        endSeconds: 392,
      }),
    );
  });
});
