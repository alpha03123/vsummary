import { ACTIVE_VIDEO_CONTEXTS_KEY } from "./background-controller.js";
import { parseVideoContext } from "./video-context.js";

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
  let playbackConnection = null;

  function disconnectPlayback() {
    const previousConnection = playbackConnection;
    playbackConnection = null;
    previousConnection?.port?.disconnect();
  }

  function connectPlayback() {
    disconnectPlayback();
    if (!activeContext) return;
    const connection = { context: activeContext, port: null, ready: null, error: null };
    playbackConnection = connection;
    connection.ready = initializePlayback(connection);
  }

  async function initializePlayback(connection) {
    const { context } = connection;
    try {
      await chromeApi.scripting.executeScript({
        target: { tabId: context.tabId, frameIds: [0] },
        files: ["content-seek-core.js", "content-seek.js"],
      });
    } catch (error) {
      if (connection !== playbackConnection) return false;
      connection.error = `无法初始化视频时间同步：${error instanceof Error ? error.message : String(error)}`;
      postToWorkspace({
        type: "vsummary:playback-time", key: context.key, tabId: context.tabId,
        seconds: null, error: connection.error,
      });
      return false;
    }
    if (connection !== playbackConnection) return false;
    const port = chromeApi.tabs.connect(context.tabId, { name: "vsummary:playback", frameId: 0 });
    connection.port = port;
    port.onMessage.addListener((message) => {
      if (connection !== playbackConnection || message.type !== "vsummary:playback-time") return;
      const sourceContext = parseVideoContext({ id: context.tabId, url: message.url });
      if (sourceContext?.key !== activeContext?.key) return;
      if (message.seconds !== null && !Number.isFinite(message.seconds)) return;
      postToWorkspace({
        type: "vsummary:playback-time",
        key: context.key,
        tabId: context.tabId,
        seconds: message.seconds,
      });
    });
    port.onDisconnect.addListener(() => {
      const error = chromeApi.runtime.lastError;
      if (connection !== playbackConnection) return;
      connection.error = `视频时间同步已断开，请重新打开侧栏。${error ? `（${error.message}）` : ""}`;
      playbackConnection = null;
      postToWorkspace({
        type: "vsummary:playback-time", key: context.key, tabId: context.tabId, seconds: null,
        error: connection.error,
      });
    });
    return true;
  }

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
      disconnectPlayback();
      activeContext = null;
      showStatus("请在 Bilibili 视频播放页打开此侧边栏。");
      return;
    }
    if (activeContext?.key === nextContext.key && activeContext?.tabId === nextContext.tabId) {
      return;
    }
    activeContext = nextContext;
    showVideoScope();
    connectPlayback();
  }

  function postSeekResult(result, context = activeContext) {
    postToWorkspace({
      type: "vsummary:seek-result",
      key: context?.key,
      tabId: context?.tabId,
      ok: result?.ok === true,
      ...(result?.ok === true
        ? { seconds: result.seconds }
        : { error: result?.error ?? "无法定位 Bilibili 播放器。" }),
    });
  }

  async function seekVideo(seconds, autoplay) {
    if (!Number.isInteger(activeContext?.tabId)) {
      postSeekResult({ ok: false, error: "当前没有可定位的视频页面。" });
      return;
    }
    const context = activeContext;
    try {
      const connection = playbackConnection;
      if (!connection) throw new Error("视频时间同步未连接，请重新打开侧栏。");
      const ready = await connection.ready;
      if (activeContext !== context || connection !== playbackConnection) return;
      if (!ready) throw new Error(connection.error);
      const result = await chromeApi.tabs.sendMessage(context.tabId, {
        type: "vsummary:seek",
        seconds,
        autoplay,
      });
      if (activeContext === context) postSeekResult(result, context);
    } catch (error) {
      if (activeContext !== context) return;
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
      connectPlayback();
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
    chromeApi.tabs.onUpdated.addListener((tabId, changeInfo) => {
      if (tabId === activeContext?.tabId && changeInfo.status === "complete") connectPlayback();
    });
    windowRef.addEventListener("pagehide", disconnectPlayback);
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
