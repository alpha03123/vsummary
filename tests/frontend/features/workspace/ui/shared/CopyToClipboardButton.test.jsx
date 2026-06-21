import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { copyText } from "@src/features/workspace/ui/shared/clipboard";
import { CopyToClipboardButton } from "@src/features/workspace/ui/shared/CopyToClipboardButton";

vi.mock("@src/features/workspace/ui/shared/clipboard", () => ({
  copyText: vi.fn(),
}));

describe("CopyToClipboardButton", () => {
  beforeEach(() => {
    copyText.mockReset();
    copyText.mockResolvedValue(undefined);
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("renders Copy 图标 + 默认文案'复制'", () => {
    render(<CopyToClipboardButton text="abc" />);
    const btn = screen.getByRole("button", { name: "复制" });
    expect(btn).toBeInTheDocument();
    expect(btn.querySelector("svg")).toBeInTheDocument();
  });

  it("点击后切换为 Check 图标 + '已复制'文案 + emerald 背景", async () => {
    render(<CopyToClipboardButton text="abc" />);
    const btn = screen.getByRole("button", { name: "复制" });
    await act(async () => {
      fireEvent.click(btn);
    });
    const copiedBtn = screen.getByRole("button", { name: "已复制" });
    expect(copiedBtn.className).toMatch(/bg-emerald-100/);
  });

  it("aria-label 反映当前状态", async () => {
    render(<CopyToClipboardButton text="abc" />);
    expect(screen.getByRole("button").getAttribute("aria-label")).toBe("复制");
    await act(async () => {
      fireEvent.click(screen.getByRole("button"));
    });
    expect(screen.getByRole("button").getAttribute("aria-label")).toBe("已复制");
  });

  it("初始态 hover 切换背景色", () => {
    render(<CopyToClipboardButton text="abc" />);
    const btn = screen.getByRole("button", { name: "复制" });
    expect(btn.className).toMatch(/bg-stone-100/);
    expect(btn.className).toMatch(/hover:bg-stone-200/);
  });

  it("1600ms 后复原初始态", async () => {
    vi.useFakeTimers();
    render(<CopyToClipboardButton text="abc" />);
    await act(async () => {
      fireEvent.click(screen.getByRole("button"));
    });
    expect(screen.getByRole("button", { name: "已复制" })).toBeInTheDocument();
    await act(async () => {
      vi.advanceTimersByTime(1600);
    });
    expect(screen.getByRole("button", { name: "复制" })).toBeInTheDocument();
  });

  it("连点同一按钮, 复原时间以最后一次为准", async () => {
    vi.useFakeTimers();
    render(<CopyToClipboardButton text="abc" />);
    await act(async () => {
      fireEvent.click(screen.getByRole("button"));
    });
    await act(async () => {
      vi.advanceTimersByTime(1000);
    });
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "已复制" }));
    });
    await act(async () => {
      vi.advanceTimersByTime(1000);
    });
    expect(screen.getByRole("button", { name: "已复制" })).toBeInTheDocument();
    await act(async () => {
      vi.advanceTimersByTime(600);
    });
    expect(screen.getByRole("button", { name: "复制" })).toBeInTheDocument();
  });

  it("卸载时清除 timeout, 无 React 警告", async () => {
    vi.useFakeTimers();
    const errorSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    const { unmount } = render(<CopyToClipboardButton text="abc" />);
    await act(async () => {
      fireEvent.click(screen.getByRole("button"));
    });
    unmount();
    await act(async () => {
      vi.advanceTimersByTime(2000);
    });
    const allCalls = errorSpy.mock.calls.flat().join("\n");
    expect(allCalls).not.toMatch(/unmounted|wrapped in act/i);
    errorSpy.mockRestore();
  });

  it("copyText reject 时保持初始态, 不进入 copied", async () => {
    copyText.mockRejectedValueOnce(new Error("permission denied"));
    render(<CopyToClipboardButton text="abc" />);
    await act(async () => {
      fireEvent.click(screen.getByRole("button"));
    });
    expect(screen.getByRole("button", { name: "复制" })).toBeInTheDocument();
  });

  it("不同实例的 copied 状态相互独立", async () => {
    vi.useFakeTimers();
    render(
      <div>
        <CopyToClipboardButton text="A" />
        <CopyToClipboardButton text="B" />
      </div>,
    );
    const buttons = screen.getAllByRole("button", { name: "复制" });
    await act(async () => {
      fireEvent.click(buttons[0]);
    });
    await act(async () => {
      fireEvent.click(buttons[1]);
    });
    expect(screen.getAllByRole("button", { name: "已复制" })).toHaveLength(2);
  });
});