import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { WorkspaceLegacyMigrationPanel } from "@src/features/workspace/ui/WorkspaceLegacyMigrationPanel";

describe("WorkspaceLegacyMigrationPanel", () => {
  it("shows three storage modes and requires cleanup confirmation before starting", async () => {
    const preview = {
      source_root: "E:\\old-vsummary",
      series: [
        { name: "复制系列", mode: "copy", effective_mode: "copy", media: [{}], external: [] },
        { name: "硬链接系列", mode: "hardlink", effective_mode: "hardlink", media: [{}], external: [] },
        { name: "外部引用系列", mode: "external_reference", effective_mode: "external_reference", media: [], external: [{}] },
      ],
      total_videos: 3,
      copy_bytes: 1024,
      target_free_bytes: 1024 * 1024,
      data: [{ name: "models", category: "copyable", bytes: 2048 }],
      warnings: [],
    };
    const onCreateRun = vi.fn().mockResolvedValue({ id: "run-1", status: "ready" });
    const onStartRun = vi.fn().mockResolvedValue({ id: "run-1", status: "running", total_videos: 3, verified_videos: 0, removed_videos: 0 });
    render(<WorkspaceLegacyMigrationPanel
      onSelectSource={vi.fn().mockResolvedValue({ path: "E:\\old-vsummary" })}
      onInspect={vi.fn().mockResolvedValue(preview)}
      onCreateRun={onCreateRun}
      onStartRun={onStartRun}
      onLoadRun={vi.fn().mockResolvedValue(null)}
      onLoadLatestRun={vi.fn().mockResolvedValue(null)}
      onCancelRun={vi.fn()}
    />);

    fireEvent.click(screen.getByRole("button", { name: "选择旧版目录" }));
    await screen.findByText("复制系列");
    expect(screen.getByText("硬链接系列")).toBeTruthy();
    expect(screen.getByText("外部引用系列")).toBeTruthy();
    const start = screen.getByRole("button", { name: "开始迁移" });
    expect(start.disabled).toBe(true);
    fireEvent.click(screen.getByRole("button", { name: /我了解/ }));
    fireEvent.click(start);

    await screen.findByText("迁移状态：迁移中");
    expect(onCreateRun).toHaveBeenCalledWith("E:\\old-vsummary", ["models"], false);
    expect(onStartRun).toHaveBeenCalledWith("run-1");
  });
});
