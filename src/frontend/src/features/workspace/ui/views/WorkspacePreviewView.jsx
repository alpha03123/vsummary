import { useEffect, useRef, useState } from "react";
import { Captions } from "lucide-react";

import { formatRange } from "../../../../shared/lib/time";

export function WorkspacePreviewView({ previewSource, previewSubtitleSource = null, previewSeekRequest }) {
  const previewVideoRef = useRef(null);
  const subtitleTrackRef = useRef(null);
  const [subtitlesEnabled, setSubtitlesEnabled] = useState(Boolean(previewSubtitleSource));

  useEffect(() => {
    setSubtitlesEnabled(Boolean(previewSubtitleSource));
  }, [previewSource, previewSubtitleSource]);

  useEffect(() => {
    const track = subtitleTrackRef.current?.track;
    if (track) {
      track.mode = subtitlesEnabled ? "showing" : "hidden";
    }
  }, [previewSubtitleSource, subtitlesEnabled]);

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
        <p className="mb-2 text-xs font-bold uppercase text-stone-600 dark:text-stone-400">Media Preview</p>
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
      <div className="workspace-elevated-panel overflow-hidden rounded-3xl border bg-black shadow-sm">
        <video key={previewSource} ref={previewVideoRef} className="h-full w-full max-h-[72vh] bg-black" controls preload="metadata">
          <source src={previewSource} />
          {previewSubtitleSource ? (
            <track
              ref={subtitleTrackRef}
              kind="subtitles"
              src={previewSubtitleSource}
              srcLang="zh-CN"
              label="中文字幕"
              default={subtitlesEnabled}
            />
          ) : null}
        </video>
      </div>
      {previewSubtitleSource ? (
        <div className="flex justify-center">
          <button
            type="button"
            aria-pressed={subtitlesEnabled}
            onClick={() => setSubtitlesEnabled((current) => !current)}
            className="inline-flex items-center gap-2 rounded-lg border border-stone-300 bg-white px-4 py-2.5 text-sm font-semibold text-stone-700 shadow-sm transition-colors hover:border-accent/50 hover:text-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/40 dark:border-stone-700 dark:bg-neutral-900 dark:text-stone-200"
          >
            <Captions size={17} aria-hidden="true" />
            {subtitlesEnabled ? "隐藏字幕" : "显示字幕"}
          </button>
        </div>
      ) : null}
    </div>
  );
}
