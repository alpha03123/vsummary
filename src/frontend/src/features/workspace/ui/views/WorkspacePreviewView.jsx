import { useEffect, useRef } from "react";

import { formatRange } from "../../../../shared/lib/time";

export function WorkspacePreviewView({ previewSource, previewSeekRequest }) {
  const previewVideoRef = useRef(null);

  useEffect(() => {
    if (!previewSeekRequest || !previewVideoRef.current) {
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
  }, [previewSeekRequest, previewSource]);

  return (
    <div className="flex flex-col gap-4">
      <div className="workspace-muted-panel rounded-3xl border p-4">
        <p className="mb-2 text-xs font-bold uppercase text-stone-500 dark:text-stone-400">Video Preview</p>
        <p className="text-sm text-stone-600 dark:text-stone-400">AI 现在可以根据当前视频的转写结果自动切到这里，并跳转到对应时间点。</p>
        {previewSeekRequest ? (
          <div className="mt-3 rounded-2xl border border-sky-200/80 bg-sky-50/80 px-4 py-3 text-sm text-sky-950 dark:border-sky-900/60 dark:bg-sky-950/20 dark:text-sky-100">
            <p className="font-semibold">
              已定位到 {formatRange(previewSeekRequest.seconds, previewSeekRequest.endSeconds ?? previewSeekRequest.seconds)}
              {previewSeekRequest.chapterTitle ? ` · ${previewSeekRequest.chapterTitle}` : ""}
            </p>
            {previewSeekRequest.query ? (
              <p className="mt-1 text-sky-800/90 dark:text-sky-200/90">检索问题：{previewSeekRequest.query}</p>
            ) : null}
            {previewSeekRequest.matchedText ? (
              <p className="mt-2 line-clamp-3 text-sky-900/90 dark:text-sky-100/90">{previewSeekRequest.matchedText}</p>
            ) : null}
          </div>
        ) : null}
      </div>
      <div className="workspace-elevated-panel overflow-hidden rounded-3xl border bg-black shadow-sm">
        <video key={previewSource} ref={previewVideoRef} className="h-full w-full max-h-[72vh] bg-black" controls preload="metadata">
          <source src={previewSource} />
        </video>
      </div>
    </div>
  );
}
