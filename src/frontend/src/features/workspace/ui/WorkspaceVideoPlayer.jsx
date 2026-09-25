import { useEffect, useRef } from "react";
import { Download } from "lucide-react";

import { DEFAULT_SUBTITLE_STYLE } from "./WorkspaceNativeSubtitleSettings";
import { WorkspaceSubtitleDisplay } from "./WorkspaceSubtitleDisplay";
import { useNativeFullscreenSubtitles } from "./useNativeFullscreenSubtitles";

export function WorkspaceVideoPlayer({
  videoSource,
  subtitleSource = null,
  playerSeekRequest,
  videoSourceType = "video",
  onTimeUpdate,
  resumeSeconds = null,
  onPlaybackEnded,
  subtitlesEnabled = Boolean(subtitleSource),
  onSubtitlesEnabledChange = () => {},
  subtitleStyle = DEFAULT_SUBTITLE_STYLE,
  onSubtitleStyleChange = () => {},
  onPlaybackStateChange = () => {},
}) {
  const videoRef = useRef(null);
  const subtitleTrackRef = useRef(null);
  const resumedVideoSourceRef = useRef(null);
  const isAudioSource = videoSourceType === "audio";
  const nativeFullscreen = useNativeFullscreenSubtitles({
    videoRef,
    subtitleTrackRef,
    subtitleSource,
    subtitlesEnabled,
  });

  useEffect(() => {
    onPlaybackStateChange(false);
  }, [videoSource]);

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

  useEffect(() => {
    if (isAudioSource || !Number.isFinite(resumeSeconds) || resumeSeconds <= 0 || !videoRef.current) {
      return;
    }
    if (resumedVideoSourceRef.current === videoSource) {
      return;
    }
    resumedVideoSourceRef.current = videoSource;

    const video = videoRef.current;
    const resume = () => {
      const duration = Number.isFinite(video.duration) ? video.duration : null;
      video.currentTime = duration == null
        ? resumeSeconds
        : Math.min(resumeSeconds, Math.max(0, duration - 0.1));
    };

    if (video.readyState >= 1) {
      resume();
      return;
    }

    video.addEventListener("loadedmetadata", resume, { once: true });
    return () => video.removeEventListener("loadedmetadata", resume);
  }, [isAudioSource, resumeSeconds, videoSource]);

  return (
    <div className="flex h-full min-h-0 flex-col gap-3">
      {isAudioSource ? (
        <div className="workspace-elevated-panel rounded-3xl border p-8 text-center text-sm font-semibold text-stone-600 shadow-sm dark:text-zinc-300">
          音频文件暂不支持预览
        </div>
      ) : videoSource ? (
        <div className="workspace-video-stage flex min-h-0 flex-1 items-center justify-center overflow-hidden">
          <div className="workspace-video-frame relative overflow-hidden rounded-3xl border border-stone-200 bg-stone-100 shadow-sm dark:border-stone-800 dark:bg-stone-900">
            <video
              key={videoSource}
              ref={videoRef}
              className="h-full w-full object-contain"
              controls
              controlsList="nodownload noplaybackrate noremoteplayback"
              disablePictureInPicture
              preload="metadata"
              onPlay={() => onPlaybackStateChange(true)}
              onPause={() => onPlaybackStateChange(false)}
              onEnded={() => {
                onPlaybackStateChange(false);
                onPlaybackEnded?.();
              }}
              onTimeUpdate={(event) => onTimeUpdate?.(event.currentTarget.currentTime)}
            >
              <source src={videoSource} />
              {subtitleSource ? (
                <track
                  ref={subtitleTrackRef}
                  kind="subtitles"
                  src={subtitleSource}
                  srcLang="zh-CN"
                  label="中文字幕"
                />
              ) : null}
            </video>
            {!nativeFullscreen ? (
              <WorkspaceSubtitleDisplay
                videoRef={videoRef}
                subtitleTrackRef={subtitleTrackRef}
                subtitleSource={subtitleSource}
                enabled={subtitlesEnabled}
                style={{ ...subtitleStyle, onPositionChange: (position) => onSubtitleStyleChange({ ...subtitleStyle, position }) }}
              />
            ) : null}
          </div>
        </div>
      ) : (
        // 未下载的媒体没有可播放源：给一个和播放器等大的 16:9 占位，
        // 说明当前状态并指向左栏的下载入口，而不是留一条没有信息的黑条。
        <div className="workspace-elevated-panel flex min-h-0 flex-1 w-full flex-col items-center justify-center gap-3 overflow-hidden rounded-3xl border border-stone-800 bg-stone-950 px-6 text-center shadow-sm">
          <span className="flex h-12 w-12 items-center justify-center rounded-2xl bg-white/10 text-stone-300">
            <Download size={22} aria-hidden="true" />
          </span>
          <p className="text-sm font-semibold text-stone-200">视频尚未下载</p>
          <p className="max-w-sm text-xs leading-relaxed text-stone-400">
            在左侧来源列表点击「下载视频」，下载完成后即可在这里预览。
          </p>
        </div>
      )}
    </div>
  );
}
