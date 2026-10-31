/** Writing styles the AI summary can be generated in; ids are the backend's template names. */
export const AI_SUMMARY_TEMPLATES = [
  { id: "general", label: "通用概括" },
  { id: "minimal", label: "要点速览" },
  { id: "detailed", label: "深度详记" },
  { id: "tutorial", label: "操作教程" },
  { id: "academic", label: "学术论文" },
  { id: "life_journal", label: "生活随笔" },
  { id: "task_oriented", label: "任务清单" },
  { id: "meeting_minutes", label: "会议纪要" },
];

export function getAiSummaryTemplate(templateId) {
  return AI_SUMMARY_TEMPLATES.find((template) => template.id === templateId) ?? AI_SUMMARY_TEMPLATES[0];
}
