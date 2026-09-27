import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { WorkspaceAiSummaryView } from "@src/features/workspace/ui/views/WorkspaceAiSummaryView";

describe("WorkspaceAiSummaryView", () => {
  it("builds a chapter outline from Markdown headings and renders matching anchors", () => {
    render(
      <WorkspaceAiSummaryView
        aiSummary={{
          title: "测试概括",
          content: "# 文档标题\n\n## 核心结论\n\n内容。\n\n### 实施细节\n\n更多内容。",
          citations: [],
        }}
        loading={false}
        generating={false}
        onGenerate={vi.fn()}
        onUpdate={vi.fn()}
      />,
    );

    expect(screen.getByRole("navigation", { name: "概括目录" })).toBeInTheDocument();
    expect(document.getElementById("ai-summary-outline-3")).toHaveTextContent("核心结论");
    expect(document.getElementById("ai-summary-outline-7")).toHaveTextContent("实施细节");
  });
});
