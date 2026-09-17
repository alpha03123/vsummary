import { useEffect, useRef, useState } from "react";

function activeCueText(track) {
  return Array.from(track?.activeCues ?? [])
    .map((cue) => cue.text?.trim())
    .filter(Boolean)
    .join("\n");
}

export function WorkspaceSubtitleDisplay({ videoRef, subtitleTrackRef, subtitleSource, enabled, style }) {
  const [text, setText] = useState("");
  const [containerHeight, setContainerHeight] = useState(0);
  const dragOriginRef = useRef(null);
  const containerRef = useRef(null);

  useEffect(() => {
    const trackElement = subtitleTrackRef.current;
    const track = trackElement?.track;
    if (!track) {
      return undefined;
    }
    const sync = () => setText(activeCueText(track));
    const trackElementSync = () => sync();
    const video = videoRef?.current;
    track.mode = "hidden";
    track.addEventListener("cuechange", sync);
    trackElement.addEventListener("load", trackElementSync);
    video?.addEventListener("timeupdate", sync);
    video?.addEventListener("loadeddata", sync);
    sync();
    return () => {
      track.removeEventListener("cuechange", sync);
      trackElement.removeEventListener("load", trackElementSync);
      video?.removeEventListener("timeupdate", sync);
      video?.removeEventListener("loadeddata", sync);
    };
  }, [subtitleSource, subtitleTrackRef, videoRef]);

  useEffect(() => {
    const move = (event) => {
      const origin = dragOriginRef.current;
      if (!origin) return;
      const position = Math.min(92, Math.max(8, origin.position + ((event.clientY - origin.clientY) / origin.height) * 100));
      style.onPositionChange?.(position);
    };
    const stop = () => { dragOriginRef.current = null; };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", stop);
    return () => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", stop);
    };
  }, [style]);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) {
      return undefined;
    }
    const updateHeight = () => setContainerHeight(container.getBoundingClientRect().height);
    const observer = new ResizeObserver(updateHeight);
    observer.observe(container);
    updateHeight();
    return () => observer.disconnect();
  }, []);

  return (
    <div ref={containerRef} className="pointer-events-none absolute inset-0 overflow-hidden" aria-live="off">
      {enabled && text ? <button
        type="button"
        aria-label="拖动调整字幕位置"
        title="拖动调整字幕位置"
        onPointerDown={(event) => {
          const height = event.currentTarget.parentElement?.getBoundingClientRect().height ?? 0;
          if (height) dragOriginRef.current = { clientY: event.clientY, height, position: style.position };
        }}
        className="pointer-events-auto absolute left-1/2 max-w-[78%] -translate-x-1/2 -translate-y-1/2 cursor-ns-resize touch-none rounded px-2.5 py-1 text-center font-semibold leading-relaxed shadow-[0_1px_2px_rgba(0,0,0,0.65)]"
        style={{
          top: `${style.position}%`,
          color: style.color,
          backgroundColor: style.backgroundColor,
          fontSize: `${containerHeight * ((style.fontScale ?? 4.2) / 100)}px`,
          whiteSpace: "pre-wrap",
        }}
      >
        {text}
      </button> : null}
    </div>
  );
}
