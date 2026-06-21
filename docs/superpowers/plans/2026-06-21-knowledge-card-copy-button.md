# 知识卡片复制按钮 — 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 `WorkspaceKnowledgeCardsView` 渲染的每张知识卡片右上角加一个"复制"按钮，点击后将该卡片的标题/摘要/详情/标签按 Markdown 格式写入剪贴板。同步把 `WorkspaceChatPanel` 中已有的私有 `copyText` 抽取到 `ui/shared/` 复用。

**Architecture:** 在 `ui/shared/` 下新建 `clipboard.js`（纯工具函数）与 `CopyToClipboardButton.jsx`（通用按钮组件，含 copied 状态 + 1.6s 自动复原 + try/catch 兜底）。`WorkspaceKnowledgeCardsView` 顶部新增纯函数 `buildCardMarkdown`（导出以便可直接单测），并在卡片头部挂载按钮。`WorkspaceChatPanel` 删除本地 `copyText` / `copiedMessageId` / `handleCopyMessage`，通过 `className` prop 覆盖默认视觉以保留原 chip 样式。

**Tech Stack:** React 19 + JSX + Tailwind 3；Vitest + @testing-library/react + jsdom（`src/frontend/vite.config.js:63-68` 已配）。测试约定参考 `tests/frontend/features/workspace/ui/ChatDrawer.test.jsx` 与 `WorkspaceMarkdownMessage.test.jsx`。

**测试范围:** 不引入 E2E。每个任务只跑该任务点名的目标测试文件，全量 vitest 在 Task 5 末尾跑一次回归。

**前置阅读（实施者必读）:**
- Spec: `docs/superpowers/specs/2026-06-21-knowledge-card-copy-button.md`
- 卡片视图: `src/frontend/src/features/workspace/ui/views/WorkspaceKnowledgeCardsView.jsx:86-117`
- ChatPanel 复制逻辑: `src/frontend/src/features/workspace/ui/WorkspaceChatPanel.jsx:58, 97-106, 234, 262-271, 344-358`
- 已有 vitest 用例参考: `tests/frontend/features/workspace/ui/shared/WorkspaceMarkdownMessage.test.jsx`

---

## File Structure

| 文件 | 角色 | 状态 |
|---|---|---|
| `src/frontend/src/features/workspace/ui/shared/clipboard.js` | `copyText` 工具函数 | **新建** |
| `src/frontend/src/features/workspace/ui/shared/CopyToClipboardButton.jsx` | 通用复制按钮组件 | **新建** |
| `src/frontend/src/features/workspace/ui/views/WorkspaceKnowledgeCardsView.jsx` | 加 `buildCardMarkdown` + 在卡片头挂按钮 | 编辑 |
| `src/frontend/src/features/workspace/ui/WorkspaceChatPanel.jsx` | 改用新组件，删除本地 copyText / state / handler | 编辑 |
| `tests/frontend/features/workspace/ui/shared/clipboard.test.js` | copyText 单元测试 | **新建** |
| `tests/frontend/features/workspace/ui/shared/CopyToClipboardButton.test.jsx` | 按钮组件单元测试 | **新建** |
| `tests/frontend/features/workspace/ui/views/WorkspaceKnowledgeCardsView.test.jsx` | buildCardMarkdown + 视图渲染/点击测试 | **新建** |

**TDD 注:** `buildCardMarkdown` 放在视图文件顶部并 `export`，以便直接单测；该函数纯 JS、无 React 依赖，导出对运行时无副作用（只是多一个 named export）。

---

## Task 1: 抽取 `copyText` 到 `ui/shared/clipboard.js`

**Files:**
- Create: `src/frontend/src/features/workspace/ui/shared/clipboard.js`
- Create: `tests/frontend/features/workspace/ui/shared/clipboard.test.js`

- [ ] **Step 1: 写失败的 copyText 测试**

创建 `tests/frontend/features/workspace/ui/shared/clipboard.test.js`:

