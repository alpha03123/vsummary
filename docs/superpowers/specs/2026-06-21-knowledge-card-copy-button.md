# 知识卡片每个知识点加复制按钮（Markdown 格式）

2026-06-21 | Status: Design

## Overview

在 `WorkspaceKnowledgeCardsView` 渲染的每张知识卡片右上角加一个"复制"按钮，点击后将该卡片的完整内容（标题 + 摘要 + 详情 + 标签）按 Markdown 格式写入剪贴板。复制成功时按钮切换为"已复制"反馈，持续约 1.6s 后复原。

实现采用"提取共享"的策略：把 `WorkspaceChatPanel.jsx` 中私有的 `copyText` 工具函数和复制按钮模式抽到 `ui/shared/`，让 ChatPanel 与 KnowledgeCardsView 共用同一组件，消除当前已存在的代码重复。

## Current State

- `WorkspaceKnowledgeCardsView.jsx:86-117` 渲染卡片网格，每张卡片包含 `kind` / `title` / `summary` / `details` / `tags`。无任何交互按钮。
- 数据 shape（`workspaceViewModel.js:85-99`）：`{ id, title, kind, summary, details, tags[], keywords[], relatedCardIds[] }`。
- `WorkspaceChatPanel.jsx:344-358` 有私有的 `copyText` 函数（14 行，含 `navigator.clipboard.writeText` + `execCommand` 兜底）。
- `WorkspaceChatPanel.jsx:97-106` 有 `handleCopyMessage` 模式：`setCopiedMessageId` + `window.setTimeout` 1600ms 复原。
- `ui/shared/` 目录已存在（`WorkspaceStateBlock` / `WorkspaceFeedbackBanner` / `WorkspaceMarkdownMessage` 等），是跨视图组件的合理落点。
- 全工程 `copyText`/`writeText` 只在 `WorkspaceChatPanel.jsx` 出现 1 次（grep 已确认）。
- 测试现状：`tests/frontend/features/workspace/ui/shared/` 目前只有 `WorkspaceMarkdownMessage.test.jsx` 等的散落用例，复制组件无测试覆盖。

## Design

### 1. 新文件 `src/frontend/src/features/workspace/ui/shared/clipboard.js`

直接迁移 `WorkspaceChatPanel.jsx:344-358` 的 `copyText`，加 `export`：

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

### 2. 新文件 `src/frontend/src/features/workspace/ui/shared/CopyToClipboardButton.jsx`

```jsx
import { useEffect, useRef, useState } from "react";
import { Check, Copy } from "lucide-react";
import { copyText } from "./clipboard";

export function CopyToClipboardButton({ text, label = "复制", copiedLabel = "已复制", iconSize = 14, className = "" }) {
  const [copied, setCopied] = useState(false);
  const timeoutRef = useRef(null);

  useEffect(() => () => {
    if (timeoutRef.current) window.clearTimeout(timeoutRef.current);
  }, []);

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

关键设计点：
- **timeout ref + 卸载清理**：避免组件卸载后 `setState` 警告
- **覆盖时清理前一个 timeout**：连点不会出现"提前复原"
- **`aria-live="polite"` + `aria-label`**：状态变化对屏幕阅读器可读
- **`label` / `copiedLabel` 可覆盖**：ChatPanel 后续如需英文文案也可复用
- **`try/catch` 包裹 `copyText`**：复制失败时按钮不进入"已复制"状态（AC B1）

> 默认视觉为 KnowledgeCardsView 设计；ChatPanel 通过 `className` 覆盖以保留原视觉（见 §5）。

### 3. 新增纯函数 `buildCardMarkdown`

放在 `WorkspaceKnowledgeCardsView.jsx` 文件顶部（不导出，仅本视图使用）：

```js
function buildCardMarkdown(card) {
  const tagsLine = Array.isArray(card.tags) && card.tags.length
    ? `**Tags:** ${card.tags.join(", ")}`
    : "";
  return [
    `# ${card.title}`,
    "",
    card.summary,
    "",
    card.details,
    tagsLine,
  ].filter(Boolean).join("\n");
}
```

- `filter(Boolean)` 跳过空字符串段（tags 为空时不会留一个多余的空行）
- 标题前后加换行使 markdown 在 VS Code / Obsidian 等渲染器里结构清晰

### 4. `WorkspaceKnowledgeCardsView.jsx` 改动

把当前 `<article>` 头部那个 `<div>` 改为 flex 容器（`WorkspaceKnowledgeCardsView.jsx:95-98`）：

```jsx
<div className="flex items-start justify-between gap-3">
  <div>
    <p className="text-[10px] font-bold uppercase tracking-widest text-stone-500 dark:text-stone-400">{card.kind}</p>
    <h3 className="mt-2 text-lg font-bold text-stone-900 dark:text-stone-100">{card.title}</h3>
  </div>
  <CopyToClipboardButton text={buildCardMarkdown(card)} className="shrink-0" />
