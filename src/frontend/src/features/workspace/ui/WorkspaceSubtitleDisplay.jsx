import { useEffect, useRef, useState } from "react";

function activeCueText(track) {
  return Array.from(track?.activeCues ?? [])
    .map((cue) => cue.text?.trim())
    .filter(Boolean)
    .join("\n");
}

export function WorkspaceSubtitleDisplay({ subtitleTrackRef, subtitleSource, enabled, style }) {
  const [text, setText] = useState("");
  const dragOriginRef = useRef(null);

  useEffect(() => {
    const trackElement = subtitleTrackRef.current;
    const track = trackElement?.track;
    if (!track) {
      return undefined;
    }
    const sync = () => setText(activeCueText(track));
    track.mode = "hidden";
    track.addEventListener("cuechange", sync);
    sync();
    return () => track.removeEventListener("cuechange", sync);
  }, [subtitleSource, subtitleTrackRef]);

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

  if (!enabled || !text) {
    return null;
  }

  return (
    <div className="pointer-events-none absolute inset-0 overflow-hidden" aria-live="off">
      <button
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
          fontSize: `${style.fontSize}px`,
          whiteSpace: "pre-wrap",
        }}
      >
        {text}
      </button>
    </div>
  );
}
