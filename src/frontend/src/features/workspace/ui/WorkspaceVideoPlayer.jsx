import { useEffect, useRef } from "react";

import { formatRange } from "../../../shared/lib/time";

export function WorkspaceVideoPlayer({ videoSource, playerSeekRequest, videoSourceType = "video" }) {
  const videoRef = useRef(null);
  const isAudioSource = videoSourceType === "audio";

  useEffect(() => {
    if (isAudioSource || !playerSeekRequest || !videoRef.current) {
      return;
    }

    const video = videoRef.current;
    const seekTo = () => {
      if (!Number.isFinite(playerSeekRequest.seconds)) {
        return;
      }
      const duration = Number.isFinite(video.duration) ? video.duration : null;
      const nextSeconds =
        duration == null
          ? Math.max(0, playerSeekRequest.seconds)
          : Math.min(Math.max(0, playerSeekRequest.seconds), duration);
      video.currentTime = nextSeconds;
      video.play().catch(() => { /* user-gesture rules; ignore failures (e.g., past-end) */ });
    };

    if (video.readyState >= 1) {
      seekTo();
      return;
    }

    video.addEventListener("loadedmetadata", seekTo, { once: true });
    return () => {
      video.removeEventListener("loadedmetadata", seekTo);
    };
  }, [isAudioSource, playerSeekRequest, videoSource]);

  return (
    <div className="flex flex-col gap-4">
      <div className="workspace-muted-panel rounded-3xl border p-4">
        <p className="mb-2 text-xs font-bold uppercase text-stone-500 dark:text-stone-400">Media Preview</p>
        {playerSeekRequest ? (
          <div className="mt-3 rounded-2xl border border-info/20 bg-info-subtle px-4 py-3 text-sm text-stone-800 dark:text-stone-100">
            <p className="font-semibold">
              已定位到 {formatRange(playerSeekRequest.seconds, playerSeekRequest.endSeconds ?? playerSeekRequest.seconds)}
              {playerSeekRequest.chapterTitle ? ` · ${playerSeekRequest.chapterTitle}` : ""}
            </p>
            {playerSeekRequest.query ? (
              <p className="mt-1 text-stone-600 dark:text-stone-300">检索问题：{playerSeekRequest.query}</p>
            ) : null}
            {playerSeekRequest.matchedText ? (
              <p className="mt-2 line-clamp-3 text-stone-700 dark:text-stone-200">{playerSeekRequest.matchedText}</p>
            ) : null}
          </div>
        ) : null}
      </div>
      {isAudioSource ? (
        <div className="workspace-elevated-panel rounded-3xl border p-8 text-center text-sm font-semibold text-stone-600 shadow-sm dark:text-zinc-300">
          音频文件暂不支持预览
        </div>
      ) : (
        <div className="workspace-elevated-panel overflow-hidden rounded-3xl border bg-black shadow-sm">
          <video key={videoSource} ref={videoRef} className="h-full w-full max-h-[72vh] bg-black" controls preload="metadata">
            <source src={videoSource} />
          </video>
        </div>
      )}
    </div>
  );
}