import { useEffect, useRef } from "react";

import { formatRange } from "../../../../shared/lib/time";

export function WorkspacePreviewView({ previewSource, previewSeekRequest, previewSourceType = "video" }) {
  const previewVideoRef = useRef(null);
  const isAudioSource = previewSourceType === "audio";

  useEffect(() => {
    if (isAudioSource || !previewSeekRequest || !previewVideoRef.current) {
      return;
    }

    const video = previewVideoRef.current;
    const seekTo = () => {
      if (!Number.isFinite(previewSeekRequest.seconds)) {
        return;
      }
      const duration = Number.isFinite(video.duration) ? video.duration : null;
      const nextSeconds =
        duration == null
          ? Math.max(0, previewSeekRequest.seconds)
          : Math.min(Math.max(0, previewSeekRequest.seconds), duration);
      video.currentTime = nextSeconds;
    };

    if (video.readyState >= 1) {
      seekTo();
      return;
    }

    video.addEventListener("loadedmetadata", seekTo, { once: true });
    return () => {
      video.removeEventListener("loadedmetadata", seekTo);
    };
  }, [isAudioSource, previewSeekRequest, previewSource]);

  return (
    <div className="flex flex-col gap-4">
      <div className="workspace-muted-panel rounded-3xl border p-4">
        <p className="mb-2 text-xs font-bold uppercase text-stone-500 dark:text-stone-400">Media Preview</p>
        {previewSeekRequest ? (
          <div className="mt-3 rounded-2xl border border-info/20 bg-info-subtle px-4 py-3 text-sm text-stone-800 dark:text-stone-100">
            <p className="font-semibold">
              已定位到 {formatRange(previewSeekRequest.seconds, previewSeekRequest.endSeconds ?? previewSeekRequest.seconds)}
              {previewSeekRequest.chapterTitle ? ` · ${previewSeekRequest.chapterTitle}` : ""}
            </p>
            {previewSeekRequest.query ? (
              <p className="mt-1 text-stone-600 dark:text-stone-300">检索问题：{previewSeekRequest.query}</p>
            ) : null}
            {previewSeekRequest.matchedText ? (
              <p className="mt-2 line-clamp-3 text-stone-700 dark:text-stone-200">{previewSeekRequest.matchedText}</p>
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
          <video key={previewSource} ref={previewVideoRef} className="h-full w-full max-h-[72vh] bg-black" controls preload="metadata">
            <source src={previewSource} />
          </video>
        </div>
      )}
    </div>
  );
}
