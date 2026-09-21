/**
 * 真实浏览器生成 E2E。
 *
 * 从当前库复制一个可读取的本地视频到临时系列，通过真实浏览器点击“生成 AI 概况”。
 * 它刻意延迟选中视频时的旧 generate/status=idle 回包，验证该旧回包不会覆盖刚提交的
 * 持久 Job。整个流程使用真实下载后的媒体、ASR、LLM、Job Worker 与 SSE；没有模拟
 * 生成器或模拟接口。无论成功失败，临时系列和复制的媒体均在 finally 中清理。
 *
 * 用法：node tools/real_llm_browser_e2e.mjs [frontend URL]
 * 默认 frontend URL：http://127.0.0.1:4173
 */

import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";
import { mkdir, mkdtemp, rm, writeFile } from "node:fs/promises";
import { createWriteStream } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { Readable } from "node:stream";
import { pipeline } from "node:stream/promises";
import { LocalBrowserApi, TemporarySeriesScope } from "./e2e_support/browser_api.mjs";

const frontendUrl = (process.argv[2] ?? "http://127.0.0.1:4173").replace(/\/$/, "");
const apiUrl = new URL("/api/", frontendUrl).toString().replace(/\/$/, "");
const api = new LocalBrowserApi(apiUrl);
const root = resolve(fileURLToPath(new URL("..", import.meta.url)));
const reportDirectory = join(root, "temp", "real-llm-browser-e2e");
const reportPath = join(reportDirectory, "latest.json");
const frontendRoot = new URL("../src/frontend/package.json", import.meta.url);
const require = createRequire(frontendRoot);
const { chromium } = require("playwright");

const chromePath = process.env.VSUMMARY_E2E_CHROME ?? "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe";

let browser;
let temporaryDirectory;
let temporarySeriesId;
let testVideoId;
const resources = new TemporarySeriesScope(api);
let capturedStatusRouteRelease;
let primaryError;
let resultReport;
let phase = "initializing";
const browserConsoleErrors = [];

