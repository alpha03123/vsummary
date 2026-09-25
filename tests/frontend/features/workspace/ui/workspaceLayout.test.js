import { afterEach, describe, expect, it } from "vitest";

import {
  WORKSPACE_LAYOUT_STORAGE_KEY,
  getStudioPanelIds,
  loadWorkspaceLayout,
  removeStudioPanel,
  splitStudioPanel,
} from "@src/features/workspace/ui/workspaceLayout";

afterEach(() => {
  window.localStorage.clear();
});

describe("workspace layout", () => {
  it("migrates the legacy horizontal panel array into a split tree", () => {
    window.localStorage.setItem(`${WORKSPACE_LAYOUT_STORAGE_KEY}:video`, JSON.stringify({
      sidebarWidth: 360,
      studioPanels: ["preview::default", "ai-summary::default"],
      panelTools: {},
      panelWidths: { "preview::default": 600 },
      chatDrawerWidth: 520,
    }));

    const layout = loadWorkspaceLayout("video");

    expect(layout.version).toBe(2);
    expect(layout.sidebarWidth).toBe(360);
    expect(layout.chatDrawerWidth).toBe(520);
    expect(layout.studioLayout).toEqual({
      type: "split",
      direction: "row",
      children: ["preview::default", "ai-summary::default"],
    });
  });

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
