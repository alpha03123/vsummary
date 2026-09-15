import { formatRange } from "../../../../shared/lib/time";

export function WorkspaceMediaPreviewHeader({ subtitleSettings = null }) {
  return (
    <div className="workspace-muted-panel relative rounded-3xl border p-4">
      <div className="mb-2 flex items-center justify-between gap-3">
        <p className="text-xs font-bold uppercase text-stone-600 dark:text-stone-400">Media Preview</p>
        {subtitleSettings}
      </div>
    </div>
  );
}

export function WorkspaceMediaSeekNotice({ seekRequest = null }) {
  if (!seekRequest) {
    return null;
  }

  return (
    <div className="rounded-2xl border border-info/20 bg-info-subtle px-4 py-3 text-sm text-stone-800 dark:text-stone-100">
      <p className="font-semibold">
        已定位到 {formatRange(seekRequest.seconds, seekRequest.endSeconds ?? seekRequest.seconds)}
        {seekRequest.chapterTitle ? ` · ${seekRequest.chapterTitle}` : ""}
      </p>
      {seekRequest.query ? (
        <p className="mt-1 text-stone-600 dark:text-stone-300">检索问题：{seekRequest.query}</p>
      ) : null}
      {seekRequest.matchedText ? (
        <p className="mt-2 line-clamp-3 text-stone-700 dark:text-stone-200">{seekRequest.matchedText}</p>
      ) : null}
    </div>
  );
}
