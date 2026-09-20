import { useEffect, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { Captions, Download } from "lucide-react";

import { DEFAULT_SUBTITLE_STYLE, WorkspaceNativeSubtitleSettings } from "./WorkspaceNativeSubtitleSettings";
import { WorkspaceSubtitleDisplay } from "./WorkspaceSubtitleDisplay";
import { WorkspaceMediaPreviewHeader, WorkspaceMediaSeekNotice } from "./shared/WorkspaceMediaPreviewHeader";

export function WorkspaceVideoPlayer({
  videoSource,
  subtitleSource = null,
  playerSeekRequest,
  videoSourceType = "video",
  onTimeUpdate,
  resumeSeconds = null,
  onPlaybackEnded,
  onFocusOverviewAtTime,
  followOverviewPlayback = false,
  onFollowOverviewPlaybackChange,
}) {
  const videoRef = useRef(null);
  const subtitleTrackRef = useRef(null);
  const resumedVideoSourceRef = useRef(null);
  const [isPlaying, setIsPlaying] = useState(false);
  const [subtitlesEnabled, setSubtitlesEnabled] = useState(Boolean(subtitleSource));
  const [subtitleStyle, setSubtitleStyle] = useState(DEFAULT_SUBTITLE_STYLE);
  const updateSubtitleStyle = (next) => setSubtitleStyle((current) => ({ ...current, ...next }));
  const isAudioSource = videoSourceType === "audio";

  useEffect(() => {
    setIsPlaying(false);
  }, [videoSource]);

  useEffect(() => {
    setSubtitlesEnabled(Boolean(subtitleSource));
  }, [subtitleSource, videoSource]);

  useEffect(() => {
    const track = subtitleTrackRef.current?.track;
    if (track) {
      track.mode = "hidden";
    }
  }, [subtitlesEnabled, subtitleSource]);

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

  function openCurrentTranscript() {
    const seconds = videoRef.current?.currentTime;
    if (Number.isFinite(seconds)) {
      onFocusOverviewAtTime?.(seconds);
    }
  }

  return (
    <div className="flex flex-col gap-3">
      <WorkspaceMediaPreviewHeader
        subtitleSettings={!isAudioSource && subtitleSource ? (
            <WorkspaceNativeSubtitleSettings
              subtitlesEnabled={subtitlesEnabled}
              onSubtitlesEnabledChange={setSubtitlesEnabled}
              followOverviewPlayback={followOverviewPlayback}
              onFollowOverviewPlaybackChange={onFollowOverviewPlaybackChange}
              style={subtitleStyle}
              onStyleChange={setSubtitleStyle}
            />
        ) : null}
      />
      <WorkspaceMediaSeekNotice seekRequest={playerSeekRequest} />
      {isAudioSource ? (
        <div className="workspace-elevated-panel rounded-3xl border p-8 text-center text-sm font-semibold text-stone-600 shadow-sm dark:text-zinc-300">
          音频文件暂不支持预览
        </div>
      ) : videoSource ? (
        <div className="workspace-elevated-panel relative aspect-video max-h-[72vh] w-full overflow-hidden rounded-3xl border bg-black shadow-sm">
          <video
            key={videoSource}
            ref={videoRef}
            className="h-full w-full bg-black object-contain"
            controls
            controlsList="nodownload noplaybackrate noremoteplayback"
            disablePictureInPicture
            preload="metadata"
            onPlay={() => setIsPlaying(true)}
            onPause={() => setIsPlaying(false)}
            onEnded={() => {
              setIsPlaying(false);
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
          <WorkspaceSubtitleDisplay
            videoRef={videoRef}
            subtitleTrackRef={subtitleTrackRef}
            subtitleSource={subtitleSource}
            enabled={subtitlesEnabled}
            style={{ ...subtitleStyle, onPositionChange: (position) => updateSubtitleStyle({ position }) }}
          />
        </div>
      ) : (
        // 未下载的媒体没有可播放源：给一个和播放器等大的 16:9 占位，
        // 说明当前状态并指向左栏的下载入口，而不是留一条没有信息的黑条。
        <div className="workspace-elevated-panel flex aspect-video max-h-[72vh] w-full flex-col items-center justify-center gap-3 overflow-hidden rounded-3xl border border-stone-800 bg-stone-950 px-6 text-center shadow-sm">
          <span className="flex h-12 w-12 items-center justify-center rounded-2xl bg-white/10 text-stone-300">
            <Download size={22} aria-hidden="true" />
          </span>
          <p className="text-sm font-semibold text-stone-200">视频尚未下载</p>
          <p className="max-w-sm text-xs leading-relaxed text-stone-400">
            在左侧来源列表点击「下载视频」，下载完成后即可在这里预览。
          </p>
        </div>
      )}
      <AnimatePresence initial={false}>
        {isPlaying && typeof onFocusOverviewAtTime === "function" ? (
          <motion.div
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 8 }}
            transition={{ duration: 0.2, ease: "easeOut" }}
            className="mt-2 flex justify-center"
          >
            <button
              type="button"
              onClick={openCurrentTranscript}
              className="inline-flex items-center gap-2 rounded-lg border border-accent/30 bg-accent/10 px-4 py-2.5 text-sm font-semibold text-accent shadow-sm transition-colors hover:border-accent/50 hover:bg-accent/15 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/40 dark:bg-accent/15 dark:hover:bg-accent/20"
            >
              <Captions size={17} aria-hidden="true" />
              查看当前转写
            </button>
          </motion.div>
        ) : null}
      </AnimatePresence>
    </div>
  );
}
