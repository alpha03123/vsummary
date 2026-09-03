import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { WorkspaceImportModal } from "@src/features/workspace/ui/WorkspaceImportModal";

describe("WorkspaceImportModal", () => {
  it("defaults to a soft link for media outside the workspace disk", async () => {
    const onSelectLocalMedia = vi.fn().mockResolvedValue({
      sourcePaths: ["\\\\nas\\videos\\lesson.mp4"],
      hardlinkAvailable: false,
    });
    const onImportLocalSeries = vi.fn().mockResolvedValue({ title: "课程", videos: [{}] });
    render(
      <WorkspaceImportModal
        onClose={vi.fn()}
        onSelectLocalMedia={onSelectLocalMedia}
        onImportLocalSeries={onImportLocalSeries}
      />,
    );

    fireEvent.change(screen.getByPlaceholderText("例如：Agent Frameworks"), {
      target: { value: "课程" },
    });
    fireEvent.click(screen.getByRole("button", { name: /未选择文件/ }));

    await screen.findByText("lesson.mp4");
    fireEvent.click(screen.getByRole("button", { name: "导入" }));

    expect(onImportLocalSeries).toHaveBeenCalledWith("课程", ["\\\\nas\\videos\\lesson.mp4"], "external_reference");
  });

  it("defaults to a hard link for media on the workspace disk", async () => {
    const onSelectLocalMedia = vi.fn().mockResolvedValue({
      sourcePaths: ["C:\\videos\\lesson.mp4"],
      hardlinkAvailable: true,
    });
    const onImportLocalSeries = vi.fn().mockResolvedValue({ title: "课程", videos: [{}] });
    render(
      <WorkspaceImportModal
        onClose={vi.fn()}
        onSelectLocalMedia={onSelectLocalMedia}
        onImportLocalSeries={onImportLocalSeries}
      />,
    );

    fireEvent.change(screen.getByPlaceholderText("例如：Agent Frameworks"), {
      target: { value: "课程" },
    });
    fireEvent.click(screen.getByRole("button", { name: /未选择文件/ }));

    await screen.findByText("lesson.mp4");
    fireEvent.click(screen.getByRole("button", { name: "导入" }));

    expect(onImportLocalSeries).toHaveBeenCalledWith("课程", ["C:\\videos\\lesson.mp4"], "hardlink");
  });
});
