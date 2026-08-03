import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { WorkspaceImportModal } from "@src/features/workspace/ui/WorkspaceImportModal";

describe("WorkspaceImportModal", () => {
  it("uploads files dropped onto the local media zone", async () => {
    const onUploadLocalSeries = vi.fn().mockResolvedValue({ title: "课程", videos: [{}] });
    render(
      <WorkspaceImportModal
        onClose={vi.fn()}
        onUploadLocalSeries={onUploadLocalSeries}
        onUploadSeriesVideos={vi.fn()}
        onUploadLocalPlaygroundVideos={vi.fn()}
      />,
    );

    fireEvent.change(screen.getByPlaceholderText("例如：Agent Frameworks"), {
      target: { value: "课程" },
    });
    const dropZone = screen.getByText("未选择文件").closest("button");
    const file = new File(["video"], "lesson.mp4", { type: "video/mp4" });
    fireEvent.drop(dropZone, {
      dataTransfer: { files: [file], types: ["Files"] },
    });

    expect(screen.getByText("lesson.mp4")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "导入" }));

    expect(onUploadLocalSeries).toHaveBeenCalledWith("课程", [file]);
  });
});
