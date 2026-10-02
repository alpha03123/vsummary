import { afterEach, describe, expect, test, vi } from "vitest";

import {
  generateVideoSummary,
  processAgentVideo,
  cancelDurableJob,
  loadAgentSessionRecovery,
  loadSeriesMindmap,
  generateVideoMindmap,
  generateVideoKnowledgeCards,
  generateVideoAiSummary,
  subscribeDurableJobProgress,
} from "@src/features/workspace/model/workspaceApi";
import { loadProviderUsage, relinkExternalVideo } from "@src/local-features/api/localWorkspaceApi";

afterEach(() => {
  vi.restoreAllMocks();
});
describe("loadAgentSessionRecovery", () => {
  test("restores assistant citations with recovered messages", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => ({
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
    })));

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
describe("loadSeriesMindmap", () => {
  test("returns null when the series mindmap has not been generated", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => ({
      ok: false,
      status: 404,
      json: async () => ({
        detail: "series mindmap not found for 'A1'",
      }),
    })));

    await expect(loadSeriesMindmap("A1")).resolves.toBeNull();
  });
});

describe("loadProviderUsage", () => {
  test("loads provider usage for the selected range", async () => {
    const fetchMock = vi.fn(async () => ({
      ok: true,
      json: async () => ({
        range: "7d",
        total: { prompt_tokens: 10, completion_tokens: 5, total_tokens: 15 },
        by_category: [
          { category: "generation", prompt_tokens: 7, completion_tokens: 3, total_tokens: 10 },
        ],
        by_provider: [
          {
            provider: "openai",
            base_url: "https://api.example.test/v1",
            model: "openai/gpt-test",
            prompt_tokens: 10,
            completion_tokens: 5,
            total_tokens: 15,
          },
        ],
        recent: [
          {
            created_at: "2026-07-03T10:00:00+00:00",
            category: "chat",
            provider: "openai",
            base_url: "https://api.example.test/v1",
            model: "openai/gpt-test",
            prompt_tokens: 3,
            completion_tokens: 2,
            total_tokens: 5,
          },
        ],
        timeline_granularity: "day",
        timeline: [
          {
            started_at: "2026-07-03T00:00:00+00:00",
            generation_tokens: 10,
            chat_tokens: 5,
            total_tokens: 15,
          },
        ],
      }),
    }));
    vi.stubGlobal("fetch", fetchMock);

    const usage = await loadProviderUsage("7d");

    expect(fetchMock).toHaveBeenCalledWith("/api/provider-settings/usage?range=7d", undefined);
    expect(usage.total.totalTokens).toBe(15);
    expect(usage.byCategory[0].totalTokens).toBe(10);
    expect(usage.byProvider[0].baseUrl).toBe("https://api.example.test/v1");
    expect(usage.recent[0].createdAt).toBe("2026-07-03T10:00:00+00:00");
    expect(usage.timelineGranularity).toBe("day");
    expect(usage.timeline[0]).toEqual({
      startedAt: "2026-07-03T00:00:00+00:00",
      generationTokens: 10,
      chatTokens: 5,
      totalTokens: 15,
    });
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
    vi.stubGlobal("fetch", fetchMock);

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
    vi.stubGlobal("fetch", vi.fn(async () => ({
      ok: true,
      json: async () => ({ jobs: [{ job_id: "job-other", status: "queued", resource: { type: "video", id: "other-video" } }] }),
    })));

    await expect(processAgentVideo("series-1", "video-1")).rejects.toThrow("当前视频的任务");
  });

  test("cancels the durable job by its ID", async () => {
    const fetchMock = vi.fn(async () => ({
      ok: true,
      json: async () => ({ job_id: "job/1", status: "cancelling" }),
    }));
    vi.stubGlobal("fetch", fetchMock);

    await expect(cancelDurableJob("job/1")).resolves.toMatchObject({ status: "cancelling" });
    expect(fetchMock).toHaveBeenCalledWith("/api/jobs/job%2F1/cancel", { method: "POST" });
  });
});

describe("generateVideoMindmap", () => {
  test("sends the selected maximum depth", async () => {
    const fetchMock = vi.fn(async () => ({
      ok: true,
      json: async () => ({ job_id: "job-mindmap", status: "queued" }),
    }));
    vi.stubGlobal("fetch", fetchMock);

    await expect(generateVideoMindmap("series-1", "video-1", 4)).resolves.toEqual({ jobId: "job-mindmap", status: "queued" });

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/videos/series-1/video-1/mindmap/generate",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ max_depth: 4 }),
      }),
    );
  });
});

describe("generateVideoKnowledgeCards", () => {
  test("submits a durable knowledge-card job", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => ({ ok: true, json: async () => ({ job_id: "job-cards", status: "queued" }) })));

    await expect(generateVideoKnowledgeCards("series-1", "video-1")).resolves.toEqual({ jobId: "job-cards", status: "queued" });
  });
});

describe("generateVideoAiSummary", () => {
  test("submits a durable AI-summary job with the selected template", async () => {
    const fetchMock = vi.fn(async () => ({ ok: true, json: async () => ({ job_id: "job-ai-summary", status: "queued" }) }));
    vi.stubGlobal("fetch", fetchMock);

    await expect(generateVideoAiSummary("series-1", "video-1", "tutorial")).resolves.toEqual({ jobId: "job-ai-summary", status: "queued" });
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/videos/series-1/video-1/ai-summary/generate",
      expect.objectContaining({ body: JSON.stringify({ template: "tutorial" }) }),
    );
  });
});

describe("generateVideoSummary", () => {
  test("keeps the durable job submission instead of parsing it as a summary", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => ({
      ok: true,
      json: async () => ({ job_id: "job-1", status: "queued" }),
    })));

    await expect(generateVideoSummary("series-1", "video-1")).resolves.toEqual({ jobId: "job-1", status: "queued" });
  });
});

describe("subscribeDurableJobProgress", () => {
  test("preserves progress and separate tasks through concurrent picture events", () => {
    const listeners = {};
    vi.stubGlobal("EventSource", class {
      addEventListener(type, listener) { listeners[type] = listener; }
      close() {}
    });
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

  test("preserves durable timing without deriving an ETA from milestone progress", () => {
    const listeners = {};
    vi.stubGlobal("EventSource", class {
      addEventListener(type, listener) {
        listeners[type] = listener;
      }

      close() {}
    });
    const listener = vi.fn();

    subscribeDurableJobProgress("job-1", listener);
    listeners.progress({
      data: JSON.stringify({
        status: "running",
        stage: "prepare",
        progress: 10,
        detail: "正在准备生成素材",
        started_at: Date.now() / 1000 - 20,
      }),
    });

    expect(listener).toHaveBeenCalledWith(expect.objectContaining({
      startedAt: expect.any(Number),
      elapsedSeconds: expect.any(Number),
      estimatedTotalSeconds: null,
      remainingSeconds: null,
    }));
  });
});

describe("relinkExternalVideo", () => {
  test("opens the backend relink flow for the selected video", async () => {
    const fetchMock = vi.fn(async () => ({ ok: true, json: async () => ({ relinked: true }) }));
    vi.stubGlobal("fetch", fetchMock);

    await expect(relinkExternalVideo("series 1", "video/1")).resolves.toEqual({ relinked: true });

    expect(fetchMock).toHaveBeenCalledWith("/api/videos/series%201/video%2F1/relink", { method: "POST" });
  });
});
