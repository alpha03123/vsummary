// tests/e2e/mindmap-export.spec.js
import { test, expect } from "@playwright/test";
import { readFile } from "node:fs/promises";

test.describe("Mindmap SVG export (e2e)", () => {
  test("T13: clicking 导出 SVG downloads a well-formed SVG with foreignObject, style, and viewBox; inner <g> has no transform", async ({ page }) => {
    await page.goto("/tests/e2e/fixtures/mindmap-export.html");
    // Wait for the export button to be enabled (the fixture sets it up after a 200ms setTimeout).
    await page.waitForFunction(() => {
      const btn = document.getElementById("export-svg");
      return btn && !btn.disabled;
    });

    // Capture the download triggered by clicking the button.
    const [download] = await Promise.all([
      page.waitForEvent("download"),
      page.click("#export-svg"),
    ]);

    expect(download.suggestedFilename()).toBe("e2e-test.svg");

    // Read the downloaded file from the temp dir Playwright assigned.
    const downloadedPath = await download.path();
    const svg = await readFile(downloadedPath, "utf-8");

    // SVG well-formedness: starts with XML or svg tag.
    expect(svg).toMatch(/^<\?xml|<svg/);

    // Has a viewBox attribute (the export sets it to state.rect + padding).
    expect(svg).toMatch(/<svg[^>]*\sviewBox=/);

    // Width and height are set explicitly (not "auto" / percentage).
    expect(svg).toMatch(/<svg[^>]*\swidth="\d+"/);
    expect(svg).toMatch(/<svg[^>]*\sheight="\d+"/);

    // The markmap <style> element is preserved (so the SVG renders styled in external viewers).
    expect(svg).toMatch(/<style/);

    // The markmap <foreignObject> text rendering is preserved (the original PNG bug would have
    // lost this — the test would have failed at toDataURL. SVG has no such issue.).
    expect(svg).toMatch(/<foreignObject/);

    // The inner <g> has NO transform attribute (d3-zoom's transform was stripped from the clone).
    // A <g> with transform="..." would mean the export captured the live (panned/zoomed) view.
    const innerGMatch = svg.match(/<g[^>]*>/);
    expect(innerGMatch).not.toBeNull();
    const innerGTag = innerGMatch[0];
    expect(innerGTag).not.toMatch(/transform=/);
  });

  test("T14: dark-mode class on the live SVG is preserved in the downloaded SVG", async ({ page }) => {
    await page.goto("/tests/e2e/fixtures/mindmap-export.html");
    // The fixture's markmap does NOT set markmap-dark by default; we set it manually before export.
    await page.waitForFunction(() => {
      const btn = document.getElementById("export-svg");
      return btn && !btn.disabled;
    });
    await page.evaluate(() => {
      const svg = document.getElementById("mindmap");
      svg.setAttribute("class", (svg.getAttribute("class") || "") + " markmap-dark");
    });

    const [download] = await Promise.all([
      page.waitForEvent("download"),
      page.click("#export-svg"),
    ]);

    const downloadedPath = await download.path();
    const svg = await readFile(downloadedPath, "utf-8");

    // The cloned <svg> retains the markmap-dark class.
    expect(svg).toMatch(/<svg[^>]*\sclass="[^"]*markmap-dark/);
  });
});
