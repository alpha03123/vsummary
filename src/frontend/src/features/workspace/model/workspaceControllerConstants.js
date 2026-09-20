export const PLAYGROUND_SERIES_ID = "__playground__";
export const BACKEND_HEALTH_RETRY_DELAY_MS = 1000;

export function isPlaygroundSeries(series) {
  return series?.kind === "playground" || series?.id === PLAYGROUND_SERIES_ID;
}
