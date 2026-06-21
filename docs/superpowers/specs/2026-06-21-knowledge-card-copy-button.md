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
    await copyText(text);
    setCopied(true);
    if (timeoutRef.current) window.clearTimeout(timeoutRef.current);
    timeoutRef.current = window.setTimeout(() => setCopied(false), 1600);
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

**5a.** 文件顶部 import 调整（当前文件已有 `Check` / `Copy` 之类图标，按需替换）：

```js
import { CopyToClipboardButton } from "./shared/CopyToClipboardButton";
import { copyText } from "./shared/clipboard";
```

**5b.** 现有复制按钮位于 `WorkspaceChatPanel.jsx:262-268`，目前被 `canCopy`（line 234: `typeof message.content === "string" && message.content.trim()`）守护。改造方案：

```jsx
{canCopy ? (
  <CopyToClipboardButton text={message.content} />
) : null}
```

**5c.** 删除现有 state 与 handler：
- `useState(null)` 的 `copiedMessageId`（line 58）
- `handleCopyMessage`（lines 97-106）
- 复制按钮处的 `isCopied` 计算与条件渲染分支（lines 235 / 265）

**5d.** 删除文件底部私有 `copyText`（lines 344-358）。

**5e.** 文件顶部 import 调整（line 3 当前的 `Copy` 图标若已无用则移除，新增）：

```js
import { CopyToClipboardButton } from "./shared/CopyToClipboardButton";
```

> `canCopy` 已包含字符串判断（B4 不需要额外处理）。

## Acceptance Criteria

### 数据契约 (D)

| AC# | Condition |
|-----|-----------|
| D1 | `buildCardMarkdown(card)` 返回字符串，tags 为空时不包含 `**Tags:**` 行，tags 非空时以 `**Tags:** t1, t2` 格式拼接 |
| D2 | `copyText` 行为与迁移前完全一致：优先 `navigator.clipboard.writeText`，回退到 `textarea + execCommand` |

### 渲染行为 (R)

| AC# | Condition |
|-----|-----------|
| R1 | 每张知识卡片右上角显示"复制"按钮，含 Copy 图标 + 文案"复制" |
| R2 | 按钮点击后图标变为 Check、文案变为"已复制"、背景色变为绿色系（emerald），持续约 1.6s 后复原为初始状态 |
| R3 | 按钮在卡片头部右对齐，使用 `shrink-0` 保证不被长 title 挤压 |
| R4 | ChatPanel 的现有复制按钮改为复用 `<CopyToClipboardButton>`，行为与之前一致（图标 + 文字反馈 + 1.6s 复原） |

### 行为 / 降级 (B)

| AC# | Condition |
|-----|-----------|
| B1 | 复制失败（`clipboard.writeText` reject）时不抛 UI 异常；按钮不切换到"已复制"状态（或切换后立即复原，行为可接受） |
| B2 | 组件在 copied 状态下被卸载，`window.clearTimeout` 被调用，无 React 警告 |
| B3 | 用户在 1.6s 内连点按钮，复原时间以最后一次点击起算（不提前复原） |
| B4 | ChatPanel 中非字符串 `message.content` 的消息不显示复制按钮（保留原 `handleCopyMessage` 中的字符串判断语义） |

## Test Cases

