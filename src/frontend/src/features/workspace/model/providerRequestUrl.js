export function buildOpenAICompatibleChatCompletionsUrl(baseUrl) {
  const apiBase = resolveOpenAICompatibleApiBaseUrl(baseUrl);
  return apiBase ? `${apiBase}/chat/completions` : "";
}

export function buildProviderRequestPreviewUrl(provider, baseUrl) {
  const normalizedProvider = typeof provider === "string" ? provider.trim().toLowerCase() : "";
  if (normalizedProvider === "ollama") {
    return buildOllamaGenerateUrl(baseUrl);
  }
  return buildOpenAICompatibleChatCompletionsUrl(baseUrl);
}

function buildOllamaGenerateUrl(baseUrl) {
  const apiBase = resolveOllamaApiBaseUrl(baseUrl);
  return apiBase ? `${apiBase}/api/generate` : "";
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

function resolveOllamaApiBaseUrl(value) {
  const normalized = normalizeProviderBaseUrl(value) || "http://127.0.0.1:11434";
  for (const endpoint of ["/api/generate", "/api/chat", "/v1"]) {
    if (normalized.endsWith(endpoint)) {
      return normalized.slice(0, -endpoint.length).replace(/\/+$/, "");
    }
  }
  return normalized;
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
