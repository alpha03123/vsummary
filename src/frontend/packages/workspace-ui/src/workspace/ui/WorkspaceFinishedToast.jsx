import { useEffect, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { CheckCircle2, X } from "lucide-react";

const AUTO_HIDE_MS = 15000;

/**
 * Videos of the open series that became processed since the last library refresh, except the one
 * on screen (its panels update by themselves). Switching series resets the baseline, so opening
 * a series never reports its old videos.
 */
function useNewlyProcessedVideos(series, currentVideoId) {
  const baseline = useRef({ seriesId: null, processed: new Set() });
  const [finished, setFinished] = useState([]);
  useEffect(() => {
    const videos = series?.videos ?? [];
    const processed = new Set(videos.filter((video) => video.processed).map((video) => video.id));
    const previous = baseline.current;
    if (previous.seriesId === (series?.id ?? null)) {
      const fresh = videos.filter((video) => processed.has(video.id) && !previous.processed.has(video.id) && video.id !== currentVideoId);
      if (fresh.length) setFinished(fresh);
    } else {
      setFinished([]);
    }
    baseline.current = { seriesId: series?.id ?? null, processed };
  }, [series, currentVideoId]);
  return [finished, () => setFinished([])];
}

/** "生成好了，去看" — the moment a new user otherwise misses, because the result lands in another video. */
export function WorkspaceFinishedToast({ series, currentVideoId, onOpenVideo }) {
  const [finished, dismiss] = useNewlyProcessedVideos(series, currentVideoId);
  useEffect(() => {
    if (!finished.length) return undefined;
    const timer = window.setTimeout(dismiss, AUTO_HIDE_MS);
    return () => window.clearTimeout(timer);
  }, [finished]);
  const first = finished[0];
  return (
    <AnimatePresence>
      {first ? (
        <motion.div
          role="status"
          initial={{ opacity: 0, y: -12 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -12 }}
          transition={{ duration: 0.2 }}
          className="workspace-panel absolute inset-x-3 top-3 z-40 mx-auto flex max-w-md items-center gap-3 rounded-2xl border px-4 py-3 shadow-lg"
        >
          <CheckCircle2 size={18} className="shrink-0 text-success" aria-hidden="true" />
          <p className="min-w-0 flex-1 truncate text-sm text-body">
            {finished.length === 1
              ? <><span className="font-semibold text-strong">{first.title}</span> 已生成</>
              : <><span className="font-semibold text-strong">{finished.length} 个视频</span>已生成</>}
          </p>
          <button
            type="button"
            onClick={() => { onOpenVideo(series.id, first.id); dismiss(); }}
            className="shrink-0 rounded-xl bg-accent px-3.5 py-1.5 text-xs font-semibold text-on-accent transition-colors hover:bg-accent/90"
          >
            查看
          </button>
          <button type="button" onClick={dismiss} aria-label="关闭提示" className="-mr-1 inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-lg text-faint transition-colors hover:bg-soft hover:text-strong">
            <X size={15} />
          </button>
        </motion.div>
      ) : null}
    </AnimatePresence>
  );
}
