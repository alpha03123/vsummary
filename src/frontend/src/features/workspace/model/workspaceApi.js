import { currentLibrary } from "./workspaceState";
import { toWorkspaceLibrary, toWorkspaceSummary, unwrapSummaryPayload } from "./workspaceViewModel";

export async function loadWorkspaceFromLocation(search = window.location.search) {
  const params = new URLSearchParams(search);
  const summaryPath = params.get("summary");
  const mindmapPath = params.get("mindmap");

  return summaryPath
    ? loadRemoteWorkspace(summaryPath, mindmapPath)
    : loadDefaultWorkspace();
}

export async function readJsonFile(file) {
  const text = await file.text();
  return JSON.parse(text);
}

async function loadDefaultWorkspace() {
  const library = toWorkspaceLibrary(await fetchJson("/api/videos"));
  const firstVideo = library.videos?.[0];
  if (!firstVideo) {
    throw new Error("sample/output 中没有可展示的视频总结。");
  }

  const summaryPayload = await fetchJson(`/api/videos/${encodeURIComponent(firstVideo.id)}/summary`);
  return { summary: toWorkspaceSummary(summaryPayload), library };
}

async function loadRemoteWorkspace(summaryPath, mindmapPath) {
  const [summaryPayload, mindmapData] = await Promise.all([
    fetchJson(summaryPath),
    mindmapPath ? fetchJson(mindmapPath) : Promise.resolve(null),
  ]);

  const summary = toWorkspaceSummary(summaryPayload);
  const rawSummary = unwrapSummaryPayload(summaryPayload);
  return {
    summary: {
      ...summary,
      mindmap: mindmapData ? toWorkspaceSummary({ ...rawSummary, mindmap: mindmapData }).mindmap : summary.mindmap,
    },
    library: currentLibrary(null, summary),
  };
}

async function fetchJson(path) {
  const response = await fetch(path);
  if (!response.ok) {
    throw new Error(`加载失败：${path}`);
  }
  return response.json();
}
