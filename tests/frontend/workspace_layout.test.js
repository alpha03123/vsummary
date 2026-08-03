import { describe, expect, it } from "vitest";

import {
  WORKSPACE_LAYOUT_LIMITS,
  clampChatDrawerWidth,
  loadWorkspaceLayout,
} from "../../src/frontend/src/features/workspace/ui/workspaceLayout";

describe("chat drawer layout", () => {
  it("uses the default width when no persisted value exists", () => {
    window.localStorage.clear();

    expect(loadWorkspaceLayout().chatDrawerWidth).toBe(WORKSPACE_LAYOUT_LIMITS.chatDrawerDefaultWidth);
  });

  it("keeps the drawer within its desktop bounds", () => {
    expect(clampChatDrawerWidth({ proposedWidth: 100, viewportWidth: 1440 })).toBe(360);
    expect(clampChatDrawerWidth({ proposedWidth: 2000, viewportWidth: 1440 })).toBe(960);
  });

  it("limits the drawer on narrow screens", () => {
    expect(clampChatDrawerWidth({ proposedWidth: 800, viewportWidth: 480 })).toBe(408);
  });
});
