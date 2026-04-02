import { toWorkspaceLibrary, toWorkspaceSummary } from "./workspaceViewModel";

export async function loadWorkspaceLibrary() {
  return toWorkspaceLibrary(await fetchJson("/api/videos"));
}

export async function loadVideoSummary(seriesId, videoId) {
  return toWorkspaceSummary(await fetchJson(`/api/videos/${encodeURIComponent(seriesId)}/${encodeURIComponent(videoId)}/summary`));
}

export async function generateVideoSummary(seriesId, videoId) {
  return toWorkspaceSummary(
    await fetchJson(`/api/videos/${encodeURIComponent(seriesId)}/${encodeURIComponent(videoId)}/generate`, {
      method: "POST",
    }),
  );
}

async function fetchJson(path, init) {
  const response = await fetch(path, init);
  if (!response.ok) {
    throw new Error(`加载失败：${path}`);
  }
  return response.json();
}
