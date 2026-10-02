(() => {
  if (globalThis.VSummaryContentBridge) return;
  const { observePlaybackVideo, seekVideo, waitForPlaybackVideo } = globalThis.VSummaryContentSeek;

  chrome.runtime.onConnect.addListener((port) => {
    if (port.name !== "vsummary:playback") return;
    const stop = observePlaybackVideo((seconds) => {
      port.postMessage({ type: "vsummary:playback-time", seconds, url: window.location.href });
    });
    port.onDisconnect.addListener(stop);
  });

  chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
    if (message?.type !== "vsummary:seek" || !Number.isFinite(message.seconds)) {
      return undefined;
    }
    waitForPlaybackVideo()
      .then((video) => seekVideo(video, message.seconds, message.autoplay === true))
      .then((seconds) => sendResponse({ ok: true, seconds }))
      .catch((error) => sendResponse({ ok: false, error: error.message }));
    return true;
  });
  globalThis.VSummaryContentBridge = true;
})();
