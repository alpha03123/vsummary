import { test, expect } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";

const sourceRoot = "E:\\旧版VSummary";
const preview = {
  source_root: sourceRoot,
  found: { data: true, workspace: true, videos: true },
  series: [
    { name: "课程视频·复制", mode: "copy", effective_mode: "copy", media: [{}], external: [] },
    { name: "访谈素材·硬链接", mode: "hardlink", effective_mode: "hardlink", media: [{}], external: [] },
    { name: "外部资料·路径引用", mode: "external_reference", effective_mode: "external_reference", media: [], external: [{}] },
  ],
  data: [
    { name: "models", category: "copyable", bytes: 1_610_612_736 },
    { name: "agent_sessions", category: "sql", bytes: 15_360 },
    { name: "downloads", category: "rebuildable", bytes: 734_003_200 },
  ],
  total_videos: 3,
  copy_bytes: 367_001_600,
  target_free_bytes: 21_474_836_480,
  warnings: [],
};

test("migration update panel preview, progress, and completion", async ({ page }, testInfo) => {
  await page.setViewportSize({ width: 1600, height: 1700 });
  const screenshotDir = process.env.VSUMMARY_SCREENSHOT_DIR || testInfo.outputDir;
  fs.mkdirSync(screenshotDir, { recursive: true });
  let polls = 0;
  await page.route("**/api/**", async (route) => {
    const request = route.request();
    const pathname = new URL(request.url()).pathname;
    if (!pathname.startsWith("/api/")) return route.continue();
    const json = (payload) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(payload) });
    if (pathname === "/api/health") return json({ status: "ok" });
    if (pathname === "/api/videos") return json({ workspace: { id: "workspace-demo", title: "VSummary" }, series: [] });
    if (pathname === "/api/application-update") return json({ installation_kind: "source", current_version: "v.Source", update_available: false, can_apply: false, requires_full_package: false, message: "源码版" });
    if (pathname === "/api/settings") return json({});
    if (pathname === "/api/provider-settings") return json({ llm_provider: "openai", openai_base_url: "", openai_model: "gpt-5", has_openai_api_key: false, openai_api_key_masked: "", hf_endpoint: "" });
    if (pathname === "/api/provider-settings/usage") return json({ range: "7d", total: { prompt_tokens: 0, completion_tokens: 0, total_tokens: 0 }, by_category: [], by_provider: [], recent: [], timeline: [] });
    if (pathname === "/api/legacy-migration/latest") return json(null);
    if (pathname === "/api/legacy-migration/select-source") return json({ path: sourceRoot });
    if (pathname === "/api/legacy-migration/inspect") return json(preview);
    if (pathname === "/api/legacy-migration/runs" && request.method() === "POST") return json({ id: "run-demo", status: "ready", source_root: sourceRoot, manifest: preview, include_data: ["models"], total_videos: 3, verified_videos: 0, removed_videos: 0 });
    if (pathname === "/api/legacy-migration/runs/run-demo/start") return json({ id: "run-demo", status: "running", total_videos: 3, verified_videos: 1, removed_videos: 1 });
    if (pathname === "/api/legacy-migration/runs/run-demo") {
      polls += 1;
      return json({ id: "run-demo", status: polls > 1 ? "completed" : "running", total_videos: 3, verified_videos: polls > 1 ? 3 : 2, removed_videos: polls > 1 ? 2 : 1 });
    }
    if (pathname.startsWith("/api/asr/") || pathname === "/api/rag/models") return json([]);
    return json({});
  });

  await page.goto("/");
  await page.getByRole("button", { name: "打开界面设置" }).click();
  await page.getByRole("button", { name: "应用更新" }).click();
  const panel = page.getByTestId("legacy-migration-panel");
  await expect(panel).toBeVisible();
  await panel.getByRole("button", { name: "选择旧版目录" }).click();
  await expect(panel).toContainText("课程视频·复制");
  await expect(panel).toContainText("访谈素材·硬链接");
  await expect(panel).toContainText("外部资料·路径引用");
  await panel.screenshot({ path: path.join(screenshotDir, "vsummary-migration-native-preview.png") });

  await panel.getByRole("button", { name: /我了解/ }).click();
  await panel.getByRole("button", { name: "开始迁移" }).click();
  await expect(page.getByTestId("legacy-migration-status")).toContainText("迁移中");
  await panel.screenshot({ path: path.join(screenshotDir, "vsummary-migration-native-running.png") });
  await expect(page.getByTestId("legacy-migration-status")).toContainText("已完成", { timeout: 5000 });
  await panel.screenshot({ path: path.join(screenshotDir, "vsummary-migration-native-completed.png") });
});
