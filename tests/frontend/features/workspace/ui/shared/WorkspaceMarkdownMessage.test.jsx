import { WorkspaceMarkdownMessage } from "@workspace/workspace/ui/shared/WorkspaceMarkdownMessage";
import { render } from "@src/testing/renderWorkspace";
import { fireEvent, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

describe("WorkspaceMarkdownMessage", () => {
  it("opens citation references with video locations when clicking transcript citations", () => {
    const onOpenCitationReference = vi.fn();

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
                video_id: "video-1",
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
        onOpenCitationReference={onOpenCitationReference}
      />,
    );

    fireEvent.click(screen.getByRole("link", { name: "1" }));

    expect(onOpenCitationReference).toHaveBeenCalledWith({
      videoId: "video-1",
      seconds: 42,
      endSeconds: 55,
      matchedText: "关键知识点对应的字幕",
      chapterTitle: "Video 1",
      query: "",
    });
  });

  it("opens citation references for transcript segment citation anchors", () => {
    const onOpenCitationReference = vi.fn();

    render(
      <WorkspaceMarkdownMessage
        content="这里讲到了关键知识点。[2.1]"
        citations={[
          {
            id: "2.1",
            label: "Video 1",
            source_type: "transcript",
            slots: [
              {
                slot: 1,
                target_type: "video",
                video_title: "Video 1",
                start_seconds: 12,
                end_seconds: 18,
              },
              {
                slot: 2,
                target_type: "transcript",
                video_title: "Video 1",
                text: "关键知识点对应的精确字幕",
              },
            ],
          },
        ]}
        onOpenCitationReference={onOpenCitationReference}
      />,
    );

    fireEvent.click(screen.getByRole("link", { name: "2.1" }));

    expect(onOpenCitationReference).toHaveBeenCalledWith({
      seconds: 12,
      endSeconds: 18,
      matchedText: "关键知识点对应的精确字幕",
      chapterTitle: "Video 1",
      query: "",
    });
  });

  it("seeks and opens the transcript when clicking an AI summary image", () => {
    const onSeek = vi.fn();
    const onOpenTranscriptAtTime = vi.fn();

    render(
      <WorkspaceMarkdownMessage
        content="画面说明\n\n[[IMG:00:05]]"
        noteImageContext={{ seriesId: "series-1", videoId: "video-1", durationSeconds: 30 }}
        onSeek={onSeek}
        onOpenTranscriptAtTime={onOpenTranscriptAtTime}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "视频画面（00:05）" }));

    expect(onOpenTranscriptAtTime).toHaveBeenCalledWith({ seconds: 5 });
    expect(onSeek).not.toHaveBeenCalled();
  });
});
