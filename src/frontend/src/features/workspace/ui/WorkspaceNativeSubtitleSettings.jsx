import { createPortal } from "react-dom";
import { useEffect, useRef, useState } from "react";
import { Palette, RotateCcw, Settings2, Type } from "lucide-react";

import { WorkspaceToggleSwitch } from "./shared/WorkspaceSettingsControls";

export const DEFAULT_SUBTITLE_STYLE = {
  color: "#ffffff",
  backgroundColor: "#111827",
  fontScale: 4.2,
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
  const colorControls = [
    { id: "color", label: "文字颜色", value: style.color, icon: Type },
    { id: "backgroundColor", label: "背景颜色", value: style.backgroundColor, icon: Palette },
  ];

  useEffect(() => {
    if (!open) {
      return undefined;
    }

    const updatePanelPosition = () => {
      const bounds = triggerRef.current?.getBoundingClientRect();
      if (!bounds) {
        return;
      }
      const panelWidth = Math.min(320, window.innerWidth - 32);
      const left = Math.min(
        Math.max(16, bounds.right - panelWidth),
        window.innerWidth - panelWidth - 16,
      );
      setPanelPosition({ left, top: bounds.bottom + 8, width: panelWidth });
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
        className="workspace-elevated-panel inline-flex h-9 w-9 items-center justify-center rounded-xl border text-stone-600 transition-colors duration-200 hover:border-accent/50 hover:bg-accent/5 hover:text-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/40 dark:text-stone-300 dark:hover:bg-accent/10"
      >
        <Settings2 size={17} aria-hidden="true" />
      </button>
      {open && panelPosition ? createPortal(
        <div
          ref={panelRef}
          className="workspace-elevated-panel fixed z-[70] max-h-[calc(100vh-2rem)] overflow-y-auto rounded-3xl border p-4 text-stone-900 shadow-2xl motion-fade-scale dark:text-stone-100"
          style={{ left: panelPosition.left, top: panelPosition.top, width: panelPosition.width }}
        >
          <div className="mb-4 flex items-center justify-between border-b border-stone-200/80 pb-3 dark:border-stone-800">
            <div>
              <p className="text-sm font-bold tracking-tight">字幕外观</p>
              <p className="mt-0.5 text-xs text-stone-500 dark:text-stone-400">调整播放时的字幕显示效果</p>
            </div>
            <button
              type="button"
              onClick={() => onStyleChange(DEFAULT_SUBTITLE_STYLE)}
              className="inline-flex h-8 w-8 items-center justify-center rounded-lg text-stone-500 transition-colors hover:bg-accent/10 hover:text-accent dark:text-stone-400 dark:hover:bg-accent/15"
              aria-label="恢复默认字幕样式"
              title="恢复默认字幕样式"
            >
              <RotateCcw size={15} aria-hidden="true" />
            </button>
          </div>
          <div className="workspace-muted-panel mb-2 flex items-center justify-between rounded-2xl border px-4 py-3">
            <div>
              <p className="text-sm font-semibold">显示字幕</p>
              <p className="mt-0.5 text-xs text-stone-500 dark:text-stone-400">在播放器中显示当前字幕</p>
            </div>
            <WorkspaceToggleSwitch
              checked={subtitlesEnabled}
              onChange={() => onSubtitlesEnabledChange(!subtitlesEnabled)}
              ariaLabel="显示或隐藏字幕"
            />
          </div>
          {onFollowOverviewPlaybackChange ? (
            <div className="workspace-muted-panel mb-4 flex items-center justify-between rounded-2xl border px-4 py-3">
              <div>
                <p className="text-sm font-semibold">概况跟随播放</p>
                <p className="mt-0.5 text-xs text-stone-500 dark:text-stone-400">播放时自动定位当前原文</p>
              </div>
              <WorkspaceToggleSwitch
                checked={followOverviewPlayback}
                onChange={() => onFollowOverviewPlaybackChange(!followOverviewPlayback)}
                ariaLabel="AI 概况跟随播放"
              />
            </div>
          ) : null}
          <section className="mt-4">
            <p className="mb-2 px-1 text-[10px] font-bold uppercase tracking-widest text-stone-500 dark:text-stone-400">颜色</p>
            <div className="grid grid-cols-2 gap-2">
              {colorControls.map(({ id, label, value, icon: Icon }) => (
                <label key={id} className="workspace-muted-panel flex cursor-pointer items-center gap-2 rounded-xl border px-3 py-2.5 transition-colors hover:border-accent/40">
                  <Icon size={15} className="shrink-0 text-stone-500 dark:text-stone-400" aria-hidden="true" />
                  <span className="min-w-0 flex-1 text-xs font-semibold">{label}</span>
                  <span className="relative h-6 w-6 shrink-0 overflow-hidden rounded-md border border-stone-300 shadow-sm dark:border-stone-600" style={{ backgroundColor: value }}>
                    <input
                      aria-label={`字幕${label}`}
                      type="color"
                      value={value}
                      onChange={(event) => updateStyle({ [id]: event.target.value })}
                      className="absolute inset-[-0.5rem] h-10 w-10 cursor-pointer opacity-0"
                    />
                  </span>
                </label>
              ))}
            </div>
          </section>
          <section className="mt-4 space-y-3">
            <p className="px-1 text-[10px] font-bold uppercase tracking-widest text-stone-500 dark:text-stone-400">排版</p>
            <label className="workspace-muted-panel block cursor-pointer rounded-2xl border px-4 py-3">
              <span className="mb-2 flex items-center justify-between text-sm font-semibold"><span>字体大小</span><span className="text-accent">{style.fontScale}%</span></span>
              <input aria-label="字幕字体大小" type="range" min="1" max="8" step="0.1" value={style.fontScale} onChange={(event) => updateStyle({ fontScale: Number(event.target.value) })} className="block w-full cursor-pointer accent-accent" />
            </label>
            <label className="workspace-muted-panel block cursor-pointer rounded-2xl border px-4 py-3">
              <span className="mb-2 flex items-center justify-between text-sm font-semibold"><span>字幕位置</span><span className="text-accent">{Math.round(style.position)}%</span></span>
              <input aria-label="字幕位置" type="range" min="8" max="92" value={style.position} onChange={(event) => updateStyle({ position: Number(event.target.value) })} className="block w-full cursor-pointer accent-accent" />
            </label>
          </section>
        </div>,
        document.body,
      ) : null}
    </div>
  );
}