```js
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { copyText } from "@src/features/workspace/ui/shared/clipboard";

describe("copyText", () => {
  const originalClipboard = navigator.clipboard;
  const originalExecCommand = document.execCommand;

  afterEach(() => {
    Object.defineProperty(navigator, "clipboard", {
      value: originalClipboard,
      configurable: true,
      writable: true,
    });
    document.execCommand = originalExecCommand;
    vi.restoreAllMocks();
  });

  it("writes to navigator.clipboard.writeText when available", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", {
      value: { writeText },
      configurable: true,
      writable: true,
    });
    const execSpy = vi.fn();
    document.execCommand = execSpy;

    await copyText("hello");

    expect(writeText).toHaveBeenCalledWith("hello");
    expect(execSpy).not.toHaveBeenCalled();
  });

  it("falls back to execCommand when clipboard API is unavailable", async () => {
    Object.defineProperty(navigator, "clipboard", {
      value: undefined,
      configurable: true,
      writable: true,
    });
    const execSpy = vi.fn();
    document.execCommand = execSpy;

    await copyText("fallback-text");

    expect(execSpy).toHaveBeenCalledWith("copy");
    expect(document.body.querySelector("textarea")).toBeNull();
  });
});
```

- [ ] **Step 2: 跑测试, 确认失败**

Run: `cd src/frontend && npx vitest run tests/frontend/features/workspace/ui/shared/clipboard.test.js`
Expected: FAIL — `Failed to resolve import "@src/features/workspace/ui/shared/clipboard"` 或 `copyText is not a function`

- [ ] **Step 3: 实现 clipboard.js**

创建 `src/frontend/src/features/workspace/ui/shared/clipboard.js`:

```js
export async function copyText(text) {
  if (navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(text);
    return;
  }
  const textarea = document.createElement("textarea");
  textarea.value = text;
  textarea.setAttribute("readonly", "");
  textarea.style.position = "fixed";
  textarea.style.left = "-9999px";
  document.body.appendChild(textarea);
  textarea.select();
  document.execCommand("copy");
  document.body.removeChild(textarea);
}
```

- [ ] **Step 4: 跑测试, 确认通过**

Run: `cd src/frontend && npx vitest run tests/frontend/features/workspace/ui/shared/clipboard.test.js`
Expected: 2 passed

- [ ] **Step 5: 提交**

```bash
git add src/frontend/src/features/workspace/ui/shared/clipboard.js tests/frontend/features/workspace/ui/shared/clipboard.test.js
git commit -m "feat(frontend): extract copyText utility to ui/shared/clipboard"
```

---

## Task 2: 创建 `CopyToClipboardButton` 组件

**Files:**
- Create: `src/frontend/src/features/workspace/ui/shared/CopyToClipboardButton.jsx`
- Create: `tests/frontend/features/workspace/ui/shared/CopyToClipboardButton.test.jsx`

本任务一次性写完所有 9 个测试（覆盖 R1/R2/R5/R6/B1/B2/B3/B4 + 1600ms 复原），跑确认全失败，实现组件，再跑确认全通过，最后一次提交。B6 键盘测试不写（详见 Self-Review）。

- [ ] **Step 1: 写所有失败的组件测试**

创建 `tests/frontend/features/workspace/ui/shared/CopyToClipboardButton.test.jsx`:

