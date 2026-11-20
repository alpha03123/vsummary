import { useState } from "react";
import { Film } from "lucide-react";
import { useWorkspaceRuntime } from "../../../runtime/WorkspaceProvider";

// Videos without a cover get a neutral tile: the old per-id hues (rose, amber, violet…) read as
// broken images next to real covers, and colours belong to the theme's roles, not to components.
export function WorkspaceCoverPlaceholder({ iconSize = 28, className = "" }) {
  return (
    <div className={`flex h-full w-full items-center justify-center bg-soft text-ghost ${className}`}>
      <Film size={iconSize} strokeWidth={1.4} />
    </div>
  );
}

/** A video cover that falls back to a tinted placeholder when there is no image or it fails to load. */
export function WorkspaceCover({ url, seed, alt = "", iconSize, className = "", imageClassName = "" }) {
  const { api } = useWorkspaceRuntime();
  const [failedUrl, setFailedUrl] = useState(null);
  if (!url || failedUrl === url) {
    return <WorkspaceCoverPlaceholder iconSize={iconSize} className={className} />;
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
