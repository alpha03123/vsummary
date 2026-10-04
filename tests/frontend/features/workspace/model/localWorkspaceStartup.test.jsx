import { act, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { WorkspaceApp } from "@workspace/runtime/WorkspaceApplication";
import { createLocalWorkspaceEffects } from "@src/local-features/workspace/model/LocalWorkspaceEffects";
import { defaultLocalUiSettings } from "@src/local-features/workspace/model/localUiSettings";

vi.mock("@workspace/workspace/ui/WorkspacePage", () => ({
  WorkspacePage: ({ page }) => (
    <output aria-label="workspace state">{JSON.stringify({
      theme: page.shell.ui.theme,
      ragModels: page.generation.ragModels,
      asrModels: page.generation.fasterWhisperModels,
      error: page.shell.state.error,
    })}</output>
  ),
}));

describe("Local workspace startup", () => {
  it("loads local settings and models into the live controller after backend readiness", async () => {
    let markBackendReady;
    const health = new Promise((resolve) => { markBackendReady = resolve; });
    const ragModels = [{ key: "embedding", status: "completed", downloaded: true }];
    const asrModels = [{ id: "large-v3-turbo", downloaded: true }];
    const localApi = {
      loadWorkspaceSettings: vi.fn().mockResolvedValue({ ...defaultLocalUiSettings, theme: "dark" }),
      loadRagModels: vi.fn().mockResolvedValue(ragModels),
      loadFasterWhisperModels: vi.fn().mockResolvedValue(asrModels),
    };
    const host = {
      api: {
        checkBackendHealth: vi.fn(() => health),
        loadWorkspaceLibrary: vi.fn().mockResolvedValue({ workspace: { id: "local", title: "Local" }, series: [] }),
        loadAgentMemoryStatus: vi.fn().mockResolvedValue({ status: "idle" }),
        dispose: vi.fn(),
      },
      storage: window.localStorage,
      initialUi: defaultLocalUiSettings,
      Effects: createLocalWorkspaceEffects(localApi),
    };

    const view = render(<WorkspaceApp host={host} />);
    expect(localApi.loadRagModels).not.toHaveBeenCalled();

    await act(async () => markBackendReady());

    await waitFor(() => {
      const state = JSON.parse(screen.getByLabelText("workspace state").textContent);
      expect(state).toMatchObject({ theme: "dark", ragModels, asrModels, error: "" });
    });
    view.unmount();
  });
});