```js
import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { copyText } from "@src/features/workspace/ui/shared/clipboard";
import { CopyToClipboardButton } from "@src/features/workspace/ui/shared/CopyToClipboardButton";

vi.mock("@src/features/workspace/ui/shared/clipboard", () => ({
  copyText: vi.fn(),
}));

describe("CopyToClipboardButton", () => {
  beforeEach(() => {
    copyText.mockReset();
    copyText.mockResolvedValue(undefined);
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("renders Copy 图标 + 默认文案'复制'", () => {
    render(<CopyToClipboardButton text="abc" />);
    const btn = screen.getByRole("button", { name: "复制" });
    expect(btn).toBeInTheDocument();
    expect(btn.querySelector("svg")).toBeInTheDocument();
  });

  it("点击后切换为 Check 图标 + '已复制'文案 + emerald 背景", async () => {
    render(<CopyToClipboardButton text="abc" />);
    const btn = screen.getByRole("button", { name: "复制" });
    await act(async () => {
      fireEvent.click(btn);
    });
    const copiedBtn = screen.getByRole("button", { name: "已复制" });
    expect(copiedBtn.className).toMatch(/bg-emerald-100/);
  });

  it("aria-label 反映当前状态", async () => {
    render(<CopyToClipboardButton text="abc" />);
    expect(screen.getByRole("button").getAttribute("aria-label")).toBe("复制");
    await act(async () => {
      fireEvent.click(screen.getByRole("button"));
    });
    expect(screen.getByRole("button").getAttribute("aria-label")).toBe("已复制");
  });

  it("初始态 hover 切换背景色", () => {
    render(<CopyToClipboardButton text="abc" />);
    const btn = screen.getByRole("button", { name: "复制" });
    expect(btn.className).toMatch(/bg-stone-100/);
    expect(btn.className).toMatch(/hover:bg-stone-200/);
  });

  it("1600ms 后复原初始态", async () => {
    vi.useFakeTimers();
    render(<CopyToClipboardButton text="abc" />);
    await act(async () => {
      fireEvent.click(screen.getByRole("button"));
    });
    expect(screen.getByRole("button", { name: "已复制" })).toBeInTheDocument();
    await act(async () => {
      vi.advanceTimersByTime(1600);
    });
    expect(screen.getByRole("button", { name: "复制" })).toBeInTheDocument();
  });

  it("连点同一按钮, 复原时间以最后一次为准", async () => {
    vi.useFakeTimers();
    render(<CopyToClipboardButton text="abc" />);
    await act(async () => {
      fireEvent.click(screen.getByRole("button"));
    });
    await act(async () => {
      vi.advanceTimersByTime(1000);
    });
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "已复制" }));
    });
    await act(async () => {
      vi.advanceTimersByTime(1000);
    });
    expect(screen.getByRole("button", { name: "已复制" })).toBeInTheDocument();
    await act(async () => {
      vi.advanceTimersByTime(600);
    });
    expect(screen.getByRole("button", { name: "复制" })).toBeInTheDocument();
  });

  it("卸载时清除 timeout, 无 React 警告", async () => {
    vi.useFakeTimers();
    const errorSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    const { unmount } = render(<CopyToClipboardButton text="abc" />);
    await act(async () => {
      fireEvent.click(screen.getByRole("button"));
    });
    unmount();
    await act(async () => {
      vi.advanceTimersByTime(2000);
    });
    // React 在组件卸载后调用 setState 会输出 "An update to X inside a test was not wrapped in act"
    // 或 "Can't perform a React state update on an unmounted component" — 任一出现即视为未清理
    const allCalls = errorSpy.mock.calls.flat().join("\n");
    expect(allCalls).not.toMatch(/unmounted|wrapped in act/i);
    errorSpy.mockRestore();
  });

  it("copyText reject 时保持初始态, 不进入 copied", async () => {
    copyText.mockRejectedValueOnce(new Error("permission denied"));
    render(<CopyToClipboardButton text="abc" />);
    await act(async () => {
      fireEvent.click(screen.getByRole("button"));
    });
    expect(screen.getByRole("button", { name: "复制" })).toBeInTheDocument();
  });

  it("不同实例的 copied 状态相互独立", async () => {
    vi.useFakeTimers();
    render(
      <div>
        <CopyToClipboardButton text="A" />
        <CopyToClipboardButton text="B" />
      </div>,
    );
    const buttons = screen.getAllByRole("button", { name: "复制" });
    await act(async () => {
      fireEvent.click(buttons[0]);
    });
    await act(async () => {
      fireEvent.click(buttons[1]);
    });
    expect(screen.getAllByRole("button", { name: "已复制" })).toHaveLength(2);
  });
});
```

**注:** 不写键盘 Enter/Space 触发测试 (AC B6)。B6 对应"`<button type="button">` 默认行为，无额外处理"，是浏览器原生行为，不属于本组件代码。`@testing-library/user-event` 未安装 (package.json devDependencies 确认)，`fireEvent.keyDown` 在 jsdom 中无法触发原生 click，因此放弃测试。

- [ ] **Step 2: 跑测试, 确认全部失败**

Run: `cd src/frontend && npx vitest run tests/frontend/features/workspace/ui/shared/CopyToClipboardButton.test.jsx`
Expected: 全部 FAIL (9 个) — `Failed to resolve import "@src/features/workspace/ui/shared/CopyToClipboardButton"`

- [ ] **Step 3: 实现 CopyToClipboardButton.jsx**

创建 `src/frontend/src/features/workspace/ui/shared/CopyToClipboardButton.jsx`:

