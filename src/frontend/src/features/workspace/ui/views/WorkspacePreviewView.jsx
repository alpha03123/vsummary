import { useEffect, useRef, useState } from "react";
import { formatRange } from "../../../../shared/lib/time";
import { DEFAULT_SUBTITLE_STYLE, WorkspaceNativeSubtitleSettings } from "../WorkspaceNativeSubtitleSettings";
import { WorkspaceSubtitleDisplay } from "../WorkspaceSubtitleDisplay";

export function WorkspacePreviewView({ previewSource, previewSubtitleSource = null, previewSeekRequest }) {
  const previewVideoRef = useRef(null);
  const subtitleTrackRef = useRef(null);
  const [subtitlesEnabled, setSubtitlesEnabled] = useState(Boolean(previewSubtitleSource));
  const [subtitleStyle, setSubtitleStyle] = useState(DEFAULT_SUBTITLE_STYLE);
  const updateSubtitleStyle = (next) => setSubtitleStyle((current) => ({ ...current, ...next }));

  useEffect(() => {
    setSubtitlesEnabled(Boolean(previewSubtitleSource));
  }, [previewSource, previewSubtitleSource]);

  useEffect(() => {
    const track = subtitleTrackRef.current?.track;
    if (track) {
      track.mode = "hidden";
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
    <div className="flex flex-col">
      <div className="workspace-muted-panel relative rounded-3xl border p-4">
        <div className="mb-2 flex items-center justify-between gap-3">
          <p className="text-xs font-bold uppercase text-stone-600 dark:text-stone-400">Media Preview</p>
          {previewSubtitleSource ? (
            <WorkspaceNativeSubtitleSettings
              subtitlesEnabled={subtitlesEnabled}
              onSubtitlesEnabledChange={setSubtitlesEnabled}
              style={subtitleStyle}
              onStyleChange={setSubtitleStyle}
            />
          ) : null}
        </div>
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
      <div className="workspace-elevated-panel relative overflow-hidden rounded-3xl border bg-black shadow-sm">
        <video
          key={previewSource}
          ref={previewVideoRef}
          className="h-full w-full max-h-[72vh] bg-black"
          controls
          controlsList="nodownload noplaybackrate noremoteplayback"
          disablePictureInPicture
          preload="metadata"
        >
          <source src={previewSource} />
          {previewSubtitleSource ? (
            <track
              ref={subtitleTrackRef}
              kind="metadata"
              src={previewSubtitleSource}
              srcLang="zh-CN"
              label="中文字幕"
            />
          ) : null}
        </video>
        <WorkspaceSubtitleDisplay
          subtitleTrackRef={subtitleTrackRef}
          subtitleSource={previewSubtitleSource}
          enabled={subtitlesEnabled}
          style={{ ...subtitleStyle, onPositionChange: (position) => updateSubtitleStyle({ position }) }}
        />
      </div>
    </div>
  );
}
