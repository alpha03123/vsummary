// 两条实际执行链分别推进；切换文字步骤不会把仍在进行的画面识别标为完成。
const STEPS = [
  { id: "prepare", label: "准备任务", lane: "main", stages: ["queued", "claimed", "prepare", "preparing", "queue", "batch"] },
  { id: "initialize", label: "准备识别和生成模型", lane: "main", stages: ["initialize"] },
  { id: "download", label: "下载视频", lane: "main", stages: ["download"] },
  { id: "subtitles", label: "检查视频字幕", lane: "main", stages: ["probe_subtitles"] },
  { id: "probe", label: "读取视频信息", lane: "main", stages: ["probe"] },
  { id: "audio", label: "读取视频中的声音", lane: "main", stages: ["extract_audio"] },
  { id: "transcript", label: "识别讲话并转换为文字", lane: "main", stages: ["transcribe"] },
  { id: "load_text", label: "读取已有字幕", lane: "main", stages: ["load_manual_srt", "load_transcript", "extract_subtitles"] },
  { id: "organize", label: "修正文字中的错字和断句", lane: "main", stages: ["enhance_transcript", "organize"] },
  { id: "summarize", label: "整理章节和要点", lane: "main", stages: ["summarize"] },
  { id: "chapter_images", label: "为章节添加截图", lane: "main", stages: ["extract_screenshots"] },
  { id: "sample_frames", label: "选取视频画面", lane: "ai", stages: ["sample_frames"] },
  { id: "ai_summary", label: "生成 AI 概况", lane: "ai", stages: ["generate_ai_summary", "understand_frames"] },
  { id: "note_images", label: "为概况添加截图", lane: "ai", stages: ["note_images"] },
  { id: "visual", label: "结合画面完善内容", lane: "main", stages: ["enrich_visual_summary"] },
  { id: "publish", label: "保存文字、概况和截图", lane: "main", stages: ["publish"] },
];

export function generationStageLabel(stage) {
  if (stage === "understand_frames") return "识别画面并生成概况";
  if (stage === "finalize_ai_summary") return "等待概况生成";
  if (stage === "ai_summary_completed") return "概况已生成";
  if (stage === "reconnecting") return "同步进度";
  if (stage === "cancelling") return "正在停止";
  if (["succeeded", "completed", "complete"].includes(stage)) return "已完成";
  return STEPS.find((step) => step.stages.includes(stage))?.label ?? "处理中";
}

export function advanceGenerationSteps(previous = [], snapshot) {
  if (snapshot.stage === "prepare" && previous.some((step) => step.id === "publish")) previous = [];
  const definition = STEPS.find((step) => step.stages.includes(snapshot.stage));
  const finishLane = snapshot.stage === "ai_summary_completed" ? "ai"
    : snapshot.stage === "finalize_ai_summary" ? "main" : null;
  const terminal = ["completed", "failed", "cancelled"].includes(snapshot.status);
  const steps = previous.map((step) => {
    if (step.status !== "running") return step;
    if (terminal) return { ...step, status: snapshot.status === "completed" ? "completed" : snapshot.status };
    if (step.lane === finishLane || (definition && step.lane === definition.lane && step.id !== definition.id)) {
      return { ...step, status: "completed" };
    }
    return step;
  });
  if (definition && !terminal) {
    const step = {
      id: definition.id,
      lane: definition.lane,
      label: generationStageLabel(snapshot.stage),
      status: "running",
      detail: snapshot.detail,
    };
    const index = steps.findIndex((item) => item.id === step.id);
    if (index === -1) steps.push(step);
    else steps[index] = step;
  }
  // 保持流程顺序；AI 任务可能在文字整理过程中并行开始。
  return steps.sort((a, b) => STEPS.findIndex((item) => item.id === a.id) - STEPS.findIndex((item) => item.id === b.id));
}

export function visibleGenerationSteps(snapshot, mode) {
  const steps = snapshot?.steps ?? advanceGenerationSteps([], snapshot ?? {});
  const pending = mode === "transcript"
    ? [{ id: "publish", label: "保存文字" }]
    : [{ id: "summarize", label: "整理章节和要点" }, { id: "publish", label: "保存生成结果" }];
  if (["completed", "failed", "cancelled"].includes(snapshot?.status)) return steps;
  return [...steps, ...pending.filter((item) => !steps.some((step) => step.id === item.id)).map((item) => ({ ...item, status: "pending" }))];
}
