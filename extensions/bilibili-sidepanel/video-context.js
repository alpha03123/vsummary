const BILIBILI_VIDEO_HOSTS = new Set(["www.bilibili.com", "bilibili.com"]);

function normalizePage(value) {
  const page = Number.parseInt(value ?? "1", 10);
  return Number.isSafeInteger(page) && page > 0 ? page : 1;
}

export function parseVideoContext(tab) {
  if (!Number.isInteger(tab?.id) || typeof tab.url !== "string") {
    return null;
  }

  try {
    const parsed = new URL(tab.url);
    const match = parsed.pathname.match(/^\/video\/(BV[\w]+)/i);
    if (!BILIBILI_VIDEO_HOSTS.has(parsed.hostname) || !match) {
      return null;
    }

    const bvid = match[1];
    const page = normalizePage(parsed.searchParams.get("p"));
    return {
      tabId: tab.id,
      url: parsed.toString(),
      key: `${bvid}:${page}`,
    };
  } catch {
    return null;
  }
}

export function contextsMatch(left, right) {
  return left?.key === right?.key && left?.tabId === right?.tabId && left?.url === right?.url;
}
