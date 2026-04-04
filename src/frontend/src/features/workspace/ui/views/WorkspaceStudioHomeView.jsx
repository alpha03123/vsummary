import { WorkspaceStateBlock } from "../shared/WorkspaceStateBlock";

export function WorkspaceStudioHomeView() {
  return (
    <WorkspaceStateBlock
      eyebrow="Studio Home"
      title="选择一个工具进入工作页"
      description="AI概况、思维导图、知识卡片、笔记和视频预览现在都是独立工具页。点上面的卡片进入，完成后再返回工具页切换其他工具。"
      dashed
    />
  );
}
