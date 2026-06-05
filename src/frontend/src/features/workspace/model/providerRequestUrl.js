export function buildOpenAICompatibleChatCompletionsUrl(baseUrl) {
  const apiBase = resolveOpenAICompatibleApiBaseUrl(baseUrl);
  return apiBase ? `${apiBase}/chat/completions` : "";
}

function resolveOpenAICompatibleApiBaseUrl(value) {
  const normalized = normalizeProviderBaseUrl(value);
  if (!normalized) {
    return "";
  }

  let parsed;
  try {
    parsed = new URL(normalized);
  } catch {
    return normalized;
  }

  let path = parsed.pathname.replace(/\/+$/, "");
  if (!/\/v\d+$/.test(path)) {
    path = path ? `${path}/v1` : "/v1";
  }
  parsed.pathname = path;
  parsed.search = "";
  parsed.hash = "";
  return parsed.toString().replace(/\/$/, "");
}

function normalizeProviderBaseUrl(value) {
  if (typeof value !== "string") {
    return "";
  }
  let normalized = value.trim().replace(/\/+$/, "");
  for (const endpoint of ["/chat/completions", "/responses", "/completions"]) {
    if (normalized.endsWith(endpoint)) {
      normalized = normalized.slice(0, -endpoint.length).replace(/\/+$/, "");
      break;
    }
  }
  return normalized;
}
