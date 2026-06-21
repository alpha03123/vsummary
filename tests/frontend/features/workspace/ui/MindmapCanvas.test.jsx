import { describe, it, expect, vi } from "vitest";
import { render } from "@testing-library/react";

// Mock markmap before importing the component
vi.mock("markmap-view", () => ({
  Markmap: {
    create: vi.fn(() => ({
      destroy: vi.fn(),
      svg: { node: vi.fn(() => ({ classList: { add: vi.fn(), remove: vi.fn() } })) },
    })),
  },
}));
vi.mock("markmap-toolbar", () => ({
  Toolbar: {
    create: vi.fn(() => ({ el: document.createElement("div") })),
  },
}));
vi.mock("d3", () => ({
  select: vi.fn(() => ({
    on: vi.fn(),
    datum: vi.fn(),
    node: vi.fn(() => ({ classList: { add: vi.fn(), remove: vi.fn() } })),
  })),
}));

import { MindmapCanvas } from "@src/features/workspace/ui/MindmapCanvas";
import { Markmap } from "markmap-view";
import { Toolbar } from "markmap-toolbar";

const fakeRoot = {
  id: "root", title: "测试导图", summary: "",
  start_seconds: 0, end_seconds: 0,
  children: [
    { id: "c1", title: "子节点1", summary: "", start_seconds: 0, end_seconds: 0, children: [] },
  ],
};

describe("MindmapCanvas — markmap integration", () => {
  beforeEach(() => { vi.clearAllMocks(); });

  it("renders SVG when root is provided", () => {
    const { container } = render(
      <MindmapCanvas root={fakeRoot} selectedNodeId={null} onSelectNode={vi.fn()} />
    );
    expect(container.querySelector("svg")).toBeTruthy();
    expect(Markmap.create).toHaveBeenCalledTimes(1);
    expect(Toolbar.create).toHaveBeenCalledTimes(1);
  });

  it("renders nothing when root is null", () => {
    const { container } = render(
      <MindmapCanvas root={null} selectedNodeId={null} onSelectNode={vi.fn()} />
    );
    expect(container.querySelector("svg")).toBeNull();
    expect(Markmap.create).not.toHaveBeenCalled();
  });

  it("destroys and recreates markmap when root changes", () => {
    const destroy = vi.fn();
    Markmap.create.mockReturnValue({
      destroy,
      svg: { node: vi.fn(() => ({ classList: { add: vi.fn(), remove: vi.fn() } })) },
    });

    const { rerender } = render(
      <MindmapCanvas root={fakeRoot} selectedNodeId={null} onSelectNode={vi.fn()} />
    );
    expect(Markmap.create).toHaveBeenCalledTimes(1);

    rerender(
      <MindmapCanvas root={{ ...fakeRoot, title: "新导图" }} selectedNodeId={null} onSelectNode={vi.fn()} />
    );
    expect(destroy).toHaveBeenCalled();
    expect(Markmap.create).toHaveBeenCalledTimes(2);
  });

  it("attaches toolbar when root is provided", () => {
    const toolbarEl = document.createElement("div");
    Toolbar.create.mockReturnValue({ el: toolbarEl });

    const { container } = render(
      <div>
        <MindmapCanvas root={fakeRoot} selectedNodeId={null} onSelectNode={vi.fn()} />
      </div>
    );
    expect(Toolbar.create).toHaveBeenCalledTimes(1);
  });
});
