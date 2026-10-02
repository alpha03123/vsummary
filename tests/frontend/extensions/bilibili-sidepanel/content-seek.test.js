import { createContext, runInContext } from "node:vm";
import { describe, expect, it, vi } from "vitest";
import coreScript from "../../../../extensions/bilibili-sidepanel/content-seek-core.js?raw";
import bridgeScript from "../../../../extensions/bilibili-sidepanel/content-seek.js?raw";

function createChromeEvent() {
  const listeners = new Set();
  return { listeners, addListener: (listener) => listeners.add(listener) };
}

describe("playback time", () => {
  it("sends the video's actual currentTime on connection and every playback update", () => {
    const runtime = { onConnect: createChromeEvent(), onMessage: createChromeEvent() };
    const context = createContext({ chrome: { runtime }, window, document, HTMLVideoElement, HTMLMediaElement, MutationObserver, getComputedStyle });
    runInContext(coreScript, context);
    runInContext(bridgeScript, context);

    document.body.innerHTML = '<div class="bpx-player-video-wrap"><video></video></div>';
    const video = document.querySelector("video");
    video.getBoundingClientRect = () => ({ width: 640, height: 360 });
    Object.defineProperty(video, "readyState", { value: HTMLMediaElement.HAVE_METADATA });
    video.currentTime = 407.123;
    const port = { name: "vsummary:playback", postMessage: vi.fn(), onDisconnect: createChromeEvent() };
    runtime.onConnect.listeners.forEach((listener) => listener(port));
    try {
      expect(port.postMessage.mock.lastCall[0].seconds).toBe(video.currentTime);
      for (const seconds of [518.456, 548.789, 62.06]) {
        video.currentTime = seconds;
        video.dispatchEvent(new Event("timeupdate"));
        expect(port.postMessage.mock.lastCall[0].seconds).toBe(video.currentTime);
      }
    } finally {
      port.onDisconnect.listeners.forEach((listener) => listener());
      document.body.replaceChildren();
    }
  });
});