```jsx
import { useEffect, useRef, useState } from "react";
import { Check, Copy } from "lucide-react";

import { copyText } from "./clipboard";

export function CopyToClipboardButton({
  text,
  label = "复制",
  copiedLabel = "已复制",
  iconSize = 14,
  className = "",
}) {
  const [copied, setCopied] = useState(false);
  const timeoutRef = useRef(null);

  useEffect(
    () => () => {
      if (timeoutRef.current) window.clearTimeout(timeoutRef.current);
    },
    [],
  );

  async function handleClick() {
    try {
      await copyText(text);
      setCopied(true);
      if (timeoutRef.current) window.clearTimeout(timeoutRef.current);
      timeoutRef.current = window.setTimeout(() => setCopied(false), 1600);
    } catch {
      // copyText rejected: leave button in initial state, no toast/log
    }
  }

  const Icon = copied ? Check : Copy;
  const displayLabel = copied ? copiedLabel : label;

  return (
    <button
      type="button"
      onClick={handleClick}
      aria-live="polite"
      aria-label={displayLabel}
      title={displayLabel}
      className={`inline-flex items-center gap-1.5 rounded-xl px-2.5 py-1.5 text-xs font-semibold transition ${
        copied
          ? "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300"
          : "bg-stone-100 text-stone-600 hover:bg-stone-200 dark:bg-stone-800 dark:text-stone-300 dark:hover:bg-stone-700"
      } ${className}`}
    >
      <Icon size={iconSize} strokeWidth={2.2} aria-hidden="true" />
      <span>{displayLabel}</span>
    </button>
  );
}
```

- [ ] **Step 4: 跑测试, 确认全部通过**

Run: `cd src/frontend && npx vitest run tests/frontend/features/workspace/ui/shared/CopyToClipboardButton.test.jsx`
Expected: 9 passed

> 若失败: 优先检查 timer 测试 (`vi.useFakeTimers` 必须在 click 之前；`act` 包裹必须齐全); a11y 测试断言 `aria-label` 而非 `title`; 卸载测试需 `unmount()` 后再 advance timers.

- [ ] **Step 5: 提交**

```bash
git add src/frontend/src/features/workspace/ui/shared/CopyToClipboardButton.jsx tests/frontend/features/workspace/ui/shared/CopyToClipboardButton.test.jsx
git commit -m "feat(frontend): add CopyToClipboardButton shared component"
```

---

## Task 3: 在 `WorkspaceKnowledgeCardsView` 加 `buildCardMarkdown` 并集成按钮

**Files:**
- Modify: `src/frontend/src/features/workspace/ui/views/WorkspaceKnowledgeCardsView.jsx`
- Create: `tests/frontend/features/workspace/ui/views/WorkspaceKnowledgeCardsView.test.jsx`

- [ ] **Step 1: 写所有失败的测试**

创建 `tests/frontend/features/workspace/ui/views/WorkspaceKnowledgeCardsView.test.jsx`:

```jsx
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
```

- [ ] **Step 2: 跑测试, 确认全部失败**

Run: `cd src/frontend && npx vitest run tests/frontend/features/workspace/ui/views/WorkspaceKnowledgeCardsView.test.jsx`
Expected: 全部 FAIL (11 个) — `Failed to resolve import` 或 `buildCardMarkdown is not a function`

- [ ] **Step 2: 跑测试, 确认全部失败**

Run: `cd src/frontend && npx vitest run tests/frontend/features/workspace/ui/views/WorkspaceKnowledgeCardsView.test.jsx`
Expected: 全部 FAIL — `Failed to resolve import` 或 `buildCardMarkdown is not a function`

- [ ] **Step 3: 修改 WorkspaceKnowledgeCardsView.jsx**

替换 `src/frontend/src/features/workspace/ui/views/WorkspaceKnowledgeCardsView.jsx` 全文为:

```jsx
import { BrainCircuit } from "lucide-react";

import { CopyToClipboardButton } from "../shared/CopyToClipboardButton";
import { WorkspaceFeedbackBanner } from "../shared/WorkspaceFeedbackBanner";
import { WorkspaceStateBlock } from "../shared/WorkspaceStateBlock";

export function buildCardMarkdown(card) {
  const tagsLine =
    Array.isArray(card?.tags) && card.tags.length
      ? `**Tags:** ${card.tags.filter((t) => typeof t === "string").join(", ")}`
      : "";
  return [
    `# ${card?.title ?? ""}`,
    "",
    card?.summary ?? "",
    "",
    card?.details ?? "",
    tagsLine,
  ]
    .filter((line) => line !== "" && line != null)
    .join("\n");
}

