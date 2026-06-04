import { describe, expect, it } from "vitest";
import { buildOpenAICompatibleChatCompletionsUrl } from "@src/features/workspace/model/providerRequestUrl";

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