</div>
```

文件顶部新增 import：`import { CopyToClipboardButton } from "../shared/CopyToClipboardButton";`

### 5. `WorkspaceChatPanel.jsx` 迁移

**5a.** 文件顶部 import 调整（line 3 当前 import 中的 `Copy` 图标随按钮删除后变为 unused，从 import 列表移除）：

```js
import { CopyToClipboardButton } from "./shared/CopyToClipboardButton";
```

**5b.** 现有复制按钮位于 `WorkspaceChatPanel.jsx:262-271`，目前被 `canCopy`（line 234: `typeof message.content === "string" && message.content.trim()`）守护。**为保留原视觉**（消息气泡内的 chip：圆角更小、无背景色、颜色更浅），通过 `className` 覆盖默认：

```jsx
{canCopy ? (
  <CopyToClipboardButton
    text={message.content}
    iconSize={12}
    className="gap-1 rounded-full bg-transparent px-2 py-0.5 font-medium text-stone-400 hover:bg-stone-100 hover:text-stone-700 dark:bg-transparent dark:text-stone-500 dark:hover:bg-stone-800 dark:hover:text-stone-200"
  />
) : null}
```

视觉对照（与原 line 263-270 一致）：
- `rounded-full` ✓（原为 `rounded-full`，默认是 `rounded-xl`）
- `px-2 py-0.5` ✓（默认 `px-2.5 py-1.5`）
- `gap-1` ✓（默认 `gap-1.5`）
- `text-stone-400` ✓（默认 `text-stone-600`）
- 无背景 + hover 变色 ✓
- `font-medium` ✓（默认 `font-semibold`）
- `iconSize={12}` ✓（默认 14）

**5c.** 删除现有 state 与 handler：
- `useState(null)` 的 `copiedMessageId`（line 58）
- `handleCopyMessage`（lines 97-106）
- 复制按钮处的 `isCopied` 计算（line 235）

**5d.** 删除文件底部私有 `copyText`（lines 344-358）。

**5e.** 实施后 grep 验证 `WorkspaceChatPanel.jsx` 中无 `copiedMessageId` / `isCopied` / `Copy icon` 残留。

> `canCopy` 已包含字符串判断（B4 不需要额外处理）。

## Acceptance Criteria

> AC 中的"复制"/"已复制"指组件默认 props 的 `label`/`copiedLabel`；调用方可通过 props 覆盖。

### 数据契约 (D)

| AC# | Condition |
|-----|-----------|
| D1 | `buildCardMarkdown(card)` 返回字符串，tags 为空时不包含 `**Tags:**` 行，tags 非空时以 `**Tags:** t1, t2` 格式拼接；`card.summary` / `card.details` 为 null 或空字符串时该段被省略（不留下连续空行） |
| D2 | `copyText` 行为与迁移前完全一致：优先 `navigator.clipboard.writeText`，回退到 `textarea + execCommand` |

### 渲染行为 (R)

| AC# | Condition |
|-----|-----------|
| R1 | 每张知识卡片右上角显示"复制"按钮，含 Copy 图标 + 文案"复制"（默认 props） |
| R2 | 按钮点击成功后图标变为 Check、文案变为"已复制"、背景色变为 emerald-100（深色模式 emerald-900/40），持续约 1.6s 后复原为初始状态 |
| R3 | 按钮在卡片头部右对齐，使用 `shrink-0` 保证不被长 title 挤压 |
| R4 | ChatPanel 复制按钮迁移后视觉与迁移前完全一致（`rounded-full px-2 py-0.5 gap-1 text-stone-400 font-medium` + hover 变色），行为一致（图标 + 文字反馈 + 1.6s 复原） |
| R5 | 默认状态下按钮带 `aria-label` 与 `aria-live="polite"` 属性，label 反映当前状态（"复制" / "已复制"） |
| R6 | 默认按钮初始态（非 copied）背景为 `bg-stone-100`，鼠标 hover 时切换为 `bg-stone-200`（深色模式对应 `bg-stone-800` / `bg-stone-700`） |

### 行为 / 降级 (B)

| AC# | Condition |
|-----|-----------|
| B1 | `copyText` reject 时按钮**不**进入"已复制"状态（保持初始态），且异常不冒泡到 React（无 unhandled rejection 警告） |
| B2 | 组件在 copied 状态下被卸载，`window.clearTimeout` 被调用，无 React 警告 |
| B3 | 用户在 1.6s 内连点**同一**按钮，复原时间以最后一次点击起算（不提前复原） |
| B4 | 用户在 1.6s 内连点**不同**卡片的按钮，两张卡片各自显示独立的"已复制"状态，互不影响 |
| B5 | ChatPanel 中非字符串 `message.content` 的消息不显示复制按钮（保留原 `handleCopyMessage` 中的 `canCopy` 语义，line 234） |
| B6 | 按钮可通过键盘 Enter 或 Space 触发（`<button type="button">` 默认行为，无额外处理） |
| B7 | 实施后 `WorkspaceChatPanel.jsx` 中 grep `copiedMessageId` / `isCopied` 无残留（lines 58, 235, 269 已清理） |

## Test Cases

> 测试结构与项目现有约定一致（参考 `ChatDrawer.test.jsx`、`useWorkspaceController.test.js`）：`describe("Component", () => { it("does X", ...) })`，中文描述，无 `test_*` 前缀。

```
新建 tests/frontend/features/workspace/ui/shared/clipboard.test.js
  describe("copyText")
    it("writes to navigator.clipboard when available")            # D2 happy path
    it("falls back to execCommand when clipboard API is unavailable")  # D2 fallback

