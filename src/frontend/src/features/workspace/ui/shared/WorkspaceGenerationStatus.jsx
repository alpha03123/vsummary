import { useEffect, useRef, useState } from "react";
import { LoaderCircle } from "lucide-react";

export function WorkspaceGenerationStatus({ snapshot, label }) {
  const localStartedAt = useRef(Date.now() / 1000);
  const [elapsedSeconds, setElapsedSeconds] = useState(0);
  const startedAt = snapshot?.startedAt;
  const snapshotElapsed = snapshot?.elapsedSeconds ?? 0;

  useEffect(() => {
    const updateElapsed = () => {
      const start = Number.isFinite(startedAt) && startedAt > 0 ? startedAt : localStartedAt.current;
      setElapsedSeconds(Math.max(snapshotElapsed, Date.now() / 1000 - start, 0));
    };
    updateElapsed();
    const timer = window.setInterval(updateElapsed, 1000);
    return () => window.clearInterval(timer);
  }, [startedAt, snapshotElapsed]);

  return (
    <div className="motion-fade-up mt-6 w-full max-w-2xl">
      <div className="workspace-elevated-panel flex items-center gap-3 rounded-3xl border p-5">
        <LoaderCircle size={18} strokeWidth={2.2} className="shrink-0 animate-spin text-accent" />
        <p className="text-sm text-stone-600 dark:text-zinc-400">
          {snapshot?.detail || label}
          <span className="mx-2 text-stone-300 dark:text-zinc-600">·</span>
          <span className="font-medium text-stone-700 dark:text-zinc-200">已用 {Math.round(elapsedSeconds)} 秒</span>
        </p>
      </div>
    </div>
  );
}
