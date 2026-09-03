import { describe, expect, it } from "vitest";

import { buildUsageTrendRows } from "@src/features/workspace/ui/WorkspaceUsagePage";

describe("WorkspaceUsagePage", () => {
  it("uses weekly buckets for 30 day trend rows", () => {
    const timeline = Array.from({ length: 5 }, (_, index) => ({
      startedAt: `2026-06-${String(index * 7 + 1).padStart(2, "0")}T00:00:00+00:00`,
      generationTokens: index + 1,
      chatTokens: index + 2,
      totalTokens: index * 2 + 3,
    }));

    const rows = buildUsageTrendRows(timeline, "week", "30d");

    expect(rows).toHaveLength(5);
    expect(rows[0].generationTokens).toBe(1);
    expect(rows[0].chatTokens).toBe(2);
    expect(rows.every((row) => row.showAxisTick)).toBe(true);
  });
});
