import { describe, expect, it } from "vitest";
import { advanceGenerationSteps, visibleGenerationSteps } from "@src/features/workspace/model/generationSteps";

const event = (stage, status = "running") => ({ stage, status, detail: stage });

describe("generation steps", () => {
  it("starts a fresh step list for the next video in a series", () => {
    const steps = advanceGenerationSteps([], event("publish"));
    expect(advanceGenerationSteps(steps, event("prepare")).map((step) => step.id)).toEqual(["prepare"]);
  });

  it("keeps the picture task running when the text task changes stages", () => {
    let steps = [];
    for (const stage of ["transcribe", "summarize", "sample_frames", "understand_frames", "extract_screenshots", "finalize_ai_summary"]) {
      steps = advanceGenerationSteps(steps, event(stage));
    }
    expect(steps.find((step) => step.id === "chapter_images").status).toBe("completed");
    expect(steps.find((step) => step.id === "sample_frames").status).toBe("completed");
    expect(steps.find((step) => step.id === "ai_summary")).toMatchObject({ status: "running", label: "识别画面并生成概况" });
    steps = advanceGenerationSteps(steps, event("ai_summary_completed"));
    expect(steps.find((step) => step.id === "ai_summary").status).toBe("completed");
  });

  it("does not invent speech recognition or picture steps when existing subtitles are used", () => {
    let steps = [];
    for (const stage of ["initialize", "load_manual_srt", "summarize", "generate_ai_summary"]) {
      steps = advanceGenerationSteps(steps, event(stage));
    }
    const visible = visibleGenerationSteps({ ...event("generate_ai_summary"), steps }, "summary");
    expect(visible.map((step) => step.id)).toEqual(["initialize", "load_text", "summarize", "ai_summary", "publish"]);
    expect(visible.find((step) => step.id === "ai_summary").label).toBe("生成 AI 概况");
  });

  it("shows only text saving as the next step in transcript mode", () => {
    expect(visibleGenerationSteps(event("transcribe"), "transcript").map((step) => step.id)).toEqual(["transcript", "publish"]);
  });

  it("marks active tasks as stopped on cancellation without claiming they completed", () => {
    let steps = advanceGenerationSteps([], event("summarize"));
    steps = advanceGenerationSteps(steps, event("sample_frames"));
    steps = advanceGenerationSteps(steps, event("cancelled", "cancelled"));
    expect(steps.every((step) => step.status === "cancelled")).toBe(true);
  });
});
