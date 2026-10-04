import { afterEach, describe, expect, it } from "vitest";

import { getStudioPanelIds, removeStudioPanel, splitStudioPanel } from "@workspace/workspace/ui/workspaceLayout";

afterEach(() => {
  window.localStorage.clear();
});

describe("workspace layout", () => {
  it("supports a vertical split inside a horizontal layout", () => {
    const initial = {
      type: "split",
      direction: "row",
      children: ["preview::default", "overview::default"],
    };

    const layout = splitStudioPanel(initial, "preview::default", "mindmap::default", "column");

    expect(layout).toEqual({
      type: "split",
      direction: "row",
      children: [
        {
          type: "split",
          direction: "column",
          children: ["preview::default", "mindmap::default"],
        },
        "overview::default",
      ],
    });
    expect(getStudioPanelIds(layout)).toEqual([
      "preview::default",
      "mindmap::default",
      "overview::default",
    ]);
  });

  it("collapses redundant split containers when a panel closes", () => {
    const layout = {
      type: "split",
      direction: "row",
      children: [
        {
          type: "split",
          direction: "column",
          children: ["mindmap::default", "notes::default"],
        },
        "preview::default",
      ],
    };

    expect(removeStudioPanel(layout, "notes::default", "video", {})).toEqual({
      type: "split",
      direction: "row",
      children: ["mindmap::default", "preview::default"],
    });
  });
});
