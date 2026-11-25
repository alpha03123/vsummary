// Which VSummary the side panel opens: the cloud site or a copy running on this computer.
export const APP_TARGET_KEY = "appTarget";

export const APP_TARGETS = {
  cloud: { base: "https://vsummary.net", label: "云端 vsummary.net" },
  local: { base: "http://127.0.0.1:4173", label: "本机 VSummary" },
};

// The desktop package keeps "local"; the vsummary.net download is packed with "cloud".
export const DEFAULT_APP_TARGET = "local";

export function normalizeAppTarget(value) {
  return Object.hasOwn(APP_TARGETS, value) ? value : DEFAULT_APP_TARGET;
}

export async function loadAppTarget(chromeApi) {
  const stored = await chromeApi.storage.local.get(APP_TARGET_KEY);
  return normalizeAppTarget(stored[APP_TARGET_KEY]);
}
