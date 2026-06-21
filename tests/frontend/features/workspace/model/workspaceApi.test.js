import { afterEach, describe, expect, test, vi } from "vitest";

import {
  loadAgentSessionRecovery,
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
