import { useEffect, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { Captions } from "lucide-react";

import { formatRange } from "../../../shared/lib/time";

export function WorkspaceVideoPlayer({
  videoSource,
  subtitleSource = null,
  playerSeekRequest,
  videoSourceType = "video",
  onTimeUpdate,
  resumeSeconds = null,
  onPlaybackEnded,
  onOpenOverviewAtTime,
}) {
  const videoRef = useRef(null);
  const subtitleTrackRef = useRef(null);
  const resumedVideoSourceRef = useRef(null);
  const [isPlaying, setIsPlaying] = useState(false);
  const [subtitlesEnabled, setSubtitlesEnabled] = useState(Boolean(subtitleSource));
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
      track.mode = subtitlesEnabled ? "showing" : "hidden";
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
      onOpenOverviewAtTime?.(seconds);
    }
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="workspace-muted-panel rounded-3xl border p-4">
        <p className="mb-2 text-xs font-bold uppercase text-stone-600 dark:text-stone-400">Media Preview</p>
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
          <video
            key={videoSource}
            ref={videoRef}
            className="h-full w-full max-h-[72vh] bg-black"
            controls
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
                default={subtitlesEnabled}
              />
            ) : null}
          </video>
        </div>
      )}
      {!isAudioSource && subtitleSource ? (
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
      <AnimatePresence initial={false}>
        {isPlaying && typeof onOpenOverviewAtTime === "function" ? (
          <motion.div
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 8 }}
            transition={{ duration: 0.2, ease: "easeOut" }}
            className="flex justify-center"
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
