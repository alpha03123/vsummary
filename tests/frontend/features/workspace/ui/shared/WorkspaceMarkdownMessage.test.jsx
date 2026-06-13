import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

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
});
