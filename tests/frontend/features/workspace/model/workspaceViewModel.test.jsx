import { describe, expect, it } from "vitest";

import { toWorkspaceLibrary } from "@src/features/workspace/model/workspaceViewModel";

describe("toWorkspaceLibrary", () => {
  it("maps linked bilibili fields to workspace video cards", () => {
    const library = toWorkspaceLibrary({
      workspace: { id: "ws", title: "Workspace" },
      series: [
        {
          id: "__playground__",
          title: "Playground",
          is_linked: false,
          source_url: "",
          videos: [
            {
              id: "BV1xx411c7mD",
              title: "第一讲",
              source_name: "BV1xx411c7mD.mp4",
              processed: false,
              status: "linked",
              is_linked: true,
              bilibili_bvid: "BV1xx411c7mD",
              bilibili_page: 1,
              source_url: "https://www.bilibili.com/video/BV1xx411c7mD",
            },
          ],
        },
      ],
    });

    expect(library.series[0].isLinked).toBe(false);
    expect(library.series[0].videos[0]).toMatchObject({
      id: "BV1xx411c7mD",
      isLinked: true,
      bilibiliBvid: "BV1xx411c7mD",
      bilibiliPage: 1,
      sourceUrl: "https://www.bilibili.com/video/BV1xx411c7mD",
    });
  });
});
