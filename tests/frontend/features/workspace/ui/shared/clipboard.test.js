import { afterEach, describe, expect, it, vi } from "vitest";

import { copyText } from "@src/features/workspace/ui/shared/clipboard";

describe("copyText", () => {
  const originalClipboard = navigator.clipboard;
  const originalExecCommand = document.execCommand;

  afterEach(() => {
    Object.defineProperty(navigator, "clipboard", {
      value: originalClipboard,
      configurable: true,
      writable: true,
    });
    document.execCommand = originalExecCommand;
    vi.restoreAllMocks();
  });

  it("writes to navigator.clipboard.writeText when available", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", {
      value: { writeText },
      configurable: true,
      writable: true,
    });
    const execSpy = vi.fn();
    document.execCommand = execSpy;

    await copyText("hello");

    expect(writeText).toHaveBeenCalledWith("hello");
    expect(execSpy).not.toHaveBeenCalled();
  });

  it("falls back to execCommand when clipboard API is unavailable", async () => {
    Object.defineProperty(navigator, "clipboard", {
      value: undefined,
      configurable: true,
      writable: true,
    });
    const execSpy = vi.fn();
    document.execCommand = execSpy;

    await copyText("fallback-text");

    expect(execSpy).toHaveBeenCalledWith("copy");
    expect(document.body.querySelector("textarea")).toBeNull();
  });
});