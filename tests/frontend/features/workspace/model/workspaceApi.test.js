import { afterEach, describe, expect, test, vi } from "vitest";
import { createWorkspaceApi } from "@workspace/workspace/model/workspaceApi";

const transport = { fetch: vi.fn(), subscribe: vi.fn(), CLOSED: 2 };
const { generateVideoSummary, processAgentVideo, cancelDurableJob,
  generateSeriesSummaries, subscribeSeriesGenerationProgress, subscribeVideoGenerationProgress,
  loadAgentSessionRecovery, subscribeDurableJobProgress, loadProviderUsage } = createWorkspaceApi(transport);

afterEach(() => {
  vi.resetAllMocks();
});

describe("series generation submission and progress", () => {
  test("returns the accepted job so the caller can read its status", async () => {
    transport.fetch.mockResolvedValue({ ok: true, json: async () => ({ job_id: "batch-1", status: "queued" }) });
    await expect(generateSeriesSummaries("series-1", { processingMode: "transcript" }))
      .resolves.toEqual({ jobId: "batch-1", status: "queued" });
    expect(JSON.parse(transport.fetch.mock.calls[0][1].body).processing_mode).toBe("transcript");
  });

  test("rejects an incomplete acceptance response at the API boundary", async () => {
    transport.fetch.mockResolvedValue({ ok: true, json: async () => ({ status: "queued" }) });
    await expect(generateSeriesSummaries("series-1")).rejects.toThrow("job_id 或 status");
  });

  test.each(["series", "video"])("consumes named progress events through to cancellation for %s", (scope) => {
    const handlers = new Map();
    const connection = { close: vi.fn(), addEventListener: (name, handler) => handlers.set(name, handler) };
    transport.subscribe.mockReturnValue(connection);
    const listener = vi.fn();
    if (scope === "series") subscribeSeriesGenerationProgress("series-1", listener);
    else subscribeVideoGenerationProgress("series-1", "video-1", listener);
    for (const status of ["running", "cancelled"]) {
      handlers.get("progress")({ data: JSON.stringify({ status, stage: status, progress: 20 }) });
    }
    expect(listener.mock.calls.map(([snapshot]) => snapshot.status)).toEqual(["running", "cancelled"]);
    expect(connection.close).toHaveBeenCalledOnce();
    connection.onerror();
    expect(listener).toHaveBeenCalledTimes(2);
  });
});

describe("loadAgentSessionRecovery", () => {
  test("restores assistant citations with recovered messages", async () => {
    transport.fetch.mockImplementation(async () => ({
      ok: true,
      json: async () => ({
        session_id: "series|series-1",
        restored: true,
        memory_key: "series|series-1",
        updated_at: "2026-05-15T00:00:00Z",
        message_count: 2,
        messages: [
          {
            role: "user",
            content: "这个结论来自哪里？",
            created_at: "2026-05-15T00:00:00Z",
          },
          {
            role: "assistant",
            content: "来自课程摘要。[1]",
            created_at: "2026-05-15T00:00:01Z",
            citations: [
              {
                id: "1",
                label: "Video 1",
                source_type: "summary",
                search_scope: "summary",
                slots: [
                  {
                    slot: 1,
                    target_type: "summary",
                    video_id: "video-1",
                    video_title: "Video 1",
                    text: "课程摘要证据",
                  },
                ],
              },
            ],
          },
        ],
      }),
    }));

    const recovery = await loadAgentSessionRecovery("series|series-1", null);

    expect(recovery.messages[1].citations).toEqual([
      {
        id: "1",
        label: "Video 1",
        source_type: "summary",
        search_scope: "summary",
        slots: [
          {
            slot: 1,
            target_type: "summary",
            video_id: "video-1",
            video_title: "Video 1",
            text: "课程摘要证据",
          },
        ],
      },
    ]);
  });
});

describe("linked video durable jobs", () => {
  test("selects the submitted job for the requested video", async () => {
    const fetchMock = vi.fn(async () => ({
      ok: true,
      json: async () => ({ jobs: [
        { job_id: "job-other", status: "queued", resource: { type: "video", id: "other-video" } },
        { job_id: "job-current", status: "queued", resource: { type: "video", id: "video-1" } },
      ] }),
    }));
    transport.fetch.mockImplementation(fetchMock);

    await expect(processAgentVideo("series-1", "video-1", { processingMode: "transcript" }))
      .resolves.toEqual({ jobId: "job-current", status: "queued" });
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/agent/series/series-1/process",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ video_ids: ["video-1"], processing_mode: "transcript" }),
      }),
    );
  });

  test("rejects a response without the requested video's job", async () => {
    transport.fetch.mockImplementation(async () => ({
      ok: true,
      json: async () => ({ jobs: [{ job_id: "job-other", status: "queued", resource: { type: "video", id: "other-video" } }] }),
    }));

    await expect(processAgentVideo("series-1", "video-1")).rejects.toThrow("当前视频的任务");
  });

  test("cancels the durable job by its ID", async () => {
    const fetchMock = vi.fn(async () => ({
      ok: true,
      json: async () => ({ job_id: "job/1", status: "cancelling" }),
    }));
    transport.fetch.mockImplementation(fetchMock);

    await expect(cancelDurableJob("job/1")).resolves.toMatchObject({ status: "cancelling" });
    expect(fetchMock).toHaveBeenCalledWith("/api/jobs/job%2F1/cancel", { method: "POST" });
  });
});

describe("generateVideoSummary", () => {
  test("keeps the durable job submission instead of parsing it as a summary", async () => {
    transport.fetch.mockImplementation(async () => ({
      ok: true,
      json: async () => ({ job_id: "job-1", status: "queued" }),
    }));

    await expect(generateVideoSummary("series-1", "video-1")).resolves.toEqual({ jobId: "job-1", status: "queued" });
  });
});

describe("subscribeDurableJobProgress", () => {
  test("preserves progress and separate tasks through concurrent picture events", () => {
    const listeners = {};
    transport.subscribe.mockImplementation(() => new class {
      addEventListener(type, listener) { listeners[type] = listener; }
      close() {}
    }());
    const listener = vi.fn();
    subscribeDurableJobProgress("job-pictures", listener);
    for (const [stage, progress] of [["summarize", 88], ["sample_frames", null], ["understand_frames", null], ["extract_screenshots", 92]]) {
      listeners.progress({ data: JSON.stringify({ status: "running", stage, progress }) });
    }
    const snapshot = listener.mock.calls.at(-1)[0];
    expect(snapshot.progress).toBe(92);
    expect(snapshot.steps.find((step) => step.id === "ai_summary").status).toBe("running");
    expect(snapshot.steps.find((step) => step.id === "chapter_images").status).toBe("running");
    expect(listener.mock.calls[1][0].progress).toBe(88);
  });
});

describe("loadProviderUsage", () => {
  test("uses the shared route and maps the statistics response for analytics", async () => {
    transport.fetch.mockResolvedValue({ok:true,json:async()=>({
      range:"30d",total:{prompt_tokens:12,completion_tokens:8,total_tokens:20},
      by_category:[{category:"chat",prompt_tokens:12,completion_tokens:8,total_tokens:20}],
      by_provider:[],recent:[],timeline_granularity:"hour",timeline:[],
    })});
    const usage=await loadProviderUsage("30d");
    expect(transport.fetch.mock.calls[0][0]).toBe("/api/provider-settings/usage?range=30d");
    expect(usage.total).toEqual({promptTokens:12,completionTokens:8,totalTokens:20});
    expect(usage.byCategory[0].totalTokens).toBe(20);
    expect(usage.timelineGranularity).toBe("hour");
  });
});
