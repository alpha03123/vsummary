import { fireEvent, render, screen, waitFor } from "@testing-library/react";
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
      initialTab={propOverrides.initialTab ?? "keys"}
      fasterWhisperModels={[]}
      fasterWhisperModelsLoading={false}
      ragModels={[]}
      onChangeSetting={propOverrides.onChangeSetting ?? vi.fn()}
      onSaveProviderSettings={vi.fn()}
      onSaveApiKey={vi.fn()}
      onRevealOpenaiApiKey={vi.fn()}
      onTestProviderConnection={vi.fn()}
      onDownloadFasterWhisperModel={vi.fn()}
      onDownloadRagModel={vi.fn()}
      onInitBilibiliCookie={propOverrides.onInitBilibiliCookie ?? vi.fn()}
      onCreateBilibiliQrLoginSession={propOverrides.onCreateBilibiliQrLoginSession ?? vi.fn()}
      onPollBilibiliQrLogin={propOverrides.onPollBilibiliQrLogin ?? vi.fn()}
      onResetSettings={vi.fn()}
      onClose={vi.fn()}
    />,
  );
}

describe("WorkspaceSettingsPanel provider settings", () => {
  it("shows and updates the series markdown export path setting", () => {
    const onChangeSetting = vi.fn();

    renderPanel(
      { seriesMarkdownExportPath: "D:/exports" },
      { initialTab: "general", onChangeSetting },
    );

    const input = screen.getByLabelText("系列 Markdown 默认导出路径");
    expect(input).toHaveValue("D:/exports");

    fireEvent.change(input, { target: { value: "E:/notes" } });

    expect(onChangeSetting).toHaveBeenCalledWith("seriesMarkdownExportPath", "E:/notes");
  });

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

  it("saves pasted Bilibili Cookie through BiliNote-style payload", async () => {
    const onInitBilibiliCookie = vi.fn().mockResolvedValue({ configured: true });

    renderPanel({}, { initialTab: "external-import", onInitBilibiliCookie });

    fireEvent.change(screen.getByPlaceholderText("SESSDATA=...; buvid3=...; bili_jct=..."), {
      target: { value: "SESSDATA=session-value; buvid3=fingerprint-value; bili_jct=csrf-value" },
    });
    fireEvent.click(screen.getByRole("button", { name: "保存 Bilibili Cookie" }));

    await waitFor(() => expect(onInitBilibiliCookie).toHaveBeenCalledWith({
      cookie: "SESSDATA=session-value; buvid3=fingerprint-value; bili_jct=csrf-value",
    }));
    expect(screen.getByText("Bilibili Cookie 已保存"));
  });

  it("starts Bilibili QR login and shows the scan prompt", async () => {
    const onCreateBilibiliQrLoginSession = vi.fn().mockResolvedValue({
      url: "https://passport.bilibili.com/qrcode",
      qrcodeKey: "qr-key",
    });

    renderPanel({}, { initialTab: "external-import", onCreateBilibiliQrLoginSession });

    fireEvent.click(screen.getByRole("button", { name: "扫码登录 Bilibili" }));

    await waitFor(() => expect(onCreateBilibiliQrLoginSession).toHaveBeenCalledTimes(1));
    expect(screen.getByText("使用 Bilibili App 扫码确认登录")).toBeInTheDocument();
    expect(screen.getByText("https://passport.bilibili.com/qrcode")).toBeInTheDocument();
  });

  it("checks Bilibili QR login status and reports configured", async () => {
    const onCreateBilibiliQrLoginSession = vi.fn().mockResolvedValue({
      url: "https://passport.bilibili.com/qrcode",
      qrcodeKey: "qr-key",
    });
    const onPollBilibiliQrLogin = vi.fn().mockResolvedValue({
      status: "confirmed",
      message: "扫码登录成功",
      configured: true,
    });

    renderPanel({}, { initialTab: "external-import", onCreateBilibiliQrLoginSession, onPollBilibiliQrLogin });

    fireEvent.click(screen.getByRole("button", { name: "扫码登录 Bilibili" }));
    await screen.findByText("使用 Bilibili App 扫码确认登录");
    fireEvent.click(screen.getByRole("button", { name: "检查登录状态" }));

    await waitFor(() => expect(onPollBilibiliQrLogin).toHaveBeenCalledWith("qr-key"));
    expect(screen.getByText("扫码登录成功"));
  });
});