export function WorkspaceKnowledgeCardsView({
  tools,
  knowledgeCards,
  knowledgeCardsGenerating,
  knowledgeCardsFeedback,
  knowledgeCardsLoading,
  onGenerateKnowledgeCards,
  onClearKnowledgeCardsFeedback,
}) {
  const hasKnowledgeCards = Boolean(knowledgeCards?.cards?.length);

  if (knowledgeCardsGenerating) {
    return (
      <WorkspaceStateBlock
        eyebrow="Knowledge Cards"
        title="正在生成知识卡片"
        description="正在提炼..."
        loading
      >
        <div className="mt-6 h-2 overflow-hidden rounded-full bg-stone-200/80 dark:bg-stone-800">
          <div className="h-full w-1/2 animate-pulse rounded-full bg-accent" />
        </div>
        <p className="mt-3 text-xs text-stone-500 dark:text-stone-400">生成完成后会自动展示结果。</p>
      </WorkspaceStateBlock>
    );
  }

  if (!tools?.knowledgeCards.available) {
    return (
      <WorkspaceStateBlock
        eyebrow="Knowledge Cards"
        title="需要先生成 AI 概况"
        description="知识卡片依赖 AI 概况的结构化理解，没有概况就没有抽取基础。"
      />
    );
  }

  if (!tools.knowledgeCards.generated) {
    return (
      <WorkspaceStateBlock
        eyebrow="Knowledge Cards"
        title="知识卡片尚未生成"
        description="这里展示的是独立的知识资产，不是章节摘要换皮。生成后会落盘到 `knowledge_cards.json`。"
      >
        <button
          type="button"
          onClick={onGenerateKnowledgeCards}
          className="inline-flex items-center gap-2 rounded-2xl bg-stone-900 px-5 py-3 text-sm font-semibold text-white transition hover:bg-accent dark:bg-white dark:text-black"
        >
          <BrainCircuit size={16} strokeWidth={2.2} />
          生成知识卡片
        </button>
      </WorkspaceStateBlock>
    );
  }

  if (knowledgeCardsLoading) {
    return (
      <WorkspaceStateBlock
        eyebrow="Knowledge Cards"
        title="载入知识卡片"
        description="正在读取已生成的知识卡片。"
        loading
      />
    );
  }

  if (!hasKnowledgeCards) {
    return (
      <div className="flex flex-col gap-4">
        <WorkspaceFeedbackBanner feedback={knowledgeCardsFeedback} onDismiss={onClearKnowledgeCardsFeedback} />
        <WorkspaceStateBlock
          eyebrow="Knowledge Cards"
          title="还没有可展示的卡片"
          description="当前视频还没有抽取出足够稳定的知识原子，可稍后重新生成。"
        />
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-4">
      <WorkspaceFeedbackBanner feedback={knowledgeCardsFeedback} onDismiss={onClearKnowledgeCardsFeedback} />
      <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
        {knowledgeCards.cards.map((card) => (
          <article
            key={card.id}
            className="workspace-elevated-panel rounded-[2rem] border p-6 transition-all hover:-translate-y-0.5 hover:border-stone-300 dark:hover:border-white/16"
          >
            <div className="flex items-start justify-between gap-3">
              <div>
                <p className="text-[10px] font-bold uppercase tracking-widest text-stone-500 dark:text-stone-400">{card.kind}</p>
                <h3 className="mt-2 text-lg font-bold text-stone-900 dark:text-stone-100">{card.title}</h3>
              </div>
              <CopyToClipboardButton text={buildCardMarkdown(card)} className="shrink-0" />
            </div>
            <p className="mt-4 text-sm leading-relaxed text-stone-600 dark:text-stone-400">{card.summary}</p>
            <p className="mt-3 text-sm leading-relaxed text-stone-700 dark:text-stone-300">{card.details}</p>
            {card.tags.length ? (
              <div className="mt-4 flex flex-wrap gap-2">
                {card.tags.map((tag) => (
                  <span
                    key={tag}
                    className="rounded-full border border-stone-200/70 bg-stone-100/80 px-3 py-1 text-[11px] font-semibold text-stone-600 dark:border-stone-700 dark:bg-stone-800 dark:text-stone-300"
                  >
                    {tag}
                  </span>
                ))}
              </div>
            ) : null}
          </article>
        ))}
      </div>
    </div>
  );
}
```

关键变化:
1. 顶部新增 `import { CopyToClipboardButton } from "../shared/CopyToClipboardButton";`
2. 文件顶部新增 `export function buildCardMarkdown(card) {...}` 纯函数
3. 卡片头部 `<div>` (line 95-98 原) 改为 `flex items-start justify-between gap-3` 容器, 右侧挂载 `<CopyToClipboardButton>`

- [ ] **Step 4: 跑测试, 确认全部通过**

Run: `cd src/frontend && npx vitest run tests/frontend/features/workspace/ui/views/WorkspaceKnowledgeCardsView.test.jsx`
Expected: 11 passed (6 buildCardMarkdown + 5 视图)

> 若失败: 
> - `screen.getByAllRole` 是占位写法, 应删; 用 `getAllByRole("button", { name: "已复制" })` 即可
> - `screen.getAllByRole("button", { name: "复制" })` 返回当前态的按钮列表, 不会包含已复制的卡片
> - 测试 props 中的 `cards` 字段名必须匹配 viewModel 实际消费路径

- [ ] **Step 5: 提交**

```bash
git add src/frontend/src/features/workspace/ui/views/WorkspaceKnowledgeCardsView.jsx tests/frontend/features/workspace/ui/views/WorkspaceKnowledgeCardsView.test.jsx
git commit -m "feat(frontend): add copy button to each knowledge card"
```

---

## Task 4: 迁移 `WorkspaceChatPanel` 到新组件

**Files:**
- Modify: `src/frontend/src/features/workspace/ui/WorkspaceChatPanel.jsx`

本任务不新增测试 (spec §Test Cases 已说明, ChatPanel 无 test.jsx)。验证手段: (a) grep 确认无残留; (b) 跑全量 vitest 确保无回归。

- [ ] **Step 1: 修改 WorkspaceChatPanel.jsx 顶部 import**

修改 `src/frontend/src/features/workspace/ui/WorkspaceChatPanel.jsx` line 3, 从 `lucide-react` 的 import 列表中移除 `Copy`, 并新增对 `CopyToClipboardButton` 的 import:

```js
import { Sparkles, ArrowUp, LoaderCircle, ChevronRight, Wrench, Clock3, BrainCircuit, CheckCircle2, FileText, PlayCircle } from "lucide-react";
```

在文件顶部 (line 3 之后) 新增:

```js
import { CopyToClipboardButton } from "./shared/CopyToClipboardButton";
```

- [ ] **Step 2: 替换复制按钮 JSX (line 262-271)**

将原:

```jsx
{canCopy ? (
  <button
    type="button"
    onClick={() => handleCopyMessage(message)}
    className="inline-flex items-center gap-1 rounded-full px-2 py-0.5 font-medium text-stone-400 transition hover:bg-stone-100 hover:text-stone-700 dark:text-stone-500 dark:hover:bg-stone-800 dark:hover:text-stone-200"
  >
    <Copy size={12} />
    {isCopied ? "已复制" : "复制"}
  </button>
) : null}
```

替换为:

```jsx
{canCopy ? (
  <CopyToClipboardButton
    text={message.content}
    iconSize={12}
    className="gap-1 rounded-full bg-transparent px-2 py-0.5 font-medium text-stone-400 hover:bg-stone-100 hover:text-stone-700 dark:bg-transparent dark:text-stone-500 dark:hover:bg-stone-800 dark:hover:text-stone-200"
  />
) : null}
```

- [ ] **Step 3: 删除本地 copyText 函数 (line 344-358)**

删除 `src/frontend/src/features/workspace/ui/WorkspaceChatPanel.jsx` 底部 `async function copyText(text) {...}` 整个函数定义。

- [ ] **Step 4: 删除 `copiedMessageId` state 和 `handleCopyMessage` handler**

删除:
- line 58: `const [copiedMessageId, setCopiedMessageId] = useState(null);`
- line 235 中: `const isCopied = copiedMessageId === message.id;`
- lines 97-106 整个 `handleCopyMessage` 函数

- [ ] **Step 5: grep 验证无残留**

Run:
```bash
cd src/frontend && grep -nE "copiedMessageId|setCopiedMessageId|isCopied|handleCopyMessage|async function copyText" src/features/workspace/ui/WorkspaceChatPanel.jsx
```
Expected: 无输出 (空)

> 若仍有残留, 回到 Step 4 补删。

- [ ] **Step 6: 跑全量 vitest 回归**

Run: `cd src/frontend && npm test`
Expected: 全部 passed (含 Task 1-3 新增的测试)。本步骤是 ChatPanel 迁移的唯一安全网。

- [ ] **Step 7: 提交**

```bash
git add src/frontend/src/features/workspace/ui/WorkspaceChatPanel.jsx
git commit -m "refactor(frontend): migrate chat copy button to CopyToClipboardButton"
```

---

## Self-Review

**1. Spec 覆盖核对:**

| Spec 项 | 任务 | 覆盖方式 |
|---|---|---|
| D1 buildCardMarkdown 完整覆盖 | Task 3 | 6 直接单测 (含 tags 为空/非数组/summary 为空/details 为 null/Markdown 特殊字符) |
| D2 copyText 行为 | Task 1 | 2 测试 (clipboard API 路径 + execCommand 兜底) |
| R1 默认 render + 右上角位置 | Task 2 + Task 3 | Task 2 默认 render 测试 + Task 3 视图渲染测试 |
| R2 copied 状态 + 1.6s 复原 | Task 2 | 2 测试 (状态切换 + 1600ms 复原) |
| R3 shrink-0 + flex | Task 3 | 视图 flex 容器断言 |
| R4 ChatPanel 视觉一致 | Task 4 | className 严格对齐 + grep 验证 (B7) |
| R5 aria-live/aria-label | Task 2 | aria-label 反映状态测试 |
| R6 hover 背景 | Task 2 | className 正则断言 (bg-stone-100 / hover:bg-stone-200) |
| B1 copyText reject 处理 | Task 2 | mockRejectedValueOnce + try/catch 行为测试 |
| B2 卸载清理 | Task 2 | unmount + advanceTimersByTime + 监控 console.error |
| B3 连点不提前复原 | Task 2 | fakeTimers + 两次点击断言 |
| B4 跨实例独立 | Task 2 + Task 3 | Task 2 单元测试 + Task 3 视图跨卡片测试 |
| B5 ChatPanel canCopy 守护 | Task 4 Step 2 | 保留原 canCopy 判断 (`{canCopy ? ... : null}`) |
| B6 键盘 Enter/Space | **不测** | 浏览器原生行为, 非组件代码; jsdom + fireEvent.keyDown 无法可靠触发 |
| B7 grep 无残留 | Task 4 Step 5 | grep -nE "copiedMessageId\|setCopiedMessageId\|isCopied\|handleCopyMessage\|async function copyText" |

**B6 决策:** spec B6 明文 "`<button type="button">` 默认行为，无额外处理"。组件未实现自定义键盘逻辑，测试浏览器默认行为 = 测试浏览器/框架, 非本组件代码。`@testing-library/user-event` 未安装 (`package.json` 确认); `fireEvent.keyDown` 在 jsdom 中不会触发原生 click → 测试不可靠。决定删除 2 个 B6 测试。

**2. Placeholder 扫描:**
- 已删除 Task 3 Step 1 的 `beforeEachProps` 占位和 `getByAllRole` 错字; 改为正确的 `beforeEach(() => {...})`。
- 其它 step 无 TBD / TODO / "implement later"。

**3. 类型/命名一致性:**
- `copyText(text)` 在 Task 1, 2, 3 一致
- `CopyToClipboardButton` props (`text` / `label` / `copiedLabel` / `iconSize` / `className`) 在 Task 2 定义, Task 3/4 使用一致
- `buildCardMarkdown(card)` 在 Task 3 定义并 export, Task 3 测试 + 视图使用
- `clipboard.js` 导出名 (`copyText`) 在 Task 1/2/3 一致
- vitest mock path (`@src/features/workspace/ui/shared/clipboard`) 在 Task 2/3 一致
- 测试 import 顺序统一为: testing-library → vitest → 模块 → vi.mock (避免 hoisting 误判)

无不一致。

---

## Execution

Plan complete. 推荐用 superpowers:subagent-driven-development 执行 (每任务一 fresh subagent, 中间审查), 也可以 inline 执行。