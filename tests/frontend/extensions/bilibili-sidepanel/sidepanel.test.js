import { describe, expect, it, vi } from "vitest";

import { createSidePanelController } from "../../../../extensions/bilibili-sidepanel/sidepanel";
import { ACTIVE_VIDEO_CONTEXTS_KEY } from "../../../../extensions/bilibili-sidepanel/background-controller";

function createEventTarget() {
  const listeners = new Map();
  return {
    addEventListener(type, listener) {
      listeners.set(type, listener);
    },
    dispatch(type, event) {
      listeners.get(type)?.(event);
    },
  };
}

function createChrome(contexts = {}) {
  return {
    storage: {
      session: { get: vi.fn(async () => ({ [ACTIVE_VIDEO_CONTEXTS_KEY]: contexts })) },
      onChanged: { addListener: vi.fn() },
    },
    tabs: { sendMessage: vi.fn(async () => ({ ok: false, error: "播放器不可用" })) },
  };
}

describe("side panel controller", () => {
  it("keeps one iframe and forwards new video contexts to it", async () => {
    document.body.innerHTML = `
      <main id="unsupported"><p id="unsupported-description"></p></main>
      <iframe id="workspace" hidden></iframe>
    `;
    const workspace = document.querySelector("#workspace");
    const iframeWindow = { postMessage: vi.fn() };
    Object.defineProperty(workspace, "contentWindow", { value: iframeWindow });
    const windowRef = createEventTarget();
    const chrome = createChrome();
    const controller = createSidePanelController({ chromeApi: chrome, documentRef: document, windowRef, windowId: 1 });

    await controller.start();
    controller.applyContexts({ 1: { tabId: 10, key: "BV1:1", url: "https://www.bilibili.com/video/BV1" } });
    const initialSource = workspace.src;
    windowRef.dispatch("message", {
      source: iframeWindow,
      origin: "http://127.0.0.1:4173",
      data: { type: "vsummary:video-scope-ready" },
    });
    controller.applyContexts({ 1: { tabId: 11, key: "BV2:1", url: "https://www.bilibili.com/video/BV2" } });

    expect(workspace.src).toBe(initialSource);
    expect(iframeWindow.postMessage).toHaveBeenLastCalledWith(
      expect.objectContaining({ type: "vsummary:set-video-context", context: expect.objectContaining({ tabId: 11 }) }),
      "http://127.0.0.1:4173",
    );
  });

  it("returns seek failures to the iframe", async () => {
    document.body.innerHTML = `<main id="unsupported"><p id="unsupported-description"></p></main><iframe id="workspace"></iframe>`;
    const workspace = document.querySelector("#workspace");
    const iframeWindow = { postMessage: vi.fn() };
    Object.defineProperty(workspace, "contentWindow", { value: iframeWindow });
    const windowRef = createEventTarget();
    const chrome = createChrome();
    const controller = createSidePanelController({ chromeApi: chrome, documentRef: document, windowRef, windowId: 1 });

    await controller.start();
    controller.applyContexts({ 1: { tabId: 10, key: "BV1:1", url: "https://www.bilibili.com/video/BV1" } });
    windowRef.dispatch("message", {
      source: iframeWindow,
      origin: "http://127.0.0.1:4173",
      data: { type: "vsummary:seek", seconds: 40, autoplay: true },
    });
    await Promise.resolve();

    expect(chrome.tabs.sendMessage).toHaveBeenCalledWith(10, expect.objectContaining({ seconds: 40, autoplay: true }));
    expect(iframeWindow.postMessage).toHaveBeenLastCalledWith(
      { type: "vsummary:seek-result", ok: false, error: "播放器不可用" },
      "http://127.0.0.1:4173",
    );
  });
});
