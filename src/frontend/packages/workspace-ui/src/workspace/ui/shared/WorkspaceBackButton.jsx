import { ChevronLeft, LayoutGrid } from "lucide-react";

/**
 * 工具页里所有「返回」类按钮的唯一实现。
 *
 * 这个按钮此前在四个地方各写了一份，圆角从 rounded-lg / rounded-full / rounded-xl
 * 不等，字号 12px / 14px 混杂，有的带边框有的不带，视频预览页甚至用的是字符 `←`
 * 而不是图标组件 —— 同一件事渲染出四种样子。
 *
 * 现在统一为无边框的小按钮。「全部工具」用强调色浅底：它是用户找到其他工具的入口，
 * 新用户需要一眼看到它（只用浅底，不用实心，避免和页面主操作抢）。列表内的「返回」
 * （chevron）保持裸文字，hover 时才浮出浅底。
 *
 * 变体：
 *   default — 与导出按钮同排（工具页头），12px
 *   compact — 嵌在标题行里（AI 对话头），12px，间距更紧
 *   panel — 嵌在工作区卡片标题栏，固定 28px 高度以对齐相邻操作
 *   chevron — 笔记列表内部返回，保留 ChevronLeft 的方向语义
 */
export function WorkspaceBackButton({
  onClick,
  // The tool grid is not "back" for a new user who has never seen it, so it is named for what it is.
  label = "全部工具",
  variant = "default",
  icon: IconOverride,
  className = "",
}) {
  const isChevron = variant === "chevron";
  const Icon = IconOverride ?? (isChevron ? ChevronLeft : LayoutGrid);
  const gap = variant === "compact" ? "gap-1" : "gap-2";
  const padding = variant === "compact" ? "px-1.5 py-0.5" : variant === "panel" ? "h-7 px-2" : "px-2.5 py-1.5";
  // 「全部工具」is how users find the other tools, so it carries the accent (tinted, not solid:
  // one solid accent action per view). In-list "返回" (chevron) stays quiet.
  const tone = isChevron
    ? "font-medium text-subtle hover:bg-soft hover:text-strong"
    : "font-semibold bg-accent/10 text-accent hover:bg-accent/15";

  return (
    <button
      type="button"
      onClick={onClick}
      className={`inline-flex shrink-0 items-center ${gap} whitespace-nowrap ${padding} rounded-xl text-xs ${tone} transition ${className}`}
    >
      <Icon size={14} />
      {label}
    </button>
  );
}
