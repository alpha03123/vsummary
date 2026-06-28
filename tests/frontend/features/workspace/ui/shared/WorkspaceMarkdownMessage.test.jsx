import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { WorkspaceMarkdownMessage } from "@src/features/workspace/ui/shared/WorkspaceMarkdownMessage";

describe("WorkspaceMarkdownMessage", () => {
  it("links citation markers by citation id", () => {
    render(
      <WorkspaceMarkdownMessage
        content="这个结论来自第四条证据。[4]"
        citations={[
          {
            id: "4",
            label: "Video 4",
            source_type: "summary",
            slots: [
              {
                slot: 1,
                target_type: "summary",
                video_title: "Video 4",
                text: "第四条证据",
              },
            ],
          },
        ]}
      />,
    );

    expect(screen.getByRole("link", { name: "4" })).toHaveAttribute("href", "#citation-4");
  });

  it("renders bracketed latex expressions with katex", () => {
    const { container } = render(
      <WorkspaceMarkdownMessage content={String.raw`[ \frac{dX}{dt}=X(2-AY) ]`} />,
    );

    expect(container.querySelector(".katex")).not.toBeNull();
  });

  it("truncates long citation preview text", () => {
    const longText = "字幕内容".repeat(120);

    render(
      <WorkspaceMarkdownMessage
        content="回答来自视频。[2]"
        citations={[
          {
            id: "2",
            label: "Video 1",
            source_type: "transcript",
            slots: [
              {
                slot: 1,
                target_type: "video",
                video_title: "Video 1",
                start_seconds: 13,
                end_seconds: 767,
              },
              {
                slot: 2,
                target_type: "transcript",
                video_title: "Video 1",
                text: longText,
              },
            ],
          },
        ]}
      />,
    );

    fireEvent.mouseEnter(screen.getByRole("link", { name: "2" }));

    expect(screen.getByText("[2] Video 1")).toBeInTheDocument();
    expect(screen.queryByText(longText)).not.toBeInTheDocument();
    expect(screen.getByText(/^字幕内容.*\.\.\.$/)).toBeInTheDocument();
  });

  it("opens video seek references when clicking transcript citations", () => {
    const onOpenSeekReference = vi.fn();

    render(
      <WorkspaceMarkdownMessage
        content="这里讲到了关键知识点。[1]"
        citations={[
          {
            id: "1",
            label: "Video 1",
            source_type: "transcript",
            slots: [
              {
                slot: 1,
                target_type: "video",
                video_title: "Video 1",
                start_seconds: 42,
                end_seconds: 55,
              },
              {
                slot: 2,
                target_type: "transcript",
                video_title: "Video 1",
                text: "关键知识点对应的字幕",
              },
            ],
          },
        ]}
        onOpenSeekReference={onOpenSeekReference}
      />,
    );

    fireEvent.click(screen.getByRole("link", { name: "1" }));

    expect(onOpenSeekReference).toHaveBeenCalledWith({
      seconds: 42,
      endSeconds: 55,
      matchedText: "关键知识点对应的字幕",
      chapterTitle: "Video 1",
      query: "",
    });
  });

  it("renders model think tags as a collapsible thinking block", () => {
    render(
      <WorkspaceMarkdownMessage
        content={"<think>先分析问题，再回答。</think>\n\n最终答案：**可以**。"}
      />,
    );

    expect(screen.getByRole("button", { name: /思考过程/ })).toBeInTheDocument();
    expect(screen.getByText("先分析问题，再回答。")).toBeInTheDocument();
    expect(screen.getByText(/最终答案：/)).toBeInTheDocument();
    expect(screen.getByText("可以")).toBeInTheDocument();
  });
});
