import { createPortal } from "react-dom";
import { useEffect, useRef, useState } from "react";
import { RotateCcw, Settings2 } from "lucide-react";

import { WorkspaceToggleSwitch } from "./shared/WorkspaceSettingsControls";

export const DEFAULT_SUBTITLE_STYLE = {
  color: "#ffffff",
  backgroundColor: "#111827",
  fontSize: 20,
  position: 82,
};

export function WorkspaceNativeSubtitleSettings({
  subtitlesEnabled,
  onSubtitlesEnabledChange,
  followOverviewPlayback = false,
  onFollowOverviewPlaybackChange,
  style,
  onStyleChange,
}) {
  const [open, setOpen] = useState(false);
  const [panelPosition, setPanelPosition] = useState(null);
  const triggerRef = useRef(null);
  const panelRef = useRef(null);
  const pointerStartedInsideRef = useRef(false);
  const updateStyle = (next) => onStyleChange({ ...style, ...next });

  useEffect(() => {
    if (!open) {
      return undefined;
    }

    const updatePanelPosition = () => {
      const bounds = triggerRef.current?.getBoundingClientRect();
      if (!bounds) {
        return;
      }
      setPanelPosition({ left: bounds.left, top: bounds.bottom + 8 });
    };
    updatePanelPosition();
    window.addEventListener("resize", updatePanelPosition);
    window.addEventListener("scroll", updatePanelPosition, true);
    return () => {
      window.removeEventListener("resize", updatePanelPosition);
      window.removeEventListener("scroll", updatePanelPosition, true);
    };
  }, [open]);

  useEffect(() => {
    if (!open) {
      return undefined;
    }

    const isInside = (target) => (
      triggerRef.current?.contains(target) || panelRef.current?.contains(target)
    );
    const recordPointerStart = (event) => {
      pointerStartedInsideRef.current = Boolean(isInside(event.target));
    };
    const dismissAfterOutsideClick = (event) => {
      const endedInside = Boolean(isInside(event.target));
      if (!pointerStartedInsideRef.current && !endedInside) {
        setOpen(false);
      }
      pointerStartedInsideRef.current = false;
    };
    const dismissOnEscape = (event) => {
      if (event.key === "Escape") {
        setOpen(false);
      }
    };
    window.addEventListener("pointerdown", recordPointerStart);
    window.addEventListener("pointerup", dismissAfterOutsideClick);
    window.addEventListener("keydown", dismissOnEscape);
    return () => {
      window.removeEventListener("pointerdown", recordPointerStart);
      window.removeEventListener("pointerup", dismissAfterOutsideClick);
      window.removeEventListener("keydown", dismissOnEscape);
    };
  }, [open]);

  return (
    <div>
      <button
        ref={triggerRef}
        type="button"
        aria-label="字幕设置"
        aria-expanded={open}
        title="字幕设置"
        onClick={() => setOpen((current) => !current)}
        className="workspace-elevated-panel inline-flex h-9 w-9 items-center justify-center rounded-lg border text-stone-600 transition-colors hover:border-accent/50 hover:text-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/40 dark:text-stone-300"
      >
        <Settings2 size={17} aria-hidden="true" />
      </button>
      {open && panelPosition ? createPortal(
        <div
          ref={panelRef}
          className="workspace-elevated-panel fixed z-[70] w-64 max-w-[calc(100vw-2rem)] rounded-2xl border p-3 text-stone-900 shadow-xl dark:text-stone-100"
          style={{ left: panelPosition.left, top: panelPosition.top }}
        >
          <div className="mb-3 flex items-center justify-between">
            <p className="text-sm font-bold">字幕设置</p>
            <button
              type="button"
              onClick={() => onStyleChange(DEFAULT_SUBTITLE_STYLE)}
              className="inline-flex h-7 w-7 items-center justify-center rounded-md text-stone-500 transition-colors hover:bg-stone-100 hover:text-accent dark:hover:bg-stone-800"
              aria-label="恢复默认字幕样式"
              title="恢复默认字幕样式"
            >
              <RotateCcw size={15} aria-hidden="true" />
            </button>
          </div>
          <div className="mb-3 flex items-center justify-between rounded-lg border border-stone-200 bg-stone-50 px-3 py-2 dark:border-stone-700 dark:bg-stone-800/50">
            <span className="text-sm font-semibold">显示字幕</span>
            <WorkspaceToggleSwitch
              checked={subtitlesEnabled}
              onChange={() => onSubtitlesEnabledChange(!subtitlesEnabled)}
              ariaLabel="显示或隐藏字幕"
            />
          </div>
          {onFollowOverviewPlaybackChange ? (
            <div className="mb-3 flex items-center justify-between rounded-lg border border-stone-200 bg-stone-50 px-3 py-2 dark:border-stone-700 dark:bg-stone-800/50">
              <div>
                <p className="text-sm font-semibold">概况跟随播放</p>
                <p className="mt-0.5 text-xs text-stone-500 dark:text-stone-400">当前原文保持在中间</p>
              </div>
              <WorkspaceToggleSwitch
                checked={followOverviewPlayback}
                onChange={() => onFollowOverviewPlaybackChange(!followOverviewPlayback)}
                ariaLabel="AI 概况跟随播放"
              />
            </div>
          ) : null}
          <label className="mb-2 flex items-center justify-between gap-3 text-xs font-semibold">
            字体颜色
            <input aria-label="字幕字体颜色" type="color" value={style.color} onChange={(event) => updateStyle({ color: event.target.value })} className="h-7 w-12 cursor-pointer rounded-lg border border-stone-300 bg-transparent p-1 dark:border-stone-600" />
          </label>
          <label className="mb-2 flex items-center justify-between gap-3 text-xs font-semibold">
            底色
            <input aria-label="字幕底色" type="color" value={style.backgroundColor} onChange={(event) => updateStyle({ backgroundColor: event.target.value })} className="h-7 w-12 cursor-pointer rounded-lg border border-stone-300 bg-transparent p-1 dark:border-stone-600" />
          </label>
          <label className="mb-2 block text-xs font-semibold">
            <span className="mb-1 flex justify-between"><span>字体大小</span><span className="text-accent">{style.fontSize}px</span></span>
            <input aria-label="字幕字体大小" type="range" min="14" max="44" value={style.fontSize} onChange={(event) => updateStyle({ fontSize: Number(event.target.value) })} className="w-full accent-accent" />
          </label>
          <label className="block text-xs font-semibold">
            <span className="mb-1 flex justify-between"><span>字幕位置</span><span className="text-accent">{Math.round(style.position)}%</span></span>
            <input aria-label="字幕位置" type="range" min="8" max="92" value={style.position} onChange={(event) => updateStyle({ position: Number(event.target.value) })} className="w-full accent-accent" />
          </label>
        </div>,
        document.body,
      ) : null}
    </div>
  );
}
