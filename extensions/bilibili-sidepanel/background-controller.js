import { contextsMatch, parseVideoContext } from "./video-context.js";

export const ACTIVE_VIDEO_CONTEXTS_KEY = "activeVideoContexts";

export function createBackgroundController(chromeApi) {
  let contextsByWindow = {};
  const initialization = chromeApi.storage.session
    .get(ACTIVE_VIDEO_CONTEXTS_KEY)
    .then((stored) => {
      const storedContexts = stored[ACTIVE_VIDEO_CONTEXTS_KEY];
      contextsByWindow = storedContexts && typeof storedContexts === "object" ? storedContexts : {};
    });

  async function persistContexts() {
    await chromeApi.storage.session.set({
      [ACTIVE_VIDEO_CONTEXTS_KEY]: contextsByWindow,
    });
  }

  async function setWindowContext(windowId, tab) {
    await initialization;
    const nextContext = parseVideoContext(tab);
    if (contextsMatch(contextsByWindow[windowId], nextContext)) {
      return;
    }
    contextsByWindow = { ...contextsByWindow, [windowId]: nextContext };
    await persistContexts();
  }

  async function syncActiveTab(tabId) {
    const tab = await chromeApi.tabs.get(tabId);
    if (tab.active && Number.isInteger(tab.windowId)) {
      await setWindowContext(tab.windowId, tab);
    }
  }

  async function initializeActiveContexts() {
    await initialization;
    const activeTabs = await chromeApi.tabs.query({ active: true });
    for (const tab of activeTabs) {
      if (Number.isInteger(tab.windowId)) {
        await setWindowContext(tab.windowId, tab);
      }
    }
  }

  async function removeWindowContext(windowId) {
    await initialization;
    if (!(windowId in contextsByWindow)) {
      return;
    }
    const { [windowId]: _removed, ...remainingContexts } = contextsByWindow;
    contextsByWindow = remainingContexts;
    await persistContexts();
  }

  function reportBackgroundError(error) {
    console.error("VSummary side panel background error", error);
  }

  function start() {
    chromeApi.tabs.onUpdated.addListener((tabId, changeInfo, tab) => {
      if ((changeInfo.url || changeInfo.status === "complete") && tab.active && Number.isInteger(tab.windowId)) {
        void setWindowContext(tab.windowId, tab).catch(reportBackgroundError);
      }
    });
    chromeApi.tabs.onActivated.addListener(({ tabId }) => {
      void syncActiveTab(tabId).catch(reportBackgroundError);
    });
    chromeApi.webNavigation.onHistoryStateUpdated.addListener(({ tabId, frameId }) => {
      if (frameId === 0) {
        void syncActiveTab(tabId).catch(reportBackgroundError);
      }
    });
    chromeApi.windows.onRemoved.addListener((windowId) => {
      void removeWindowContext(windowId).catch(reportBackgroundError);
    });
    chromeApi.runtime.onInstalled.addListener(() => {
      void chromeApi.sidePanel
        .setPanelBehavior({ openPanelOnActionClick: true })
        .then(initializeActiveContexts)
        .catch(reportBackgroundError);
    });
    chromeApi.runtime.onStartup.addListener(() => {
      void initializeActiveContexts().catch(reportBackgroundError);
    });
    void initializeActiveContexts().catch(reportBackgroundError);
  }

  return {
    initializeActiveContexts,
    setWindowContext,
    start,
  };
}
