import { act, fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { copyText } from "@src/features/workspace/ui/shared/clipboard";
import {
  buildCardMarkdown,
  WorkspaceKnowledgeCardsView,
} from "@src/features/workspace/ui/views/WorkspaceKnowledgeCardsView";

vi.mock("@src/features/workspace/ui/shared/clipboard", () => ({
  copyText: vi.fn(),
}));

const baseProps = {
  tools: { knowledgeCards: { available: true, generated: true } },
  knowledgeCards: null,
  knowledgeCardsGenerating: false,
  knowledgeCardsFeedback: null,
  knowledgeCardsLoading: false,
  onGenerateKnowledgeCards: vi.fn(),
  onClearKnowledgeCardsFeedback: vi.fn(),
};

const sampleCards = [
  {
    id: "c1",
    kind: "CONCEPT",
    title: "Transformer 注意力",
    summary: "核心是 self-attention",
    details: "Q/K/V 投影",
    tags: ["transformer", "nlp"],
  },
  {
    id: "c2",
    kind: "FACT",
    title: "另一个知识点",
    summary: "次要点",
    details: "细节",
    tags: [],
  },
];

describe("buildCardMarkdown", () => {
  it("包含标题、摘要、详情和 tags 行", () => {
    const md = buildCardMarkdown({
      title: "Transformer 注意力",
      summary: "核心是 self-attention",
      details: "Q/K/V 投影",
      tags: ["transformer", "nlp"],
    });
    expect(md).toBe(
      "# Transformer 注意力\n\n核心是 self-attention\n\nQ/K/V 投影\n\n**Tags:** transformer, nlp",
    );
  });

  it("tags 为空数组时省略 Tags 行", () => {
    const md = buildCardMarkdown({
      title: "T",
      summary: "S",
      details: "D",
      tags: [],
    });
    expect(md).toBe("# T\n\nS\n\nD");
    expect(md).not.toContain("**Tags:**");
  });

  it("tags 为非数组或非字符串时省略 Tags 行", () => {
    expect(
      buildCardMarkdown({ title: "T", summary: "S", details: "D", tags: null }),
    ).toBe("# T\n\nS\n\nD");
    expect(
      buildCardMarkdown({ title: "T", summary: "S", details: "D", tags: "raw-string" }),
    ).toBe("# T\n\nS\n\nD");
  });

  it("summary 为空字符串时该段省略, 不留空行", () => {
    const md = buildCardMarkdown({
      title: "T",
      summary: "",
      details: "D",
      tags: ["x"],
    });
    expect(md).toBe("# T\n\nD\n\n**Tags:** x");
  });

  it("details 为 null 时该段省略", () => {
    const md = buildCardMarkdown({
      title: "T",
      summary: "S",
      details: null,
      tags: [],
    });
    expect(md).toBe("# T\n\nS");
  });

  it("保留 Markdown 特殊字符 (#, *, `, >) 不转义", () => {
    const md = buildCardMarkdown({
      title: "标题含 # 不转义",
      summary: "代码 `let x = 1`",
      details: "> 引用\n* 列表项",
      tags: ["a*b"],
    });
    expect(md).toContain("# 标题含 # 不转义");
    expect(md).toContain("`let x = 1`");
    expect(md).toContain("> 引用");
    expect(md).toContain("**Tags:** a*b");
  });
});

describe("WorkspaceKnowledgeCardsView - 复制按钮", () => {
  beforeEach(() => {
    copyText.mockReset();
    copyText.mockResolvedValue(undefined);
  });

  function renderView() {
    return render(
      <WorkspaceKnowledgeCardsView
        {...baseProps}
        knowledgeCards={{ seriesId: "s1", videoId: "v1", title: "V", cards: sampleCards }}
      />,
    );
  }

  it("每张卡片渲染一个复制按钮", () => {
    renderView();
    expect(screen.getAllByRole("button", { name: "复制" })).toHaveLength(2);
  });

  it("按钮位于卡片右上角 (flex 容器 justify-between)", () => {
    renderView();
    const articles = screen.getAllByRole("article");
    articles.forEach((article) => {
      const header = article.firstElementChild;
      expect(header.className).toMatch(/justify-between/);
    });
  });

  it("点击按钮复制包含完整 Markdown 的文本", async () => {
    renderView();
    const buttons = screen.getAllByRole("button", { name: "复制" });
    await act(async () => {
      fireEvent.click(buttons[0]);
    });
    expect(copyText).toHaveBeenCalledWith(
      "# Transformer 注意力\n\n核心是 self-attention\n\nQ/K/V 投影\n\n**Tags:** transformer, nlp",
    );
  });

  it("两张卡片同时点击各自显示独立 '已复制' 状态", async () => {
    renderView();
    const buttons = screen.getAllByRole("button", { name: "复制" });
    await act(async () => {
      fireEvent.click(buttons[0]);
      fireEvent.click(buttons[1]);
    });
    expect(screen.getAllByRole("button", { name: "已复制" })).toHaveLength(2);
  });

  it("按钮默认可见 (不依赖父级 hover)", () => {
    renderView();
    const btn = screen.getAllByRole("button", { name: "复制" })[0];
    expect(btn).toBeVisible();
  });
});