新建 tests/frontend/features/workspace/ui/shared/CopyToClipboardButton.test.jsx
  describe("CopyToClipboardButton")
    it("renders Copy 图标 + 默认文案'复制'")                        # R1
    it("点击后切换为 Check 图标 + '已复制'文案 + emerald 背景")     # R2
    it("aria-label 反映当前状态")                                   # R5
    it("初始态 hover 切换背景色")                                   # R6
    it("1600ms 后复原初始态")                                       # R2
    it("连点同一按钮, 复原时间以最后一次为准")                       # B3
    it("卸载时清除 timeout, 无 React 警告")                          # B2
    it("copyText reject 时保持初始态, 不进入 copied")                # B1
    it("Enter 键触发复制")                                          # B6
    it("Space 键触发复制")                                          # B6
    it("不同实例的 copied 状态相互独立")                             # B4 (与视图测试配合)

新建 tests/frontend/features/workspace/ui/views/WorkspaceKnowledgeCardsView.test.jsx
  describe("buildCardMarkdown")
    it("包含标题、摘要、详情和 tags 行")                            # D1 happy
    it("tags 为空数组时省略 Tags 行")                                # D1
    it("tags 为非数组或非字符串时省略 Tags 行")                     # D1 边界
    it("summary 为空字符串时该段省略, 不留空行")                     # D1
    it("details 为 null 时该段省略")                                 # D1
    it("保留 Markdown 特殊字符 (#, *, `, >) 不转义")                # 安全/正确性

  describe("WorkspaceKnowledgeCardsView - 复制按钮")
    it("每张卡片渲染一个复制按钮")                                  # R1
    it("按钮位于卡片右上角 (flex 容器 justify-between)")            # R3
    it("点击按钮复制包含完整 Markdown 的文本")                       # D1 + R2
    it("两张卡片同时点击各自显示独立 '已复制' 状态")                 # B4
    it("hover 卡片时按钮仍可见 (常驻右上角, 不依赖 hover)")          # R1 + R3

