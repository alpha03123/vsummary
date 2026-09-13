import { describe, expect, it, vi } from "vitest";

import {
  ACTIVE_VIDEO_CONTEXTS_KEY,
  createBackgroundController,
} from "../../../../extensions/bilibili-sidepanel/background-controller";

function createEvent() {
  const listeners = [];
  return {
    addListener(listener) {
      listeners.push(listener);
    },
    listeners,
  };
}

function createChrome({ activeTabs = [] } = {}) {
  const state = {};
  return {
    runtime: { onInstalled: createEvent(), onStartup: createEvent() },
    sidePanel: { setPanelBehavior: vi.fn(() => Promise.resolve()) },
    tabs: {
      get: vi.fn(async (tabId) => activeTabs.find((tab) => tab.id === tabId)),
      query: vi.fn(async () => activeTabs),
      onUpdated: createEvent(),
      onActivated: createEvent(),
    },
    webNavigation: { onHistoryStateUpdated: createEvent() },
    windows: { onRemoved: createEvent() },
    storage: {
      session: {
        get: vi.fn(async () => state),
        set: vi.fn(async (value) => Object.assign(state, value)),
      },
    },
  };
}

describe("background controller", () => {
  it("persists active contexts independently for every window", async () => {
    const chrome = createChrome({
      activeTabs: [
        { id: 10, windowId: 1, active: true, url: "https://www.bilibili.com/video/BV1a?p=1" },
        { id: 20, windowId: 2, active: true, url: "https://www.bilibili.com/video/BV2b?p=2" },
      ],
    });

    const controller = createBackgroundController(chrome);
    await controller.initializeActiveContexts();

    expect(chrome.storage.session.set).toHaveBeenLastCalledWith({
      [ACTIVE_VIDEO_CONTEXTS_KEY]: {
        1: expect.objectContaining({ tabId: 10, key: "BV1a:1" }),
        2: expect.objectContaining({ tabId: 20, key: "BV2b:2" }),
      },
    });
  });

  it("does not write the same SPA context twice", async () => {
    const chrome = createChrome();
    const controller = createBackgroundController(chrome);
    const tab = { id: 10, windowId: 1, active: true, url: "https://www.bilibili.com/video/BV1a?p=2" };

    await controller.setWindowContext(1, tab);
    await controller.setWindowContext(1, tab);

    expect(chrome.storage.session.set).toHaveBeenCalledTimes(1);
  });

  it("synchronizes active tabs when a cold service worker starts", async () => {
    const chrome = createChrome({
      activeTabs: [{ id: 10, windowId: 1, active: true, url: "https://www.bilibili.com/video/BV1a" }],
    });

    createBackgroundController(chrome).start();
    await vi.waitFor(() => expect(chrome.storage.session.set).toHaveBeenCalledTimes(1));

    expect(chrome.storage.session.set).toHaveBeenCalledWith({
      [ACTIVE_VIDEO_CONTEXTS_KEY]: { 1: expect.objectContaining({ key: "BV1a:1" }) },
    });
  });
});
