import { describe, expect, it } from "vitest";
import { isSaveableOpenaiBaseUrl, toProviderTestErrorMessage } from "@src/features/workspace/model/workspaceSettingsActions";

describe("toProviderTestErrorMessage", () => {
  it("keeps backend model timeout message without HTTP status prefix", () => {
    expect(toProviderTestErrorMessage(new Error("503 模型超时"))).toBe("模型超时");
  });

  it("treats aborted provider tests as model timeout", () => {
    expect(toProviderTestErrorMessage(new DOMException("This operation was aborted", "AbortError"))).toBe("模型超时");
  });
});

describe("isSaveableOpenaiBaseUrl", () => {
  it("does not save incomplete edits while the user is typing", () => {
    expect(isSaveableOpenaiBaseUrl("")).toBe(false);
    expect(isSaveableOpenaiBaseUrl("https://")).toBe(false);
    expect(isSaveableOpenaiBaseUrl("api.example.com")).toBe(false);
  });

  it("accepts complete OpenAI-compatible base URLs without removing trailing slash", () => {
    expect(isSaveableOpenaiBaseUrl("https://api.example.com/")).toBe(true);
    expect(isSaveableOpenaiBaseUrl("http://127.0.0.1:8317/v1/")).toBe(true);
  });
});
