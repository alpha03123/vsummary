import { afterEach, describe, expect, test, vi } from "vitest";

import {
  loadAgentSessionRecovery,
  loadProviderUsage,
  loadSeriesMindmap,
} from "@src/features/workspace/model/workspaceApi";

afterEach(() => {
  vi.restoreAllMocks();
});

describe("loadAgentSessionRecovery", () => {
  test("restores assistant citations with recovered messages", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => ({
      ok: true,
      json: async () => ({
        session_id: "series|series-1|series-home",
        restored: true,
        memory_key: "series|series-1|series-home",
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

    const recovery = await loadAgentSessionRecovery("series|series-1|series-home", null);

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
