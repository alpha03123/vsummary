import { describe, expect, it } from "vitest";

import { isVideoScopeMessage } from "@src/features/workspace/ui/WorkspaceVideoScopeEmbed";

describe("isVideoScopeMessage", () => {
  it("accepts context updates and seek results from the embedding extension", () => {
    const parentWindow = window.parent;

    expect(isVideoScopeMessage({
      source: parentWindow,
      origin: "chrome-extension://extension-id",
      data: { type: "vsummary:set-video-context" },
    })).toBe(true);
    expect(isVideoScopeMessage({
      source: parentWindow,
      origin: "chrome-extension://extension-id",
      data: { type: "vsummary:seek-result", ok: false },
    })).toBe(true);
  });

  it("rejects messages that do not originate from the embedding extension", () => {
    expect(isVideoScopeMessage({
      source: window,
      origin: "http://127.0.0.1:4173",
      data: { type: "vsummary:seek-result" },
    })).toBe(false);
  });
});
