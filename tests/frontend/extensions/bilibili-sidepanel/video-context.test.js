import { describe, expect, it } from "vitest";

import { parseVideoContext } from "../../../../extensions/bilibili-sidepanel/video-context";

describe("parseVideoContext", () => {
  it.each([
    ["https://www.bilibili.com/video/BV1xx411c7mD", "BV1xx411c7mD:1"],
    ["https://bilibili.com/video/BV1xx411c7mD?p=2", "BV1xx411c7mD:2"],
    ["https://www.bilibili.com/video/BV1xx411c7mD?p=0", "BV1xx411c7mD:1"],
    ["https://www.bilibili.com/video/BV1xx411c7mD?p=abc", "BV1xx411c7mD:1"],
  ])("normalizes %s", (url, key) => {
    expect(parseVideoContext({ id: 8, url })).toMatchObject({ tabId: 8, key });
  });

  it("rejects unsupported Bilibili routes", () => {
    expect(parseVideoContext({ id: 8, url: "https://www.bilibili.com/bangumi/play/ep123" })).toBeNull();
    expect(parseVideoContext({ id: 8, url: "https://www.bilibili.com/video/av123" })).toBeNull();
  });
});
