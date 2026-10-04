// tests/frontend/features/workspace/ui/mindmapSVGExport.test.js
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

import { exportMindmapAsSVG } from "@workspace/workspace/ui/mindmapSVGExport";

function makeMarkmapMock({
  currentTransform = { k: 1, x: 0, y: 0 },
  contentRect = { x1: 0, x2: 2000, y1: 0, y2: 1500 },
} = {}) {
  // Real jsdom SVG so cloneNode / setAttribute / getAttribute work as in the browser.
  const svgNode = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svgNode.setAttribute("class", "mindmap-svg");
  // Markmap's d3-zoom wraps the content in an inner <g> with a transform attribute.
  // Simulate that so T4 can verify the transform is removed from the clone.
  const innerG = document.createElementNS("http://www.w3.org/2000/svg", "g");
  innerG.setAttribute("transform", "translate(0,0) scale(1)");
  svgNode.appendChild(innerG);
  // d3-zoom stores the transform on the SVG node's __zoom property.
  Object.defineProperty(svgNode, "__zoom", {
    value: currentTransform,
    writable: true,
    configurable: true,
  });

  const transformCalls = [];
  const call = vi.fn((sel, transform) => {
    transformCalls.push(transform);
    if (transform && typeof transform === "object" && "k" in transform) {
      Object.defineProperty(svgNode, "__zoom", { value: transform, writable: true, configurable: true });
    }
    return sel;
  });

  const fit = vi.fn(() => Promise.resolve());
  const mm = {
    fit,
    svg: { node: vi.fn(() => svgNode), call },
    zoom: { transform: "TRANSFORM_OP" }, // sentinel; d3-zoom.transform is a function, but the mock only
                                         // uses it as a tag inside `mm.svg.call(mm.zoom.transform, t)`.
    state: { rect: contentRect },
  };
  return { mm, svgNode, fit, call, transformCalls };
}

describe("exportMindmapAsSVG", () => {
  beforeEach(() => {
    if (!globalThis.URL.createObjectURL) {
      globalThis.URL.createObjectURL = vi.fn(() => "blob:test");
      globalThis.URL.revokeObjectURL = vi.fn();
    }
  });

  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it("exports the full content bounds independently of the visible viewport", async () => {
    // content bounds: 2000 wide x 1500 tall; clientWidth is intentionally different
    // so the test fails if the implementation regresses to using clientWidth.
    const contentRect = { x1: 100, x2: 2100, y1: 50, y2: 1550 };
    const { mm, svgNode } = makeMarkmapMock({ contentRect });
    Object.defineProperty(svgNode, "clientWidth", { value: 800, configurable: true });
    Object.defineProperty(svgNode, "clientHeight", { value: 600, configurable: true });

    let capturedClone = null;
    const origCloneNode = svgNode.cloneNode;
    svgNode.cloneNode = vi.fn((deep) => {
      const clone = origCloneNode.call(svgNode, deep);
      capturedClone = clone;
      return clone;
    });

    await exportMindmapAsSVG(mm, "out.svg");

    // (2100 - 100 + 60 * 2) = 2120, (1550 - 50 + 60 * 2) = 1620
    expect(capturedClone).not.toBeNull();
    expect(capturedClone.getAttribute("width")).toBe("2120");
    expect(capturedClone.getAttribute("height")).toBe("1620");
    expect(capturedClone.getAttribute("viewBox")).toBe("40 -10 2120 1620");
    // The inner <g> had d3-zoom's transform; the clone must have it removed.
    const innerG = capturedClone.querySelector("g");
    expect(innerG.hasAttribute("transform")).toBe(false);

    svgNode.cloneNode = origCloneNode;
  });

  it("downloads the exported SVG with the requested filename", async () => {
    const { mm } = makeMarkmapMock();
    const downloadCalls = [];
    const origCreate = document.createElement.bind(document);
    const createSpy = vi.spyOn(document, "createElement").mockImplementation((tag) => {
      const el = origCreate(tag);
      if (tag === "a") {
        el.click = vi.fn(() => {
          downloadCalls.push({ download: el.download, href: el.href });
        });
      }
      return el;
    });

    await exportMindmapAsSVG(mm, "my-mindmap.svg");

    expect(downloadCalls).toHaveLength(1);
    expect(downloadCalls[0].download).toBe("my-mindmap.svg");
    expect(downloadCalls[0].href.startsWith("blob:")).toBe(true);

    createSpy.mockRestore();
  });

  it.each([false, true])("preserves the live SVG and zoom when export fails: %s", async (fails) => {
    const transform = { k: 2.5, x: 100, y: 200 };
    const { mm, svgNode } = makeMarkmapMock({ currentTransform: transform });
    // Set distinctive attributes on the live SVG to detect any mutation.
    svgNode.setAttribute("width", "100%");
    svgNode.setAttribute("height", "100%");
    const liveWidthBefore = svgNode.getAttribute("width");
    const liveHeightBefore = svgNode.getAttribute("height");
    const liveViewBoxBefore = svgNode.getAttribute("viewBox");
    const liveContentBefore = svgNode.innerHTML;

    if (fails) {
      vi.stubGlobal("Blob", class { constructor() { throw new Error("Export failed"); } });
      await expect(exportMindmapAsSVG(mm, "test.svg")).rejects.toThrow("Export failed");
    } else {
      await exportMindmapAsSVG(mm, "test.svg");
    }

    expect(svgNode.getAttribute("width")).toBe(liveWidthBefore);
    expect(svgNode.getAttribute("height")).toBe(liveHeightBefore);
    expect(svgNode.getAttribute("viewBox")).toBe(liveViewBoxBefore);
    expect(svgNode.innerHTML).toBe(liveContentBefore);
    expect(svgNode.__zoom).toMatchObject(transform);
  });

  it("rejects an export before the mindmap content has rendered", async () => {
    const { mm } = makeMarkmapMock({ contentRect: { x1: 0, x2: 0, y1: 0, y2: 0 } });

    await expect(exportMindmapAsSVG(mm, "out.svg")).rejects.toThrow(/state\.rect is empty/);
  });

  it("keeps the styling required to read the SVG outside the application", async () => {
    const { mm, svgNode } = makeMarkmapMock();
    // Markmap adds a <style> element to the live SVG; simulate that.
    const styleEl = document.createElementNS("http://www.w3.org/2000/svg", "style");
    styleEl.textContent = ".markmap-node { fill: #333; }";
    svgNode.appendChild(styleEl);

    let capturedClone = null;
    const origCloneNode = svgNode.cloneNode;
    svgNode.cloneNode = vi.fn((deep) => {
      const clone = origCloneNode.call(svgNode, deep);
      capturedClone = clone;
      return clone;
    });

    await exportMindmapAsSVG(mm, "out.svg");

    expect(capturedClone).not.toBeNull();
    expect(capturedClone.querySelector("style")).not.toBeNull();
    expect(capturedClone.querySelector("style").textContent).toContain("markmap-node");

    svgNode.cloneNode = origCloneNode;
  });
});
