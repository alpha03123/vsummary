import { beforeEach, describe, expect, it } from "vitest";

import {
  createInitialWorkspaceState,
  loadChatSessionIdsByScope,
  loadChatSessionListsByScope,
  removeChatSessionForScope,
  removeScopedValue,
  resolveChatSessionsForScope,
} from "./workspaceState";
import { workspaceReducer } from "./workspaceReducer";

const CHAT_SESSION_STORAGE_KEY = "video-include.chat-sessions";

describe("workspaceState chat session persistence", () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  it("hydrates persisted multi-session metadata from storage", () => {
    window.localStorage.setItem(
      CHAT_SESSION_STORAGE_KEY,
      JSON.stringify({
        activeSessionIdsByScope: {
          "series|series-a|series-home": "series|series-a|series-home::2",
        },
        sessionListsByScope: {
          "series|series-a|series-home": [
            {
              id: "series|series-a|series-home::2",
              title: "第二个问题",
              createdAt: 2,
              updatedAt: 3,
            },
            {
              id: "series|series-a|series-home",
              title: "当前对话",
              createdAt: 1,
              updatedAt: 1,
            },
          ],
        },
      }),
    );

    const initialState = createInitialWorkspaceState();

    expect(initialState.chatSessionIdsByScope).toEqual({
      "series|series-a|series-home": "series|series-a|series-home::2",
    });
    expect(initialState.chatSessionListsByScope).toEqual({
      "series|series-a|series-home": [
        expect.objectContaining({
          id: "series|series-a|series-home::2",
          title: "第二个问题",
          createdAt: 2,
          updatedAt: 3,
        }),
        expect.objectContaining({
          id: "series|series-a|series-home",
          title: "当前对话",
          createdAt: 1,
          updatedAt: 1,
        }),
      ],
    });
  });

  it("upgrades legacy single-session storage into a selectable session list", () => {
    window.localStorage.setItem(
      CHAT_SESSION_STORAGE_KEY,
      JSON.stringify({
        "series|series-a|series-home": "series|series-a|series-home::legacy",
      }),
    );

    const sessionIdsByScope = loadChatSessionIdsByScope();
    const sessionListsByScope = loadChatSessionListsByScope();
    const resolved = resolveChatSessionsForScope(
      sessionIdsByScope,
      sessionListsByScope,
      "series|series-a|series-home",
    );

    expect(resolved.activeSessionId).toBe("series|series-a|series-home::legacy");
    expect(resolved.sessions).toEqual([
      expect.objectContaining({
        id: "series|series-a|series-home::legacy",
        title: "当前对话",
      }),
    ]);
    expect(resolved.chatSessionListsByScope["series|series-a|series-home"]).toHaveLength(1);
  });

  it("removes deleted session metadata and scoped records", () => {
    const sessionListsByScope = {
      "series|series-a|series-home": [
        { id: "series|series-a|series-home::2", title: "第二个问题" },
        { id: "series|series-a|series-home", title: "当前对话" },
      ],
    };
    const chatThreads = {
      "series|series-a|series-home::2": [{ id: "msg-2", role: "assistant", content: "第二个回答" }],
      "series|series-a|series-home": [{ id: "msg-1", role: "assistant", content: "第一个回答" }],
    };

    expect(
      removeChatSessionForScope(
        sessionListsByScope,
        "series|series-a|series-home",
        "series|series-a|series-home::2",
      )["series|series-a|series-home"],
    ).toEqual([
      expect.objectContaining({ id: "series|series-a|series-home", title: "当前对话" }),
    ]);
    expect(removeScopedValue(chatThreads, "series|series-a|series-home::2")).toEqual({
      "series|series-a|series-home": [{ id: "msg-1", role: "assistant", content: "第一个回答" }],
    });
  });
});

describe("workspaceReducer knowledge memory status", () => {
  it("stores the latest long-term memory snapshot", () => {
    const state = createInitialWorkspaceState();
    const snapshot = {
      status: "running",
      stage: "index",
      progress: 20,
      detail: "正在重建长期记忆索引",
      error: null,
    };

    const nextState = workspaceReducer(state, {
      type: "knowledge_memory_status_loaded",
      snapshot,
    });

    expect(nextState.knowledgeMemorySnapshot).toBe(snapshot);
  });
});
