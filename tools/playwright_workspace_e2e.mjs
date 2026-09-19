/**
 * 连接已由 start.bat 启动的真实前后端，验证用户能进入已有概括的视频工作区。
 *
 * 用法：node tools/playwright_workspace_e2e.mjs [frontend URL]
 * 默认地址为 http://127.0.0.1:4173。
 */

import { createRequire } from "node:module";

const frontendUrl = process.argv[2] ?? "http://127.0.0.1:4173";
const frontendRoot = new URL("../src/frontend/package.json", import.meta.url);
const require = createRequire(frontendRoot);
const { chromium } = require("playwright");

const apiUrl = new URL("/api/videos", frontendUrl);
const libraryResponse = await fetch(apiUrl);
if (!libraryResponse.ok) {
  throw new Error(`Backend library request failed: HTTP ${libraryResponse.status}`);
}
const library = await libraryResponse.json();
const processedVideos = library.series
  ?.flatMap((series) => series.videos.map((video) => ({ series, video })))
  .filter(({ video }) => video.processed) ?? [];
const selected = processedVideos.find(({ series }) => series.title !== "Playground") ?? processedVideos[0];
if (!selected) {
  throw new Error("No processed video is available for the browser workspace check.");
}

const browser = await chromium.launch({
  headless: true,
  executablePath: process.env.VSUMMARY_E2E_CHROME ?? "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
});
const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
try {
  await page.goto(frontendUrl, { waitUntil: "networkidle", timeout: 30_000 });
  if (selected.series.title !== "Playground") {
    await page.getByRole("button", { name: selected.series.title }).first().click();
  }
  await page.getByRole("button", { name: new RegExp(selected.video.title.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")) }).first().click();
  await page.getByText(selected.video.title, { exact: true }).first().waitFor({ timeout: 15_000 });
  await page.getByText("AI 概括", { exact: true }).first().waitFor({ timeout: 15_000 });

  const visibleText = await page.locator("body").innerText();
  if (!visibleText.includes(selected.video.title) || !visibleText.includes("AI 概括")) {
    throw new Error("Workspace did not render the selected SQL-backed video and its summary panel.");
  }
  console.log(JSON.stringify({
    series: selected.series.title,
    video: selected.video.title,
    workspaceLoaded: true,
  }, null, 2));
} finally {
  await browser.close();
}
