import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { defaultUiSettings } from "@src/features/workspace/model/workspaceState";
import { WorkspaceSettingsPanel } from "@src/features/workspace/ui/WorkspaceSettingsPanel";

function renderPanel(uiOverrides = {}, propOverrides = {}) {
  return render(
    <WorkspaceSettingsPanel
      ui={{
        ...defaultUiSettings,
        ...uiOverrides,
      }}
      initialTab="keys"
      fasterWhisperModels={[]}
      fasterWhisperModelsLoading={false}
      ragModels={[]}
      onChangeSetting={vi.fn()}
      onSaveProviderSettings={vi.fn()}
      onSaveApiKey={vi.fn()}
      onRevealOpenaiApiKey={vi.fn()}
      onTestProviderConnection={vi.fn()}
      onDownloadFasterWhisperModel={vi.fn()}
      onDownloadRagModel={vi.fn()}
      onResetSettings={vi.fn()}
      onClose={vi.fn()}
      {...propOverrides}
    />,
  );
}

describe("WorkspaceSettingsPanel provider settings", () => {
  it("hides the API key editor for Ollama", () => {
    renderPanel({
      llmProvider: "ollama",
      openaiBaseUrl: "http://127.0.0.1:11434",
      openaiModel: "qwen2.5:7b",
    });

    expect(screen.queryByText("API Key")).not.toBeInTheDocument();
    expect(screen.queryByText("保存 Key")).not.toBeInTheDocument();
  });

  it("shows the API key editor for OpenAI-compatible providers", () => {
    renderPanel({
      llmProvider: "openai",
      openaiBaseUrl: "https://api.example.com",
      openaiModel: "gpt-5.4",
    });

    expect(screen.getByText("API Key")).toBeInTheDocument();
    expect(screen.getByText("保存 Key")).toBeInTheDocument();
  });

  it("shows the AI summary frame-pool budget only when frame input is enabled", () => {
    const { rerender } = renderPanel({ noteVisualInput: "evidence" }, { initialTab: "ai" });

    expect(screen.getByText("章节画面")).toBeInTheDocument();
    expect(screen.queryByText("AI 概括帧池上限")).not.toBeInTheDocument();

    rerender(
      <WorkspaceSettingsPanel
        ui={{ ...defaultUiSettings, noteVisualInput: "frames" }}
        initialTab="ai"
        fasterWhisperModels={[]}
        fasterWhisperModelsLoading={false}
        ragModels={[]}
        onChangeSetting={vi.fn()}
        onSaveProviderSettings={vi.fn()}
        onSaveApiKey={vi.fn()}
        onRevealOpenaiApiKey={vi.fn()}
        onTestProviderConnection={vi.fn()}
        onDownloadFasterWhisperModel={vi.fn()}
        onDownloadRagModel={vi.fn()}
        onResetSettings={vi.fn()}
        onClose={vi.fn()}
      />,
    );

    expect(screen.getByText("AI 概括帧池上限")).toBeInTheDocument();
  });

  it("opens the dedicated usage page from provider settings", () => {
    const onOpenUsagePage = vi.fn();
    renderPanel({}, { onOpenUsagePage });

    fireEvent.click(screen.getByRole("button", { name: "打开用量统计" }));

    expect(onOpenUsagePage).toHaveBeenCalledTimes(1);
  });

  it("allows an in-progress RAG download to be cancelled", () => {
    const onCancelRagModelDownload = vi.fn();
    renderPanel({}, {
      initialTab: "network",
      downloadingRagModelKey: "embedding",
      ragModels: [{
        key: "embedding",
        label: "bge-small-zh-v1.5",
        downloaded: false,
        status: "running",
        progress: 42,
      }],
      onCancelRagModelDownload,
    });

    fireEvent.click(screen.getByRole("button", { name: "取消下载" }));

    expect(onCancelRagModelDownload).toHaveBeenCalledWith("embedding");
  });
});

describe("WorkspaceSettingsPanel auto-generate multi-select", () => {
  it("renders the artifact options as toggle pills with the saved selection marked", () => {
    renderPanel({ autoGenerateArtifacts: ["notes"] }, { initialTab: "ai" });

    expect(screen.getByRole("button", { name: "笔记" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", { name: "思维导图" })).toHaveAttribute("aria-pressed", "false");
    expect(screen.getByRole("button", { name: "知识卡片" })).toHaveAttribute("aria-pressed", "false");
  });

  it("adds an artifact to the selection when toggled on", () => {
    const onChangeSetting = vi.fn();
    renderPanel({ autoGenerateArtifacts: ["notes"] }, { initialTab: "ai", onChangeSetting });

    fireEvent.click(screen.getByRole("button", { name: "思维导图" }));

    expect(onChangeSetting).toHaveBeenCalledWith("autoGenerateArtifacts", ["notes", "mindmap"]);
  });

  it("drops an artifact from the selection when toggled off", () => {
    const onChangeSetting = vi.fn();
    renderPanel({ autoGenerateArtifacts: ["notes", "mindmap"] }, { initialTab: "ai", onChangeSetting });

    fireEvent.click(screen.getByRole("button", { name: "笔记" }));

    expect(onChangeSetting).toHaveBeenCalledWith("autoGenerateArtifacts", ["mindmap"]);
  });
});
