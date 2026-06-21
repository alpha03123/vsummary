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

  it("maps audio source type to workspace video cards", () => {
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
              id: "lesson-1",
              title: "lesson-1",
              source_name: "lesson-1.mp3",
              source_type: "audio",
              processed: false,
              status: "pending",
            },
          ],
        },
      ],
    });

    expect(library.series[0].videos[0].sourceType).toBe("audio");
  });

  it("maps core_problem to coreProblem when present", () => {
    const library = toWorkspaceLibrary({
      workspace: { id: "ws", title: "Workspace" },
      series: [
        {
          id: "s1",
          title: "S1",
          is_linked: false,
          source_url: "",
          videos: [
            {
              id: "v1",
              title: "V1",
              source_name: "v1.mp4",
              processed: true,
              status: "ready",
              core_problem: "如何用三步拆解复杂问题",
            },
          ],
        },
      ],
    });

    expect(library.series[0].videos[0]).toMatchObject({
      coreProblem: "如何用三步拆解复杂问题",
    });
  });

  it("returns empty coreProblem when core_problem field is missing", () => {
    const library = toWorkspaceLibrary({
      workspace: { id: "ws", title: "Workspace" },
      series: [
        {
          id: "s1",
          title: "S1",
          is_linked: false,
          source_url: "",
          videos: [
            {
              id: "v1",
              title: "V1",
              source_name: "v1.mp4",
              processed: false,
              status: "pending",
              // core_problem 故意不传
            },
          ],
        },
      ],
    });

    expect(library.series[0].videos[0].coreProblem).toBe("");
  });

  it("returns empty coreProblem when core_problem is not a string", () => {
    const library = toWorkspaceLibrary({
      workspace: { id: "ws", title: "Workspace" },
      series: [
        {
          id: "s1",
          title: "S1",
          is_linked: false,
          source_url: "",
          videos: [
            {
              id: "v1",
              title: "V1",
              source_name: "v1.mp4",
              processed: true,
              status: "ready",
              core_problem: 42,  // 故意传错类型
            },
          ],
        },
      ],
    });

    expect(library.series[0].videos[0].coreProblem).toBe("");
  });
});
