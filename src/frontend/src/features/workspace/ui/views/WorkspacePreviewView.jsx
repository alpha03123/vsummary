import { useEffect, useRef, useState } from "react";
import { DEFAULT_SUBTITLE_STYLE, WorkspaceNativeSubtitleSettings } from "../WorkspaceNativeSubtitleSettings";
import { WorkspaceSubtitleDisplay } from "../WorkspaceSubtitleDisplay";
import { WorkspaceMediaPreviewHeader, WorkspaceMediaSeekNotice } from "../shared/WorkspaceMediaPreviewHeader";
import { useNativeFullscreenSubtitles } from "../useNativeFullscreenSubtitles";

export function WorkspacePreviewView({ previewSource, previewSubtitleSource = null, previewSeekRequest }) {
  const previewVideoRef = useRef(null);
  const subtitleTrackRef = useRef(null);
  const [subtitlesEnabled, setSubtitlesEnabled] = useState(Boolean(previewSubtitleSource));
  const [subtitleStyle, setSubtitleStyle] = useState(DEFAULT_SUBTITLE_STYLE);
  const updateSubtitleStyle = (next) => setSubtitleStyle((current) => ({ ...current, ...next }));
  const nativeFullscreen = useNativeFullscreenSubtitles({
    videoRef: previewVideoRef,
    subtitleTrackRef,
    subtitleSource: previewSubtitleSource,
    subtitlesEnabled,
  });

  useEffect(() => {
    setSubtitlesEnabled(Boolean(previewSubtitleSource));
  }, [previewSource, previewSubtitleSource]);

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
    <div className="flex flex-col gap-3">
      <WorkspaceMediaPreviewHeader
        subtitleSettings={previewSubtitleSource ? (
            <WorkspaceNativeSubtitleSettings
              subtitlesEnabled={subtitlesEnabled}
              onSubtitlesEnabledChange={setSubtitlesEnabled}
              style={subtitleStyle}
              onStyleChange={setSubtitleStyle}
            />
        ) : null}
      />
      <WorkspaceMediaSeekNotice seekRequest={previewSeekRequest} />
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
              kind="subtitles"
              src={previewSubtitleSource}
              srcLang="zh-CN"
              label="中文字幕"
            />
          ) : null}
        </video>
        {!nativeFullscreen ? (
          <WorkspaceSubtitleDisplay
            videoRef={previewVideoRef}
            subtitleTrackRef={subtitleTrackRef}
            subtitleSource={previewSubtitleSource}
            enabled={subtitlesEnabled}
            style={{ ...subtitleStyle, onPositionChange: (position) => updateSubtitleStyle({ position }) }}
          />
        ) : null}
      </div>
    </div>
  );
}
