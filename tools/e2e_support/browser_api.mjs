const terminalStatuses = new Set(["succeeded", "failed", "cancelled"]);

export class LocalBrowserApi {
  constructor(apiUrl) {
    this.apiUrl = apiUrl.replace(/\/$/, "");
  }

  async json(path, action, options) {
    const response = await fetch(`${this.apiUrl}${path}`, options);
    if (!response.ok) throw new Error(`${action} failed with HTTP ${response.status}: ${await response.text()}`);
    const payload = await response.json();
    if (!payload || typeof payload !== "object") throw new Error(`${action} returned a non-object JSON payload.`);
    return payload;
  }

  library() { return this.json("/videos", "load library"); }
  job(jobId) { return this.json(`/jobs/${encodeURIComponent(jobId)}`, "read durable job"); }
  generationStatus(seriesId, videoId) { return this.json(`/videos/${encodeURIComponent(seriesId)}/${encodeURIComponent(videoId)}/generate/status`, "read generation status"); }

  async importLocalSeries(title, sourcePath) {
    return this.json("/import/local/series/from-paths", "import test media", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ series_title: title, source_paths: [sourcePath], storage_mode: "copy" }),
    });
  }

  async cancelSeriesGeneration(seriesId) {
    return fetch(`${this.apiUrl}/series/${encodeURIComponent(seriesId)}/generate/cancel`, { method: "POST" });
  }

  async cancelVideoGeneration(seriesId, videoId) {
    return fetch(`${this.apiUrl}/videos/${encodeURIComponent(seriesId)}/${encodeURIComponent(videoId)}/generate/cancel`, { method: "POST" });
  }

  async deleteSeries(seriesId) {
    return fetch(`${this.apiUrl}/series/${encodeURIComponent(seriesId)}`, { method: "DELETE" });
  }

  async waitForJob(jobId, { timeoutMs = 300_000, requireSuccess = true } = {}) {
    const deadline = Date.now() + timeoutMs;
    let latest;
    while (Date.now() < deadline) {
      latest = await this.job(jobId);
      if (terminalStatuses.has(latest.status)) {
        if (requireSuccess && latest.status !== "succeeded") throw new Error(`Job did not succeed: ${JSON.stringify(latest)}`);
        return latest;
      }
      await sleep(500);
    }
    throw new Error(`Job timed out after ${timeoutMs / 1_000}s: ${JSON.stringify(latest)}`);
  }
}

export class TemporarySeriesScope {
  constructor(api) {
    this.api = api;
    this.seriesId = null;
    this.videoId = null;
    this.jobIds = [];
  }

  trackSeries(seriesId, videoId) {
    this.seriesId = seriesId;
    this.videoId = videoId;
  }

  trackJob(jobId) {
    if (!jobId) throw new Error("Job submission did not return job_id.");
    this.jobIds.push(jobId);
    return jobId;
  }

  async cleanup() {
    if (!this.seriesId) return;
    let cancellation = await this.api.cancelSeriesGeneration(this.seriesId);
    if (cancellation.status === 404 && this.videoId) {
      cancellation = await this.api.cancelVideoGeneration(this.seriesId, this.videoId);
    }
    if (!cancellation.ok && cancellation.status !== 404) {
      throw new Error(`cancel E2E series generation failed with HTTP ${cancellation.status}: ${await cancellation.text()}`);
    }
    for (const jobId of this.jobIds) await this.api.waitForJob(jobId, { timeoutMs: 60_000, requireSuccess: false });
    const deadline = Date.now() + 60_000;
    while (true) {
      const deletion = await this.api.deleteSeries(this.seriesId);
      if (deletion.ok) {
        const library = await this.api.library();
        if (!library.series?.some((series) => series.id === this.seriesId)) return;
        throw new Error(`Temporary browser E2E series remains: ${this.seriesId}`);
      }
      if (deletion.status !== 409 || Date.now() >= deadline) {
        throw new Error(`delete temporary browser E2E series failed with HTTP ${deletion.status}: ${await deletion.text()}`);
      }
      await sleep(500);
    }
  }
}

function sleep(milliseconds) {
  return new Promise((resolve) => setTimeout(resolve, milliseconds));
}
