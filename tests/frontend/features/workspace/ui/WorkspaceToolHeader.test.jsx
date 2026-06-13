import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { WorkspaceToolHeader } from "@src/features/workspace/ui/shared/WorkspaceToolHeader";

describe("WorkspaceToolHeader", () => {
  it("renders an enabled markdown export link when export metadata is available", async () => {
    render(
      <WorkspaceToolHeader
        meta={{ label: "AI概况", description: "章节与关键结论" }}
        onBack={vi.fn()}
        exportActions={[{ href: "/api/videos/s/v/exports/summary.md", enabled: true, label: "概况导出" }]}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "导出" }));
    const link = screen.getByRole("link", { name: "概况导出" });

    expect(link).toHaveAttribute("href", "/api/videos/s/v/exports/summary.md");
    expect(link).toHaveAttribute("download");
  });

  it("renders a disabled markdown export control when export is unavailable", () => {
    render(
      <WorkspaceToolHeader
        meta={{ label: "知识卡片", description: "独立知识资产" }}
        onBack={vi.fn()}
        exportActions={[{ href: "/api/videos/s/v/exports/knowledge-cards.md", enabled: false, label: "知识卡片导出" }]}
      />,
    );

    expect(screen.queryByRole("link", { name: "知识卡片导出" })).toBeNull();
    expect(screen.getByRole("button", { name: "导出" })).toBeDisabled();
  });

  it("renders multiple export links for a tool page", async () => {
    render(
      <WorkspaceToolHeader
        meta={{ label: "AI概况", description: "章节与关键结论" }}
        onBack={vi.fn()}
        exportActions={[
          { href: "/api/videos/s/v/exports/summary.md", enabled: true, label: "概况导出" },
          { href: "/api/videos/s/v/exports/transcript.md", enabled: true, label: "转写导出" },
        ]}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "导出" }));
    expect(screen.getByRole("link", { name: "概况导出" })).toHaveAttribute("href", "/api/videos/s/v/exports/summary.md");
    expect(screen.getByRole("link", { name: "转写导出" })).toHaveAttribute("href", "/api/videos/s/v/exports/transcript.md");
  });
});
