import { useState } from "react";
import { Film } from "lucide-react";
import { useWorkspaceRuntime } from "../../../runtime/WorkspaceProvider";

// Soft tints for videos without a cover, picked from the id so a card keeps its colour between visits.
const PLACEHOLDER_TINTS = [
  "from-indigo-100 to-sky-50 text-indigo-300 dark:from-indigo-950/70 dark:to-slate-900 dark:text-indigo-800",
  "from-amber-100 to-orange-50 text-amber-300 dark:from-amber-950/60 dark:to-stone-900 dark:text-amber-800",
  "from-emerald-100 to-teal-50 text-emerald-300 dark:from-emerald-950/60 dark:to-stone-900 dark:text-emerald-800",
  "from-rose-100 to-pink-50 text-rose-300 dark:from-rose-950/60 dark:to-stone-900 dark:text-rose-800",
  "from-violet-100 to-fuchsia-50 text-violet-300 dark:from-violet-950/60 dark:to-stone-900 dark:text-violet-800",
  "from-stone-200 to-stone-50 text-stone-300 dark:from-stone-800 dark:to-stone-900 dark:text-stone-700",
];

function tintFor(seed) {
  let hash = 0;
  for (const character of String(seed ?? "")) hash = (hash * 31 + character.charCodeAt(0)) >>> 0;
  return PLACEHOLDER_TINTS[hash % PLACEHOLDER_TINTS.length];
}

export function WorkspaceCoverPlaceholder({ seed, iconSize = 28, className = "" }) {
  return (
    <div className={`flex h-full w-full items-center justify-center bg-gradient-to-br ${tintFor(seed)} ${className}`}>
      <Film size={iconSize} strokeWidth={1.6} />
    </div>
  );
}

/** A video cover that falls back to a tinted placeholder when there is no image or it fails to load. */
export function WorkspaceCover({ url, seed, alt = "", iconSize, className = "", imageClassName = "" }) {
  const { api } = useWorkspaceRuntime();
  const [failedUrl, setFailedUrl] = useState(null);
  if (!url || failedUrl === url) {
    return <WorkspaceCoverPlaceholder seed={seed} iconSize={iconSize} className={className} />;
  }
  const src = url.startsWith("/api/") && api?.resourceUrl ? api.resourceUrl(url) : url;
  return (
    <img
      src={src}
      alt={alt}
      loading="lazy"
      draggable={false}
      onError={() => setFailedUrl(url)}
      className={`h-full w-full object-cover ${className} ${imageClassName}`}
    />
  );
}

export function formatDuration(seconds) {
  if (typeof seconds !== "number" || !Number.isFinite(seconds) || seconds <= 0) return "";
  const total = Math.round(seconds);
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const rest = String(total % 60).padStart(2, "0");
  return hours > 0 ? `${hours}:${String(minutes).padStart(2, "0")}:${rest}` : `${minutes}:${rest}`;
}
