import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import {
  buildUsageTrendRows,
  WorkspaceUsagePage,
} from "@src/features/workspace/ui/WorkspaceUsagePage";

describe("WorkspaceUsagePage", () => {
  it("renders recent usage with a responsive chart", () => {
    render(
      <WorkspaceUsagePage
        usage={{
          total: { promptTokens: 30, completionTokens: 20, totalTokens: 50 },
          byCategory: [
            { category: "generation", promptTokens: 18, completionTokens: 12, totalTokens: 30 },
            { category: "chat", promptTokens: 12, completionTokens: 8, totalTokens: 20 },
          ],
          byProvider: [],
          recent: [
            {
              createdAt: "2026-07-03T10:00:00+00:00",
              category: "generation",
              provider: "openai",
              baseUrl: "https://api.example.test/v1",
              model: "gpt-test",
              promptTokens: 18,
              completionTokens: 12,
              totalTokens: 30,
            },
            {
              createdAt: "2026-07-03T10:05:00+00:00",
              category: "chat",
              provider: "openai",
              baseUrl: "https://api.example.test/v1",
              model: "gpt-test",
              promptTokens: 12,
              completionTokens: 8,
              totalTokens: 20,
            },
          ],
          timelineGranularity: "day",
          timeline: [
            {
              startedAt: "2026-07-03T00:00:00+00:00",
              generationTokens: 30,
              chatTokens: 20,
              totalTokens: 50,
            },
          ],
        }}
        range="7d"
        loading={false}
        error=""
        onChangeRange={vi.fn()}
        onClose={vi.fn()}
      />,
    );

    const trend = screen.getByText("Token 用量趋势");
    const chart = trend.closest(".rounded-3xl");

    expect(chart.querySelector("canvas")).toBeInTheDocument();
    expect(screen.getByText("Token 用量趋势")).toBeInTheDocument();
    expect(screen.getByText("按时间聚合真实 token 消耗，悬停查看明细。")).toBeInTheDocument();
    expect(screen.queryByText(/最近 2 次真实 token 调用/)).not.toBeInTheDocument();
    expect(screen.getAllByText("生成").length).toBeGreaterThan(0);
    expect(screen.getAllByText("对话").length).toBeGreaterThan(0);
  });

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
