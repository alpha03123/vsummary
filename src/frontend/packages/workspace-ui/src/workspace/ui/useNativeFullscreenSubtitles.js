import { useEffect, useState } from "react";

function isVideoFullscreen(video) {
  return document.fullscreenElement === video || video?.webkitDisplayingFullscreen === true;
}

export function useNativeFullscreenSubtitles({
  videoRef,
  subtitleTrackRef,
  subtitleSource,
  subtitlesEnabled,
}) {
  const [nativeFullscreen, setNativeFullscreen] = useState(false);

  useEffect(() => {
    const video = videoRef.current;
    if (!video || !subtitleSource) {
      setNativeFullscreen(false);
      return undefined;
    }

    const syncTrackMode = () => {
      const fullscreen = isVideoFullscreen(video);
      setNativeFullscreen(fullscreen);
      const track = subtitleTrackRef.current?.track;
      if (track) {
        track.mode = subtitlesEnabled && fullscreen ? "showing" : "hidden";
      }
    };

    document.addEventListener("fullscreenchange", syncTrackMode);
    video.addEventListener("webkitbeginfullscreen", syncTrackMode);
    video.addEventListener("webkitendfullscreen", syncTrackMode);
    syncTrackMode();

    return () => {
      document.removeEventListener("fullscreenchange", syncTrackMode);
      video.removeEventListener("webkitbeginfullscreen", syncTrackMode);
      video.removeEventListener("webkitendfullscreen", syncTrackMode);
    };
  }, [subtitleSource, subtitlesEnabled, subtitleTrackRef, videoRef]);

  return nativeFullscreen;
}
