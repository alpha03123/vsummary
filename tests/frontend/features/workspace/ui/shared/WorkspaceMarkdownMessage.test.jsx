import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { WorkspaceMarkdownMessage } from "@src/features/workspace/ui/shared/WorkspaceMarkdownMessage";

describe("WorkspaceMarkdownMessage", () => {
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
