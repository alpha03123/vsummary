import { describe, expect, it } from "vitest";
import {
  buildOpenAICompatibleChatCompletionsUrl,
  buildProviderRequestPreviewUrl,
} from "@src/features/workspace/model/providerRequestUrl";

describe("buildOpenAICompatibleChatCompletionsUrl", () => {
  it("adds v1 and chat completions path for a root provider url", () => {
    expect(buildOpenAICompatibleChatCompletionsUrl("https://jiuuij.de5.net")).toBe(
      "https://jiuuij.de5.net/v1/chat/completions",
    );
  });

  it("does not duplicate an existing version suffix", () => {
    expect(buildOpenAICompatibleChatCompletionsUrl("https://jiuuij.de5.net/v1/")).toBe(
      "https://jiuuij.de5.net/v1/chat/completions",
    );
  });
});

describe("buildProviderRequestPreviewUrl", () => {
  it("uses OpenAI-compatible chat completions URLs for OpenAI providers", () => {
    expect(buildProviderRequestPreviewUrl("openai", "https://api.example.com")).toBe(
      "https://api.example.com/v1/chat/completions",
    );
  });

  it("uses Ollama native generate URLs for Ollama provider", () => {
    expect(buildProviderRequestPreviewUrl("ollama", "http://127.0.0.1:11434")).toBe(
      "http://127.0.0.1:11434/api/generate",
    );
  });

  it("previews the default Ollama native endpoint when the base URL is empty", () => {
    expect(buildProviderRequestPreviewUrl("ollama", "")).toBe(
      "http://127.0.0.1:11434/api/generate",
    );
  });
});
