// src/frontend/src/features/workspace/ui/mindmapSVGExport.js
import * as d3 from "d3";

const EXPORT_PADDING = 60;

/**
 * Export the full markmap as an SVG, sized to the natural content bounds
 * (not the user's current pan/zoom). Strategy:
 *
 *   1. Save the live d3-zoom transform from the SVG node's `__zoom` property.
 *   2. Clone the live SVG. The clone is mutated, the live SVG is not.
 *   3. On the clone: set `width` / `height` / `viewBox` to
 *      `state.rect + 60px padding` so the entire content renders at 1:1.
 *   4. On the clone: remove the `transform` attribute on the inner <g> so the
 *      content is positioned in the new viewBox, not by the user's pan/zoom.
 *   5. Serialize the clone to a string, wrap in a Blob with `image/svg+xml`,
 *      trigger a download via a temporary <a download> click, revoke the blob URL.
 *   6. Restore the live SVG's d3-zoom transform in `finally` (defensive — the
 *      live SVG was never mutated, so this is a no-op safety net in case a
 *      future change accidentally writes to the live node).
 *
 * The user's pan/zoom is preserved: the live SVG's `__zoom` is restored to
 * the same value it had at the start, even on error.
 *
 * Why SVG and not PNG? Markmap renders text in `<foreignObject>` elements. When
 * an SVG with foreignObject is loaded into an <img> and rasterized to canvas,
 * the browser taints the canvas (HTML spec, security boundary). Once tainted,
 * `canvas.toDataURL()` throws SecurityError. SVG export sidesteps this entirely:
 * there is no canvas, no rasterization, no taint. The SVG is just a text file
 * with the full mindmap (including its `<style>` and `<foreignObject>`) intact.
 *
 * @param {object} mm        Markmap instance from `Markmap.create(...)`.
 * @param {string} filename  Download filename, including the `.svg` extension.
 * @returns {Promise<void>}  Resolves once the download has been triggered.
 */
export async function exportMindmapAsSVG(mm, filename) {
  if (!mm || typeof mm.svg !== "object") {
    throw new Error("exportMindmapAsSVG: a markmap instance is required");
  }

  const svgNode = mm.svg.node();
  if (!svgNode) {
    throw new Error("exportMindmapAsSVG: markmap has no SVG node attached");
  }

  // d3-zoom stores the live transform on the SVG node's `__zoom` property.
  const originalTransform = d3.zoomTransform(svgNode);

  try {
    const { x1, x2, y1, y2 } = mm.state.rect;
    const contentWidth = x2 - x1;
    const contentHeight = y2 - y1;
    if (contentWidth <= 0 || contentHeight <= 0) {
      throw new Error(
        "exportMindmapAsSVG: markmap state.rect is empty — wait for the first render",
      );
    }

    const paddedWidth = contentWidth + EXPORT_PADDING * 2;
    const paddedHeight = contentHeight + EXPORT_PADDING * 2;

    // Clone the live SVG so the user's view is not modified by the export.
    const clone = svgNode.cloneNode(true);
    clone.setAttribute("width", String(paddedWidth));
    clone.setAttribute("height", String(paddedHeight));
    clone.setAttribute(
      "viewBox",
      `${x1 - EXPORT_PADDING} ${y1 - EXPORT_PADDING} ${paddedWidth} ${paddedHeight}`,
    );
    // Remove d3-zoom's transform on the inner <g> so the content renders at
    // 1:1 in the new viewBox, not at the user's current pan/zoom.
    const innerG = clone.querySelector("g");
    if (innerG) innerG.removeAttribute("transform");

    const svgData = new XMLSerializer().serializeToString(clone);
    const blob = new Blob([svgData], { type: "image/svg+xml;charset=utf-8" });
    const url = URL.createObjectURL(blob);

    try {
      triggerDownload(url, filename);
    } finally {
      URL.revokeObjectURL(url);
    }
  } finally {
    // Restore the user's view. The live SVG was never mutated in this design,
    // so this is a defensive no-op for now; it guards against future changes
    // that might accidentally write to the live node.
    try {
      mm.svg.call(mm.zoom.transform, originalTransform);
    } catch {
      // Swallow restoration errors: the export itself has already failed
      // and surfacing a second error would mask the original cause.
    }
  }
}

function triggerDownload(href, filename) {
  const a = document.createElement("a");
  a.download = filename;
  a.href = href;
  a.click();
}
