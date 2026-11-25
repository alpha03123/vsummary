import { ChevronRight, FolderKanban, PlaySquare } from "lucide-react";

/**
 * Says what the panels below belong to (the whole series or one video) when the sidebar that
 * normally shows it is hidden — always on phones, on desktop only while it is collapsed.
 * Tapping it opens the video list, which is also where the user switches.
 */
export function WorkspaceScopeBar({ series, video, onOpenList }) {
  const videos = series?.videos ?? [];
  const index = video ? videos.findIndex((item) => item.id === video.id) : -1;
  const canSwitch = videos.length > 1;
  const Icon = video ? PlaySquare : FolderKanban;
  return (
    <button
      type="button"
      onClick={onOpenList}
      aria-label={canSwitch ? "打开视频列表切换" : "打开视频列表"}
      className="mx-3 mt-2 flex min-w-0 shrink-0 items-center gap-2 rounded-xl border border-line/80 bg-surface px-3 py-2 text-left shadow-xs transition-colors hover:border-accent/40 md:mx-4"
    >
      <Icon size={15} className="shrink-0 text-accent" aria-hidden="true" />
      <span className="min-w-0 flex-1 truncate text-sm">
        <span className="font-semibold text-strong">{video ? video.title : "整个系列"}</span>
        {video && canSwitch && index >= 0 ? <span className="text-faint"> · {index + 1} / {videos.length}</span> : null}
        {!video ? <span className="text-faint"> · {videos.length} 个视频</span> : null}
      </span>
      {canSwitch ? (
        <span className="inline-flex shrink-0 items-center gap-0.5 text-xs font-semibold text-accent">
          切换 <ChevronRight size={14} aria-hidden="true" />
        </span>
      ) : null}
    </button>
  );
}
