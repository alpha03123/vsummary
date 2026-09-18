import { ArrowLeft, ChevronLeft } from "lucide-react";

/**
 * 工具页里所有「返回」类按钮的唯一实现。
 *
 * 这个按钮此前在四个地方各写了一份，圆角从 rounded-lg / rounded-full / rounded-xl
 * 不等，字号 12px / 14px 混杂，有的带边框有的不带，视频预览页甚至用的是字符 `←`
 * 而不是图标组件 —— 同一件事渲染出四种样子。
 *
 * 现在统一为「裸文字」形态：常态无边框、无底色，只有 hover 时浮出一层浅底。
 * 这是刻意的选择 —— 工具页头部已经有一个导出菜单，再叠两个描边方块会让
 * 头部视觉重量过载；裸文字让返回动作退到次要位置，符合它的层级。
 *
 * 变体：
 *   default — 与导出按钮同排（工具页头），12px
 *   compact — 嵌在标题行里（AI 对话头），12px，间距更紧
 *   panel — 嵌在工作区卡片标题栏，固定 28px 高度以对齐相邻操作
 *   chevron — 笔记列表内部返回，保留 ChevronLeft 的方向语义
 */
export function WorkspaceBackButton({
  onClick,
  label = "返回工具页",
  variant = "default",
  icon: IconOverride,
  className = "",
}) {
  const isChevron = variant === "chevron";
  const Icon = IconOverride ?? (isChevron ? ChevronLeft : ArrowLeft);
  const gap = variant === "compact" ? "gap-1" : "gap-2";
  const padding = variant === "compact" ? "px-1.5 py-0.5" : variant === "panel" ? "h-7 px-2" : "px-2.5 py-1.5";

  return (
    <button
      type="button"
      onClick={onClick}
      className={`inline-flex shrink-0 items-center ${gap} whitespace-nowrap ${padding} rounded-xl text-xs font-semibold text-stone-600 transition hover:bg-stone-100 hover:text-stone-900 dark:text-stone-300 dark:hover:bg-stone-800 dark:hover:text-stone-100 ${className}`}
    >
      <Icon size={14} />
      {label}
    </button>
  );
}
