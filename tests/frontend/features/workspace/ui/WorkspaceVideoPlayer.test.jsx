import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { WorkspaceVideoPlayer } from "@src/features/workspace/ui/WorkspaceVideoPlayer";

describe("WorkspaceVideoPlayer", () => {
  it("shows an unavailable preview message for audio files", () => {
    const { container } = render(
      <WorkspaceVideoPlayer videoSource="/api/videos/series-1/audio-1/preview" videoSourceType="audio" />,
    );
    expect(screen.getByText("音频文件暂不支持预览")).toBeInTheDocument();
    expect(container.querySelector("video")).toBeNull();
  });

  it("seeks the <video> and calls play() when playerSeekRequest arrives", () => {
    const playMock = vi.fn(() => Promise.resolve());
    const playSpy = vi.spyOn(HTMLMediaElement.prototype, "play").mockImplementation(playMock);

    try {
      const { rerender, container } = render(
        <WorkspaceVideoPlayer videoSource="/api/videos/s1/v1/preview" playerSeekRequest={null} />,
      );
      const video = container.querySelector("video");
      // jsdom: readyState is 0 by default; the effect attaches a one-time 'loadedmetadata' listener.
      expect(video).toBeInTheDocument();

      rerender(
        <WorkspaceVideoPlayer
          videoSource="/api/videos/s1/v1/preview"
          playerSeekRequest={{
            seconds: 12.5,
            endSeconds: 18,
            query: "",
            matchedText: "",
            chapterTitle: "Chapter 1",
            requestId: "1",
          }}
        />,
      );

      // Simulate metadata loaded → triggers the seek handler.
      Object.defineProperty(video, "readyState", { value: 1, configurable: true });
      Object.defineProperty(video, "duration", { value: 60, configurable: true });
      fireEvent.loadedMetadata(video);

      expect(video.currentTime).toBe(12.5);
      expect(playMock).toHaveBeenCalled();
    } finally {
      playSpy.mockRestore();
    }
  });

  it("clamps the seek to the video duration", () => {
    const playMock = vi.fn(() => Promise.resolve());
    const playSpy = vi.spyOn(HTMLMediaElement.prototype, "play").mockImplementation(playMock);

    try {
      const { rerender, container } = render(
        <WorkspaceVideoPlayer videoSource="/api/videos/s1/v1/preview" playerSeekRequest={null} />,
      );
      const video = container.querySelector("video");
      Object.defineProperty(video, "readyState", { value: 1, configurable: true });
      Object.defineProperty(video, "duration", { value: 30, configurable: true });
      fireEvent.loadedMetadata(video);

      rerender(
        <WorkspaceVideoPlayer
          videoSource="/api/videos/s1/v1/preview"
          playerSeekRequest={{ seconds: 999, endSeconds: null, query: "", matchedText: "", chapterTitle: "", requestId: "2" }}
        />,
      );

      fireEvent.loadedMetadata(video);
      expect(video.currentTime).toBe(30);
    } finally {
      playSpy.mockRestore();
    }
  });

  it("ignores non-finite seconds without throwing", () => {
    const playMock = vi.fn(() => Promise.resolve());
    const playSpy = vi.spyOn(HTMLMediaElement.prototype, "play").mockImplementation(playMock);

    try {
      const { rerender, container } = render(
        <WorkspaceVideoPlayer videoSource="/api/videos/s1/v1/preview" playerSeekRequest={null} />,
      );
      const video = container.querySelector("video");
      Object.defineProperty(video, "readyState", { value: 1, configurable: true });

      rerender(
        <WorkspaceVideoPlayer
          videoSource="/api/videos/s1/v1/preview"
          playerSeekRequest={{ seconds: NaN, endSeconds: null, query: "", matchedText: "", chapterTitle: "", requestId: "3" }}
        />,
      );

      expect(() => fireEvent.loadedMetadata(video)).not.toThrow();
      expect(playMock).not.toHaveBeenCalled();
    } finally {
      playSpy.mockRestore();
    }
  });
});