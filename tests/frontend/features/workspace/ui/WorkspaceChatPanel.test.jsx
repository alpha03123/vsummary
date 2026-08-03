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
