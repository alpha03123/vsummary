import { describe, expect, it } from "vitest";

import { buildMarkdownOutline } from "@src/features/workspace/model/markdownOutline";

describe("buildMarkdownOutline", () => {
  it("uses h2 and h3 headings while excluding the document title", () => {
    const outline = buildMarkdownOutline("# 文档标题\n\n## 第一节\n\n### 细节\n\n#### 不进入目录", "summary");

    expect(outline.items).toEqual([
      { id: "summary-3", label: "第一节", depth: 2 },
      { id: "summary-5", label: "细节", depth: 3 },
    ]);
    expect(outline.headingIds).toEqual({ 3: "summary-3", 5: "summary-5" });
  });
});
