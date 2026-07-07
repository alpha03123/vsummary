import { afterEach, describe, expect, test, vi } from "vitest";

import {
  createBilibiliQrLoginSession,
  exportSeriesMarkdown,
  loadAgentSessionRecovery,
  loadWorkspaceSettings,
  pollBilibiliQrLogin,
  updateWorkspaceSettings,
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

describe("workspace settings API", () => {
  test("maps series markdown export path from settings response", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => ({
      ok: true,
      json: async () => ({
        theme: "light",
        show_takeaways: true,
        layout_mode: "video_center",
        transcript_enhancement_enabled: true,
        asr_model_quality: "large-v3-turbo",
        transcription_mode: "accurate",
        rag_embedding_device: "cpu",
        rag_max_hits: 5,
        rag_rerank_enabled: true,
        web_search_enabled: false,
        window_tokens: 1000000,
        answer_detail_level: "medium",
        reasoning_effort: "none",
        talk_custom_prompt: "",
        video_generation_concurrency: 1,
        chaoxing_request_delay_seconds: 0.2,
        chaoxing_init_course_delay_seconds: 0.3,
        series_markdown_export_path: "D:/exports",
      }),
    })));

    const settings = await loadWorkspaceSettings();

    expect(settings.seriesMarkdownExportPath).toBe("D:/exports");
  });

  test("sends series markdown export path when updating settings", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => ({
      ok: true,
      json: async () => ({
        theme: "light",
        show_takeaways: true,
        layout_mode: "video_center",
        transcript_enhancement_enabled: true,
        asr_model_quality: "large-v3-turbo",
        transcription_mode: "accurate",
        rag_embedding_device: "cpu",
        rag_max_hits: 5,
        rag_rerank_enabled: true,
        web_search_enabled: false,
        window_tokens: 1000000,
        answer_detail_level: "medium",
        reasoning_effort: "none",
        talk_custom_prompt: "",
        video_generation_concurrency: 1,
        chaoxing_request_delay_seconds: 0.2,
        chaoxing_init_course_delay_seconds: 0.3,
        series_markdown_export_path: "D:/exports",
      }),
    })));

    await updateWorkspaceSettings({
      theme: "light",
      showTakeaways: true,
      layoutMode: "video_center",
      transcriptEnhancementEnabled: true,
      asrModelQuality: "large-v3-turbo",
      transcriptionMode: "accurate",
      ragEmbeddingDevice: "cpu",
      ragMaxHits: 5,
      ragRerankEnabled: true,
      webSearchEnabled: false,
      windowTokens: 1000000,
      answerDetailLevel: "medium",
      reasoningEffort: "none",
      talkCustomPrompt: "",
      videoGenerationConcurrency: 1,
      chaoxingRequestDelaySeconds: 0.2,
      chaoxingInitCourseDelaySeconds: 0.3,
      seriesMarkdownExportPath: "D:/exports",
    });

    const body = JSON.parse(fetch.mock.calls[0][1].body);
    expect(body.series_markdown_export_path).toBe("D:/exports");
  });
});

describe("series markdown export API", () => {
  test("posts to the series markdown export endpoint", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => ({
      ok: true,
      json: async () => ({ output_dir: "D:/exports/Series", exported_count: 2 }),
    })));

    const result = await exportSeriesMarkdown("series-1");

    expect(fetch).toHaveBeenCalledWith("/api/series/series-1/exports/markdown", { method: "POST" });
    expect(result).toEqual({ outputDir: "D:/exports/Series", exportedCount: 2 });
  });
});

describe("Bilibili QR login API", () => {
  test("creates a QR login session", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => ({
      ok: true,
      json: async () => ({
        url: "https://passport.bilibili.com/qrcode",
        qrcode_key: "qr-key",
      }),
    })));

    const session = await createBilibiliQrLoginSession();

    expect(fetch).toHaveBeenCalledWith("/api/linked/bilibili/cookie/qr", { method: "POST" });
    expect(session).toEqual({ url: "https://passport.bilibili.com/qrcode", qrcodeKey: "qr-key" });
  });

  test("polls a QR login session", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => ({
      ok: true,
      json: async () => ({
        status: "confirmed",
        message: "扫码登录成功",
        configured: true,
      }),
    })));

    const result = await pollBilibiliQrLogin("qr-key");

    expect(fetch).toHaveBeenCalledWith("/api/linked/bilibili/cookie/qr/poll", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ qrcode_key: "qr-key" }),
    });
    expect(result).toEqual({ status: "confirmed", message: "扫码登录成功", configured: true });
  });
});
