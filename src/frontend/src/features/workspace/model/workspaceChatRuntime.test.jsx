import { describe, expect, it } from "vitest";

import { normalizeAgentToolTraceStep } from "./workspaceChatRuntime";

describe("workspaceChatRuntime", () => {
  it("describes transcript rag hits as evidence snippets instead of full transcript", () => {
    const step = normalizeAgentToolTraceStep({
      tool_name: "get_video_transcript",
      payload: {
        title: "Video 1",
        result_count: 2,
      },
    });

    expect(step.label).toBe("读取转写证据片段");
    expect(step.target).toBe("Video 1");
  });
});
