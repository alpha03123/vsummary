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
    keywords: ["attention", "qkv"],
  },
  {
    id: "c2",
    kind: "FACT",
    title: "另一个知识点",
    summary: "次要点",
    details: "细节",
    tags: [],
    keywords: [],
  },
];

describe("buildCardMarkdown", () => {
  it("包含标题、元信息、摘要和详情", () => {
    const md = buildCardMarkdown({
      kind: "concept",
      title: "抽象：隐藏不重要的细节以突出关键特征",
      summary: "抽象是通过有目的地隐藏某些细节，使系统的主要方面表达得更加清晰。",
      details: "百度百科定义其为对过程或制品某些细节的有目的隐藏。",
      tags: ["抽象", "层次结构", "系统复杂性"],
      keywords: ["abstraction", "encapsulation", "interface", "complexity"],
    });
    expect(md).toBe(
      "## 抽象：隐藏不重要的细节以突出关键特征\n\n" +
        "- 类型：concept\n" +
        "- 标签：抽象、层次结构、系统复杂性\n" +
        "- 关键词：abstraction、encapsulation、interface、complexity\n\n" +
        "### 摘要\n" +
        "抽象是通过有目的地隐藏某些细节，使系统的主要方面表达得更加清晰。\n\n" +
        "### 详情\n" +
        "百度百科定义其为对过程或制品某些细节的有目的隐藏。",
    );
  });

  it("tags 为空数组时省略 标签 行", () => {
    const md = buildCardMarkdown({
      kind: "concept",
      title: "T",
      summary: "S",
      details: "D",
      tags: [],
    });
    expect(md).toContain("## T");
    expect(md).not.toContain("- 标签：");
  });

  it("keywords 为空数组时省略 关键词 行", () => {
    const md = buildCardMarkdown({
      kind: "concept",
      title: "T",
      summary: "S",
      details: "D",
      keywords: [],
    });
    expect(md).toContain("## T");
    expect(md).not.toContain("- 关键词：");
  });

  it("tags 为非数组或非字符串时省略 标签 行", () => {
    expect(
      buildCardMarkdown({ title: "T", summary: "S", details: "D", tags: null }),
    ).not.toContain("- 标签：");
    expect(
      buildCardMarkdown({ title: "T", summary: "S", details: "D", tags: "raw-string" }),
    ).not.toContain("- 标签：");
  });

  it("keywords 为非数组或非字符串时省略 关键词 行", () => {
    expect(
      buildCardMarkdown({ title: "T", summary: "S", details: "D", keywords: null }),
    ).not.toContain("- 关键词：");
    expect(
      buildCardMarkdown({ title: "T", summary: "S", details: "D", keywords: "raw-string" }),
    ).not.toContain("- 关键词：");
  });

  it("tags 中过滤掉非字符串元素", () => {
    const md = buildCardMarkdown({
      title: "T",
      summary: "S",
      details: "D",
      tags: ["good", 123, null, "ok"],
    });
    expect(md).toContain("- 标签：good、ok");
    expect(md).not.toContain("123");
  });

  it("summary 为空字符串时省略 摘要 section, 不留空 heading", () => {
    const md = buildCardMarkdown({
      title: "T",
      summary: "",
      details: "D",
      tags: ["x"],
    });
    expect(md).not.toContain("### 摘要");
    expect(md).toContain("### 详情");
  });

  it("details 为 null 时省略 详情 section", () => {
    const md = buildCardMarkdown({
      title: "T",
      summary: "S",
      details: null,
    });
    expect(md).not.toContain("### 详情");
    expect(md).toContain("### 摘要");
  });

  it("kind 缺失时省略 类型 行", () => {
    const md = buildCardMarkdown({
      title: "T",
      summary: "S",
      details: "D",
    });
    expect(md).not.toContain("- 类型：");
  });

  it("标题/元信息/内容全缺时只剩标题行", () => {
    const md = buildCardMarkdown({});
    expect(md).toBe("## ");
  });

  it("保留 Markdown 特殊字符 (#, *, `, >) 不转义", () => {
    const md = buildCardMarkdown({
      kind: "concept",
      title: "标题含 # 不转义",
      summary: "代码 `let x = 1`",
      details: "> 引用\n* 列表项",
      tags: ["a*b"],
    });
    expect(md).toContain("## 标题含 # 不转义");
    expect(md).toContain("`let x = 1`");
    expect(md).toContain("> 引用");
    expect(md).toContain("- 标签：a*b");
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
      "## Transformer 注意力\n\n" +
        "- 类型：CONCEPT\n" +
        "- 标签：transformer、nlp\n" +
        "- 关键词：attention、qkv\n\n" +
        "### 摘要\n" +
        "核心是 self-attention\n\n" +
        "### 详情\n" +
        "Q/K/V 投影",
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
