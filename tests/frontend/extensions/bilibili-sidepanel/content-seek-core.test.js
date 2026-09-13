import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import "../../../../extensions/bilibili-sidepanel/content-seek-core";

const { seekVideo, waitForPlaybackVideo } = globalThis.VSummaryContentSeek;

function setVideoRect(video, width = 640, height = 360) {
  video.getBoundingClientRect = () => ({ width, height });
}

describe("content seek", () => {
  beforeEach(() => {
    document.body.replaceChildren();
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("waits for metadata only for a bounded duration", async () => {
    const video = document.createElement("video");
    Object.defineProperty(video, "readyState", { value: 0 });
    const result = expect(seekVideo(video, 12, false, 100)).rejects.toThrow("未能加载视频元数据");

    await vi.advanceTimersByTimeAsync(100);
    await result;
  });

  it("selects the player video instead of an unrelated page video", async () => {
    const preview = document.createElement("video");
    setVideoRect(preview);
    document.body.append(preview);
    const player = document.createElement("video");
    setVideoRect(player);
    const wrapper = document.createElement("div");
    wrapper.className = "bpx-player-video-wrap";
    wrapper.append(player);
    document.body.append(wrapper);

    await expect(waitForPlaybackVideo()).resolves.toBe(player);
  });
});
