import { ChevronLeft, LayoutGrid } from "lucide-react";

/**
 * 工具页里所有「返回」类按钮的唯一实现。
 *
 * 这个按钮此前在四个地方各写了一份，圆角从 rounded-lg / rounded-full / rounded-xl
 * 不等，字号 12px / 14px 混杂，有的带边框有的不带，视频预览页甚至用的是字符 `←`
 * 而不是图标组件 —— 同一件事渲染出四种样子。
 *
 * 现在统一为无边框的小按钮。在标题旁边时，「全部工具」做成面包屑（crumb）：
 * 「全部工具 › AI 概括」，放在标题前面，用次要色，hover 时才变强调色。之前它是贴在标题后面的
 * 强调色浅底胶囊，看起来像分段切换里「当前选中」的那一项，和实际层级正好相反。
 * 列表内的「返回」（chevron）保持裸文字，hover 时才浮出浅底。
 *
 * 变体：
 *   default — 与导出按钮同排（工具页头），12px
 *   compact — 嵌在标题行里（AI 对话头），12px，间距更紧
 *   panel — 嵌在工作区卡片标题栏（手机端标签栏右侧），固定 28px 高度以对齐相邻操作
 *   crumb — 面包屑的上一级，放在当前工具名前面（桌面面板标题、工具页头）
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
  const padding = variant === "compact" ? "px-1.5 py-0.5" : variant === "panel" ? "h-7 px-2" : variant === "crumb" ? "h-7 -ml-1.5 px-1.5" : "px-2.5 py-1.5";
  // A crumb reads as "the level above": quiet until hovered. The tinted accent chip is kept for the
  // narrow tab bar, where it sits apart from the tab labels. In-list "返回" (chevron) stays quiet.
  const tone = isChevron
    ? "font-medium text-subtle hover:bg-soft hover:text-strong"
    : variant === "crumb"
      ? "font-medium text-subtle hover:bg-accent/10 hover:text-accent"
      : "font-semibold bg-accent/10 text-accent hover:bg-accent/15";

  return (
    <button
      type="button"
      onClick={onClick}
      className={`inline-flex shrink-0 items-center ${gap} whitespace-nowrap ${padding} ${variant === "crumb" ? "rounded-lg" : "rounded-xl"} text-xs ${tone} transition ${className}`}
    >
      <Icon size={14} />
      {label}
    </button>
  );
}
