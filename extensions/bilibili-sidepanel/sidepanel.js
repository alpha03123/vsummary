import { ACTIVE_VIDEO_CONTEXTS_KEY } from "./background-controller.js";

const APP_BASE = "http://127.0.0.1:4173";
const APP_ORIGIN = new URL(APP_BASE).origin;
const SERIES_ID = "bilibili";

function isVideoContext(context) {
  return Boolean(context?.url) && Number.isInteger(context?.tabId) && typeof context.key === "string";
}

export function createSidePanelController({ chromeApi, documentRef, windowRef, windowId }) {
  const workspace = documentRef.querySelector("#workspace");
  const unsupported = documentRef.querySelector("#unsupported");
  const unsupportedDescription = documentRef.querySelector("#unsupported-description");
  let activeContext = null;
  let workspaceLoaded = false;

  function showStatus(message) {
    unsupportedDescription.textContent = message;
    workspace.hidden = true;
    unsupported.hidden = false;
  }

  function postToWorkspace(message) {
    if (workspaceLoaded && workspace.contentWindow) {
      workspace.contentWindow.postMessage(message, APP_ORIGIN);
    }
  }

  function showVideoScope() {
    unsupported.hidden = true;
    workspace.hidden = false;
    if (!workspaceLoaded) {
      const target = new URL(APP_BASE);
      target.searchParams.set("embed", "video-scope");
      target.searchParams.set("series", SERIES_ID);
      workspace.src = target.toString();
      workspaceLoaded = true;
      return;
    }
    postToWorkspace({ type: "vsummary:set-video-context", context: activeContext });
  }

  function applyContexts(contexts) {
    const nextContext = contexts?.[windowId] ?? null;
    if (!isVideoContext(nextContext)) {
      activeContext = null;
      showStatus("请在 Bilibili 视频播放页打开此侧边栏。");
      return;
    }
    if (activeContext?.key === nextContext.key && activeContext?.tabId === nextContext.tabId) {
      return;
    }
    activeContext = nextContext;
    showVideoScope();
  }

  function postSeekResult(result) {
    postToWorkspace({
      type: "vsummary:seek-result",
      ok: result?.ok === true,
      error: result?.error ?? "无法定位 Bilibili 播放器。",
    });
  }

  async function seekVideo(seconds, autoplay) {
    if (!Number.isInteger(activeContext?.tabId)) {
      postSeekResult({ ok: false, error: "当前没有可定位的视频页面。" });
      return;
    }
    try {
      const result = await chromeApi.tabs.sendMessage(activeContext.tabId, {
        type: "vsummary:seek",
        seconds,
        autoplay,
      });
      postSeekResult(result);
    } catch (error) {
      postSeekResult({
        ok: false,
        error: error instanceof Error ? error.message : "无法连接到 Bilibili 播放器。",
      });
    }
  }

  function handleWorkspaceMessage(event) {
    if (event.source !== workspace.contentWindow || event.origin !== APP_ORIGIN) {
      return;
    }
    if (event.data?.type === "vsummary:video-scope-ready") {
      postToWorkspace({ type: "vsummary:set-video-context", context: activeContext });
      return;
    }
    if (event.data?.type === "vsummary:seek" && Number.isFinite(event.data.seconds)) {
      void seekVideo(event.data.seconds, event.data.autoplay === true);
    }
  }

  function handleStorageChange(changes, areaName) {
    if (areaName === "session" && ACTIVE_VIDEO_CONTEXTS_KEY in changes) {
      applyContexts(changes[ACTIVE_VIDEO_CONTEXTS_KEY].newValue ?? {});
    }
  }

  async function start() {
    windowRef.addEventListener("message", handleWorkspaceMessage);
    chromeApi.storage.onChanged.addListener(handleStorageChange);
    const stored = await chromeApi.storage.session.get(ACTIVE_VIDEO_CONTEXTS_KEY);
    applyContexts(stored[ACTIVE_VIDEO_CONTEXTS_KEY] ?? {});
  }

  return { applyContexts, start };
}

async function startSidePanel() {
  const currentWindow = await chrome.windows.getCurrent();
  if (!Number.isInteger(currentWindow.id)) {
    throw new Error("无法识别当前 Chrome 窗口。");
  }
  const controller = createSidePanelController({
    chromeApi: chrome,
    documentRef: document,
    windowRef: window,
    windowId: currentWindow.id,
  });
  await controller.start();
}

if (typeof chrome !== "undefined") {
  void startSidePanel().catch((error) => {
    const description = document.querySelector("#unsupported-description");
    description.textContent = error instanceof Error ? error.message : "VSummary 侧边栏初始化失败。";
  });
}
