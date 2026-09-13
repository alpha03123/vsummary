(() => {
  const VIDEO_SELECTORS = [
    ".bpx-player-video-wrap video",
    ".bilibili-player-video video",
  ];
  const DEFAULT_TIMEOUT_MS = 5000;

  function isVisiblePlaybackVideo(video) {
    const rect = video.getBoundingClientRect();
    return rect.width > 0 && rect.height > 0 && getComputedStyle(video).visibility !== "hidden";
  }

  function findPlaybackVideo() {
    for (const selector of VIDEO_SELECTORS) {
      const candidate = Array.from(document.querySelectorAll(selector))
        .find((video) => video instanceof HTMLVideoElement && isVisiblePlaybackVideo(video));
      if (candidate) {
        return candidate;
      }
    }
    return null;
  }

  function waitForPlaybackVideo(timeoutMs = DEFAULT_TIMEOUT_MS) {
    const existing = findPlaybackVideo();
    if (existing) {
      return Promise.resolve(existing);
    }
    return new Promise((resolve, reject) => {
      const observer = new MutationObserver(() => {
        const video = findPlaybackVideo();
        if (video) {
          window.clearTimeout(timeoutId);
          observer.disconnect();
          resolve(video);
        }
      });
      const timeoutId = window.setTimeout(() => {
        observer.disconnect();
        reject(new Error("未找到 Bilibili 播放器"));
      }, timeoutMs);
      observer.observe(document.documentElement, {
        childList: true,
        subtree: true,
        attributes: true,
        attributeFilter: ["class", "style"],
      });
    });
  }

  function seekVideo(video, seconds, autoplay, timeoutMs = DEFAULT_TIMEOUT_MS) {
    const seek = () => {
      const maximum = Number.isFinite(video.duration) ? Math.max(0, video.duration - 0.1) : seconds;
      video.currentTime = Math.max(0, Math.min(seconds, maximum));
      if (autoplay) {
        void video.play().catch(() => {});
      }
    };
    if (video.readyState >= HTMLMediaElement.HAVE_METADATA) {
      seek();
      return Promise.resolve();
    }
    return new Promise((resolve, reject) => {
      const timeoutId = window.setTimeout(() => {
        cleanup();
        reject(new Error("Bilibili 播放器未能加载视频元数据"));
      }, timeoutMs);
      const complete = () => {
        cleanup();
        seek();
        resolve();
      };
      const fail = () => {
        cleanup();
        reject(new Error("Bilibili 播放器加载视频元数据失败"));
      };
      const cleanup = () => {
        window.clearTimeout(timeoutId);
        video.removeEventListener("loadedmetadata", complete);
        video.removeEventListener("error", fail);
        video.removeEventListener("abort", fail);
      };
      video.addEventListener("loadedmetadata", complete, { once: true });
      video.addEventListener("error", fail, { once: true });
      video.addEventListener("abort", fail, { once: true });
    });
  }

  globalThis.VSummaryContentSeek = Object.freeze({
    seekVideo,
    waitForPlaybackVideo,
  });
})();