try {
  await mkdir(reportDirectory, { recursive: true });
  temporaryDirectory = await mkdtemp(join(reportDirectory, "run-"));

  phase = "loading source library";
  const library = await api.library();
  const source = selectSourceVideo(library);
  const sourcePath = join(temporaryDirectory, "source.mp4");
  phase = "copying source media";
  await copyPreview(source.series.id, source.video.id, sourcePath);

  phase = "importing temporary series";
  const imported = await api.importLocalSeries(`E2E Browser Real LLM ${new Date().toISOString().replace(/[:.]/g, "-")}`, sourcePath);
  temporarySeriesId = imported.id;
  testVideoId = imported.videos?.[0]?.id;
  if (typeof temporarySeriesId !== "string" || typeof testVideoId !== "string") {
    throw new Error("Temporary series import did not return one video.");
  }
  resources.trackSeries(temporarySeriesId, testVideoId);

  phase = "launching browser";
  browser = await chromium.launch({ headless: true, executablePath: chromePath });
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
  page.on("console", (message) => {
    if (message.type() === "error") {
      browserConsoleErrors.push(message.text());
    }
  });
  const oldStatusCaptured = deferred();
  const releaseOldStatus = deferred();
  capturedStatusRouteRelease = releaseOldStatus.resolve;
  const generationStatusPath = `/api/videos/${temporarySeriesId}/${testVideoId}/generate/status`;
  let delayedStatusRequestCount = 0;

  await page.route(`**${generationStatusPath}`, async (route) => {
    delayedStatusRequestCount += 1;
    if (delayedStatusRequestCount !== 1) {
      await route.continue();
      return;
    }
    oldStatusCaptured.resolve();
    await releaseOldStatus.promise;
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        task_id: `${temporarySeriesId}/${testVideoId}`,
        snapshot: { status: "idle", stage: "idle", progress: 0, detail: null, error: null },
      }),
    });
  });

  phase = "opening workspace";
  await page.goto(frontendUrl, { waitUntil: "networkidle", timeout: 30_000 });
  phase = "selecting temporary series";
  await page.getByRole("button", { name: `打开系列 ${imported.title}`, exact: true }).click();
  phase = "selecting temporary video";
  await page.getByRole("button", { name: new RegExp(escapeRegExp(imported.videos[0].title)) }).first().click();
  phase = "waiting for prior idle status";
  await withTimeout(oldStatusCaptured.promise, 15_000, "The selected video did not request generation status.");

  const eventsRequest = page.waitForRequest((request) => request.url().includes(`/api/jobs/`) && request.url().endsWith("/events"));
  const submittedResponse = page.waitForResponse((response) => (
    response.url().includes(`/api/videos/${temporarySeriesId}/${testVideoId}/generate`)
    && response.request().method() === "POST"
  ));
  phase = "submitting generation from browser";
  await page.getByRole("button", { name: "生成 AI 概况", exact: true }).click();
  await page.getByText("正在生成 AI 概况", { exact: true }).waitFor({ timeout: 15_000 });
  const submission = await (await submittedResponse).json();
  if (!submission?.job_id || !["queued", "running", "retrying"].includes(submission.status)) {
    throw new Error(`Generation submission did not return a durable active job: ${JSON.stringify(submission)}`);
  }
  resources.trackJob(submission.job_id);

  releaseOldStatus.resolve();
  const eventsRequestUrl = (await withTimeout(eventsRequest, 20_000, "The browser did not subscribe to the durable job event stream.")).url();
  if (!eventsRequestUrl.includes(`/api/jobs/${submission.job_id}/events`)) {
    throw new Error(`The browser subscribed to the wrong durable event stream: ${eventsRequestUrl}`);
  }

  await page.waitForTimeout(1_200);
  if (!await page.getByText("正在生成 AI 概况", { exact: true }).isVisible()) {
    throw new Error("The generation overlay disappeared after the delayed idle status response.");
  }
  if (!await page.getByRole("button", { name: "取消本次生成", exact: true }).isVisible()) {
    throw new Error("The selected video's generate control was not kept in its active state.");
  }

  const duplicateSubmission = await page.evaluate(async ({ seriesId, videoId }) => {
    const response = await fetch(`/api/videos/${seriesId}/${videoId}/generate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ processing_mode: "summary" }),
    });
    return { status: response.status, payload: await response.json() };
  }, { seriesId: temporarySeriesId, videoId: testVideoId });
  if (duplicateSubmission.status !== 202 || duplicateSubmission.payload?.job_id !== submission.job_id) {
    throw new Error(`Repeated generation did not reuse the active job: ${JSON.stringify(duplicateSubmission)}`);
  }

  phase = "waiting for real generation";
  const completedJob = await api.waitForJob(submission.job_id);
  if (completedJob.status !== "succeeded") {
    throw new Error(`Real browser generation job did not succeed: ${JSON.stringify(completedJob)}`);
  }
  await page.getByRole("button", { name: "重新生成 AI 概况", exact: true }).waitFor({ timeout: 30_000 });
  await page.getByText("正在生成 AI 概况", { exact: true }).waitFor({ state: "hidden", timeout: 30_000 });

  phase = "verifying published browser results";
  const [summary, tools] = await Promise.all([
    api.json(`/videos/${temporarySeriesId}/${testVideoId}/summary`, "read generated summary"),
    api.json(`/videos/${temporarySeriesId}/${testVideoId}/tools`, "read generated tool state"),
  ]);
  if (!summary.chapters?.length || !tools.overview?.generated) {
    throw new Error("The completed browser generation did not publish a readable summary artifact.");
  }

  resultReport = {
    source_series_id: source.series.id,
    source_video_id: source.video.id,
    test_series_id: temporarySeriesId,
    test_video_id: testVideoId,
    job_id: submission.job_id,
    delayed_idle_status_request_count: delayedStatusRequestCount,
    duplicate_submission_reused_job: true,
    durable_event_stream_observed: true,
    summary_chapter_count: summary.chapters.length,
    browser_overlay_survived_stale_idle: true,
    browser_rendered_completed_state: true,
  };
} catch (error) {
  primaryError = error;
} finally {
  capturedStatusRouteRelease?.();
  await browser?.close();
  let cleanupError;
  try {
    if (temporarySeriesId) {
      await resources.cleanup();
    }
    if (temporaryDirectory) {
      await rm(temporaryDirectory, { recursive: true, force: true });
    }
  } catch (error) {
    cleanupError = error;
  }
  if (primaryError) {
    await mkdir(reportDirectory, { recursive: true });
    await writeFile(reportPath, `${JSON.stringify({
      status: "failed",
      phase,
      error: primaryError.message,
      browser_console_errors: browserConsoleErrors,
      cleanup: cleanupError ? `failed: ${cleanupError.message}` : "deleted",
    }, null, 2)}\n`, "utf8");
  } else if (!cleanupError && resultReport) {
    await writeFile(reportPath, `${JSON.stringify({ ...resultReport, cleanup: "deleted" }, null, 2)}\n`, "utf8");
    console.log(JSON.stringify({ ...resultReport, cleanup: "deleted" }, null, 2));
  }
  if (primaryError || cleanupError) {
    throw new Error(
      primaryError
        ? `Real browser E2E failed: ${primaryError.message}${cleanupError ? `; cleanup also failed: ${cleanupError.message}` : ""}`
        : `Real browser E2E cleanup failed: ${cleanupError.message}`,
      { cause: primaryError ?? cleanupError },
    );
  }
}

function selectSourceVideo(library) {
  for (const series of library.series ?? []) {
    for (const video of series.videos ?? []) {
      if (video.is_linked !== true && video.status !== "source_missing") {
        return { series, video };
      }
    }
  }
  throw new Error("No locally available library video can be used for the real browser E2E.");
}

async function copyPreview(seriesId, videoId, targetPath) {
  const response = await fetch(`${apiUrl}/videos/${seriesId}/${videoId}/preview`);
  await requireSuccess(response, "copy source video preview");
  if (!response.body) {
    throw new Error("Source preview response has no body.");
  }
  await pipeline(Readable.fromWeb(response.body), createWriteStream(targetPath));
}

async function requireSuccess(response, action) {
  if (response.ok) {
    return response;
  }
  throw new Error(`${action} failed with HTTP ${response.status}: ${await response.text()}`);
}


function deferred() {
  let resolve;
  const promise = new Promise((resolvePromise) => {
    resolve = resolvePromise;
  });
  return { promise, resolve };
}

async function withTimeout(promise, milliseconds, message) {
  let timeoutId;
  try {
    return await Promise.race([
      promise,
      new Promise((_, reject) => {
        timeoutId = setTimeout(() => reject(new Error(message)), milliseconds);
      }),
    ]);
  } finally {
    clearTimeout(timeoutId);
  }
}

function escapeRegExp(value) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}
