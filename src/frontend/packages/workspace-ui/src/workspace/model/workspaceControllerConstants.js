export const PLAYGROUND_SERIES_ID = "__playground__";
export const BACKEND_HEALTH_RETRY_DELAY_MS = 1000;
export const BILIBILI_INBOX_KIND = "bilibili_inbox";

export function isPlaygroundSeries(series) {
  return series?.kind === "playground" || series?.id === PLAYGROUND_SERIES_ID;
}

export function isBilibiliInboxSeries(series) {
  return series?.kind === BILIBILI_INBOX_KIND;
}

export function isSpecialSeries(series) {
  return isPlaygroundSeries(series) || isBilibiliInboxSeries(series);
}
