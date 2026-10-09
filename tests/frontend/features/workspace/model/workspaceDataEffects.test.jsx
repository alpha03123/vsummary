import { useReducer } from "react";
import { act, renderHook, waitFor } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import { createWorkspaceDataEffects } from "@workspace/workspace/model/useWorkspaceDataEffects";
import { workspaceReducer } from "@workspace/workspace/model/workspaceReducer";
import { buildSeriesGenerationTaskKey, createInitialWorkspaceState } from "@workspace/workspace/model/workspaceState";

function setup(jobId = null) {
  let completed = false;
  const library = { workspace: { id: "workspace" }, series: [{ id: "series-a", videos: [{ id: "video-1", processed: false }] }] };
  const readyLibrary = { ...library, series: [{ id: "series-a", videos: [{ id: "video-1", processed: true }] }] };
  const api = Object.fromEntries([
    "loadAgentContextUsage", "loadAgentSessionRecovery", "loadSeriesMindmap",
    "loadVideoKnowledgeCards", "loadVideoMindmap", "loadVideoNotes", "loadVideoSummary",
  ].map((name) => [name, vi.fn().mockResolvedValue(null)]));
  api.checkBackendHealth = vi.fn(() => new Promise(() => {}));
  api.loadWorkspaceLibrary = vi.fn(async () => completed ? readyLibrary : library);
  api.loadVideoTools = vi.fn(async () => ({ overview: { generated: false }, mindmap: { generated: false },
    knowledgeCards: { generated: false }, aiSummary: { generated: completed } }));
  api.loadVideoAiSummary = vi.fn().mockResolvedValue({ content: "Generated AI summary" });
  api.subscribeSeriesGenerationProgress = vi.fn(() => vi.fn());
  const taskKey = buildSeriesGenerationTaskKey("series-a");
  const state = { ...createInitialWorkspaceState(), library, selectedContextType: "series", selectedSeriesId: "series-a",
    generationTasksByKey: { [taskKey]: { taskKey, mode: "series", seriesId: "series-a", jobId,
      snapshot: { status: "running", progress: 0 } } } };
  const useEffects = createWorkspaceDataEffects(api);
  const hook = renderHook(() => {
    const [current, dispatch] = useReducer(workspaceReducer, state);
    useEffects(current, dispatch);
    return { state: current, dispatch };
  });
  return { api, hook, finish: () => { completed = true; } };
}

it("does not subscribe to a series before its submission has a job ID", () => {
  const { api } = setup();
  expect(api.subscribeSeriesGenerationProgress).not.toHaveBeenCalled();
});

it("refreshes the open video AI summary when a recovered series job completes", async () => {
  const { api, hook, finish } = setup("batch-1");
  expect(api.subscribeSeriesGenerationProgress).toHaveBeenCalledWith("series-a", "batch-1", expect.any(Function));
  await act(async () => hook.result.current.dispatch({ type: "video_selected", seriesId: "series-a", videoId: "video-1" }));
  expect(hook.result.current.state.aiSummary).toBeNull();
  finish();
  await act(async () => api.subscribeSeriesGenerationProgress.mock.calls[0][2]({ status: "completed", progress: 100 }));
  await waitFor(() => expect(hook.result.current.state.aiSummary?.content).toBe("Generated AI summary"));
  expect(api.loadVideoAiSummary).toHaveBeenCalledWith("series-a", "video-1");
});

it("reloads AI summary on series completion without relying on a library replacement", async () => {
  const { api, hook, finish } = setup();
  await act(async () => hook.result.current.dispatch({ type: "video_selected", seriesId: "series-a", videoId: "video-1" }));
  expect(hook.result.current.state.aiSummary).toBeNull();
  finish();
  await act(async () => hook.result.current.dispatch({ type: "generation_status_loaded",
    taskKey: buildSeriesGenerationTaskKey("series-a"), mode: "series", seriesId: "series-a", jobId: "batch-1",
    snapshot: { status: "completed", progress: 100 }, subscriptionActive: false }));
  await waitFor(() => expect(hook.result.current.state.aiSummary?.content).toBe("Generated AI summary"));
  expect(api.loadWorkspaceLibrary).not.toHaveBeenCalled();
});
