import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { WorkspacePreviewView } from "@src/features/workspace/ui/views/WorkspacePreviewView";

describe("WorkspacePreviewView", () => {
  it("shows an unavailable preview message for audio files", () => {
    render(<WorkspacePreviewView previewSource="/api/videos/series-1/audio-1/preview" previewSourceType="audio" />);

    expect(screen.getByText("音频文件暂不支持预览")).toBeInTheDocument();
    expect(screen.queryByRole("video")).toBeNull();
  });
});
