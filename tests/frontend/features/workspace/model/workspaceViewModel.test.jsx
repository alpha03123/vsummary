import { describe, expect, it } from "vitest";

import { toWorkspaceSummary } from "@workspace/workspace/model/workspaceViewModel";

describe("toWorkspaceSummary", () => {
  it("preserves a chapter screenshot timestamp for player navigation", () => {
    const summary = toWorkspaceSummary({
      title: "概况",
      chapters: [{
        id: "chapter-1",
        title: "第一章",
        summary: "章节摘要",
        key_points: [],
        start_seconds: 10,
        end_seconds: 20,
        image_timestamp_seconds: 14.5,
        image_url: "/api/videos/series-1/video-1/screenshots/chapter-01.jpg",
      }],
    });

    expect(summary.chapters[0].image_timestamp_seconds).toBe(14.5);
  });
});