```
# 新建 tests/frontend/features/workspace/ui/shared/clipboard.test.js
  - test_copyText_uses_clipboard_api_when_available
    (mock navigator.clipboard.writeText, 验证调用)
  - test_copyText_falls_back_to_execCommand_when_clipboard_unavailable
    (mock 缺失 clipboard, 验证 execCommand 路径)

# 新建 tests/frontend/features/workspace/ui/shared/CopyToClipboardButton.test.jsx
  - test_renders_copy_icon_and_label_by_default
  - test_click_copies_text_and_shows_check_icon_and_copied_label
  - test_reverts_to_initial_state_after_1600ms  (用 vi.useFakeTimers)
  - test_consecutive_clicks_reset_timer  (连点不提前复原)
  - test_clears_timeout_on_unmount  (无 React 警告)

# 新建 tests/frontend/features/workspace/ui/views/WorkspaceKnowledgeCardsView.test.jsx
  - test_renders_copy_button_on_each_card
  - test_clicking_copy_button_copies_markdown_with_title_summary_details_tags
  - test_markdown_omits_tags_line_when_card_has_no_tags
  - test_concurrent_clicks_only_last_timer_wins

# ChatPanel 现有复制相关测试（如有）保留并适配：
  tests/frontend/features/workspace/ui/WorkspaceChatPanel.test.jsx
    - 复用 CopyToClipboardButton 后,断言点击触发复制即可,不再单独断言内部 state
```

> 当前 ChatPanel 无 test.jsx（已 grep 确认）；若未来新增，按上述模式处理。

测试运行命令：`cd src/frontend && npm test -- --run <path>`。

## Scope

| 类别 | 文件 | 改动 | 备注 |
|---|---|---|---|
| 新建 | `src/frontend/src/features/workspace/ui/shared/clipboard.js` | 迁移 + export copyText | 14 行 |
| 新建 | `src/frontend/src/features/workspace/ui/shared/CopyToClipboardButton.jsx` | 新组件 | ~45 行 |
| 编辑 | `src/frontend/src/features/workspace/ui/views/WorkspaceKnowledgeCardsView.jsx` | import + buildCardMarkdown + 头部 flex 容器 | +15 行 |
| 编辑 | `src/frontend/src/features/workspace/ui/WorkspaceChatPanel.jsx` | 替换为新组件,删除本地 copyText/state | -10/+5 行 |
| 新建 | `tests/frontend/features/workspace/ui/shared/clipboard.test.js` | 2 用例 | 新建 |
| 新建 | `tests/frontend/features/workspace/ui/shared/CopyToClipboardButton.test.jsx` | 5 用例 | 新建 |
| 新建 | `tests/frontend/features/workspace/ui/views/WorkspaceKnowledgeCardsView.test.jsx` | 4 用例 | 新建 |
| 文档 | `docs/superpowers/specs/2026-06-21-knowledge-card-copy-button.md` | 本 spec | — |

合计：**4 个源文件（2 新 + 2 改）+ 3 个测试文件新建 + 1 个 spec**，净增约 80-120 行。

## Risks & Mitigations

| 风险 | 缓解 |
|---|---|
| `navigator.clipboard` 在非安全上下文（HTTP）下不可用 | `copyText` 已有 `execCommand` 兜底（B2/D2） |
| 快速连点导致 timeout 泄漏 | ref 持有 + 每次点击前 `clearTimeout`（B3） |
| 组件卸载后 setState | useEffect cleanup 清 timeout（B2） |
| ChatPanel 现有复制按钮的尺寸/位置在新组件下不一致 | `className` 透传支持覆盖；本次 ChatPanel 复制按钮位置不变（消息气泡内），文案/图标风格保持一致 |
| `buildCardMarkdown` 与卡片实际渲染文本不一致（LLM 含特殊字符、HTML 转义差异） | Markdown 是文本复制,React 文本节点不解析 HTML,语义一致 |
| ChatPanel 中 `message.content` 类型多样（string / array / null） | 在 ChatPanel 渲染处判断字符串后再渲染按钮（B4） |

## Out of Scope

- 全局键盘快捷键（如 Cmd/Ctrl+Shift+C）
- 复制失败的 toast 通知
- 复制时附带视频来源 / seriesId 等元数据（YAGNI；Markdown 仅为卡片内容本身）
- 把 `buildCardMarkdown` 抽到独立工具文件（仅本视图使用）
- ChatPanel 中其他复制需求（如 thinking trace、引用块等）的批量迁移（本次只迁现有复制按钮）
- 国际化（i18n）文案处理（项目目前无 i18n 框架）