# ChatPanel 暂不新增测试 (已 grep 确认 test.jsx 不存在); 视觉一致性靠 §5b 的 className 严格对齐保证
```

测试运行命令：`cd src/frontend && npm test -- --run <path>`。

### 跳过 E2E (按用户要求)
- 不引入 Playwright / Cypress 浏览器端 E2E 测试
- 不通过 UI 截图断言视觉（hover / dark mode 通过 className 字符串断言）

## Scope

| 类别 | 文件 | 改动 | 备注 |
|---|---|---|---|
| 新建 | `src/frontend/src/features/workspace/ui/shared/clipboard.js` | 迁移 + export copyText | 14 行 |
| 新建 | `src/frontend/src/features/workspace/ui/shared/CopyToClipboardButton.jsx` | 新组件 | ~50 行 |
| 编辑 | `src/frontend/src/features/workspace/ui/views/WorkspaceKnowledgeCardsView.jsx` | import + buildCardMarkdown + 头部 flex 容器 | +15 行 |
| 编辑 | `src/frontend/src/features/workspace/ui/WorkspaceChatPanel.jsx` | 替换为新组件,删除本地 copyText/state | -10/+5 行 |
| 新建 | `tests/frontend/features/workspace/ui/shared/clipboard.test.js` | 2 用例 | 新建 |
| 新建 | `tests/frontend/features/workspace/ui/shared/CopyToClipboardButton.test.jsx` | 11 用例 | 新建 |
| 新建 | `tests/frontend/features/workspace/ui/views/WorkspaceKnowledgeCardsView.test.jsx` | 11 用例 (6 buildCardMarkdown + 5 视图) | 新建 |
| 文档 | `docs/superpowers/specs/2026-06-21-knowledge-card-copy-button.md` | 本 spec | — |

合计：**4 个源文件（2 新 + 2 改）+ 3 个测试文件新建 + 1 个 spec**，净增约 80-120 行。

## Risks & Mitigations

| 风险 | 缓解 |
|---|---|
| `navigator.clipboard` 在非安全上下文（HTTP）下不可用 | `copyText` 已有 `execCommand` 兜底（D2） |
| `navigator.clipboard.writeText` 存在但 reject（如权限拒绝） | `copyText` 当前不处理（保持原行为）；按钮组件 try/catch 包裹,不进入 copied 状态（B1）。**不修改 `copyText` 的拒绝行为（YAGNI / 非本次范围）** |
| 快速连点导致 timeout 泄漏 | ref 持有 + 每次点击前 `clearTimeout`（B3） |
| 组件卸载后 setState | useEffect cleanup 清 timeout（B2） |
| ChatPanel 复制按钮视觉回归（圆角/尺寸/颜色/字重） | 通过 `className` 显式覆盖默认值，逐项对齐 `WorkspaceChatPanel.jsx:263-270`（§5b 视觉对照） |
| `buildCardMarkdown` 与卡片实际渲染文本不一致（LLM 含特殊字符、HTML 转义差异） | Markdown 是文本复制,React 文本节点不解析 HTML,语义一致 |
| ChatPanel 中 `message.content` 类型多样（string / array / null） | `canCopy` 已在 line 234 守护（B5） |
| ChatPanel 删除 `copiedMessageId` / `isCopied` 后遗漏 | 实施后 grep `WorkspaceChatPanel.jsx` 验证无残留（B7） |

## Out of Scope

- 全局键盘快捷键（如 Cmd/Ctrl+Shift+C）
- 复制失败的 toast 通知
- 复制时附带视频来源 / seriesId 等元数据（YAGNI；Markdown 仅为卡片内容本身）
- 把 `buildCardMarkdown` 抽到独立工具文件（仅本视图使用）
- ChatPanel 中其他复制需求（如 thinking trace、引用块等）的批量迁移（本次只迁现有复制按钮）
- 国际化（i18n）文案处理（项目目前无 i18n 框架）