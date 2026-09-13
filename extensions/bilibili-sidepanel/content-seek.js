const { seekVideo, waitForPlaybackVideo } = globalThis.VSummaryContentSeek;

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (message?.type !== "vsummary:seek" || !Number.isFinite(message.seconds)) {
    return undefined;
  }
  waitForPlaybackVideo()
    .then((video) => seekVideo(video, message.seconds, message.autoplay === true))
    .then(() => sendResponse({ ok: true }))
    .catch((error) => sendResponse({ ok: false, error: error.message }));
  return true;
});
