import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { WorkspaceSettingsPanel } from "@src/features/workspace/ui/WorkspaceSettingsPanel";
import { defaultUiSettings } from "@src/features/workspace/model/workspaceState";

function renderPanel(uiOverrides = {}) {
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
    />,
  );
}

describe("WorkspaceSettingsPanel provider settings", () => {
  it("hides the API key editor for Ollama while showing the provider-native request preview", () => {
    renderPanel({
      llmProvider: "ollama",
      openaiBaseUrl: "http://127.0.0.1:11434",
      openaiModel: "qwen2.5:7b",
    });

    expect(screen.queryByText("API Key")).not.toBeInTheDocument();
    expect(screen.queryByText("保存 Key")).not.toBeInTheDocument();
    expect(screen.getByText("http://127.0.0.1:11434/api/generate")).toBeInTheDocument();
  });

  it("previews the default Ollama native URL when base URL is empty", () => {
    renderPanel({
      llmProvider: "ollama",
      openaiBaseUrl: "",
      openaiModel: "qwen2.5:7b",
    });

    expect(screen.getByText("http://127.0.0.1:11434/api/generate")).toBeInTheDocument();
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
});
