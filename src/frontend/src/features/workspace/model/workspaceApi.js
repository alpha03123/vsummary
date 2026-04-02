import { toWorkspaceLibrary, toWorkspaceMindmap, toWorkspaceSummary, toWorkspaceTools } from "./workspaceViewModel";

export async function loadWorkspaceLibrary() {
  return toWorkspaceLibrary(await fetchJson("/api/videos"));
}

export async function loadVideoSummary(seriesId, videoId) {
  return toWorkspaceSummary(await fetchJson(`/api/videos/${encodeURIComponent(seriesId)}/${encodeURIComponent(videoId)}/summary`));
}

export async function loadVideoTools(seriesId, videoId) {
  return toWorkspaceTools(await fetchJson(`/api/videos/${encodeURIComponent(seriesId)}/${encodeURIComponent(videoId)}/tools`));
}

export async function loadVideoMindmap(seriesId, videoId) {
  return toWorkspaceMindmap(await fetchJson(`/api/videos/${encodeURIComponent(seriesId)}/${encodeURIComponent(videoId)}/mindmap`));
}

export async function generateVideoSummary(seriesId, videoId) {
  return toWorkspaceSummary(
    await fetchJson(`/api/videos/${encodeURIComponent(seriesId)}/${encodeURIComponent(videoId)}/generate`, {
      method: "POST",
    }),
  );
}

export async function generateVideoMindmap(seriesId, videoId) {
  return toWorkspaceMindmap(
    await fetchJson(`/api/videos/${encodeURIComponent(seriesId)}/${encodeURIComponent(videoId)}/mindmap/generate`, {
      method: "POST",
    }),
  );
}

export function getVideoPreviewUrl(seriesId, videoId) {
  return `/api/videos/${encodeURIComponent(seriesId)}/${encodeURIComponent(videoId)}/preview`;
}

async function fetchJson(path, init) {
  const response = await fetch(path, init);
  if (!response.ok) {
    throw new Error(`加载失败：${path}`);
  }
  return response.json();
}
