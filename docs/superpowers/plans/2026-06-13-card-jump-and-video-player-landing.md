# Card Jump + Video Player Landing — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let users click any chapter card or transcript segment in **AI 概况** to seek + auto-play the video; move the **video player** to the middle column (replacing the chat) and put the **chat** in a right-side drawer opened from the toolbar; remove the **媒体预览** tool tile.

**Architecture:** Frontend-only refactor. The state layer is renamed (`previewSeekRequest` → `playerSeekRequest`, action `preview_seek_requested` → `player_seek_requested`) and gains a `chatDrawerOpen` field + 3 actions. The controller exposes `onSeekToTime` and chat-drawer toggles. The page model groups player behavior under `shell.player.*` and drawer state under `chat.*`. The UI moves `WorkspacePreviewView` to `ui/WorkspaceVideoPlayer.jsx` (auto-play on seek), adds `ui/ChatDrawer.jsx`, wires chapter/transcript clicks in `WorkspaceOverviewView`, adds a 💬 button to `WorkspaceToolbar`, removes the preview tile from `workspaceToolMeta`, and rewires `WorkspacePage.jsx`.

**Tech Stack:** React 19, Vite 7, Tailwind 3, framer-motion (slide animation), Lucide icons, vitest + @testing-library/react (jsdom), Vitest with `@src` alias.

**Staging note:** The repo currently has no commits and a large number of pre-staged files. Every task's commit step uses `git add <exact files>` and `git commit --only -- <files>` to commit only that task's files. If a task has no other staged changes, the `--only` flag is a no-op. This keeps each task's commit focused.

---

## Acceptance Criteria (end-to-end)

The implementation is **done** when **all** of these pass:

1. **AC-1 Card jump**: Clicking the chapter header (eyebrow + title + time badge) in AI 概况 seeks the video to `chapter.start_seconds` and auto-plays.
2. **AC-2 Transcript jump**: Clicking any transcript segment row inside a chapter's expanded details seeks to that segment's `start_seconds` and auto-plays.
3. **AC-3 Non-clickable areas**: Clicking a chapter's `summary` paragraph, `key_points` bullet, or the **Key Takeaways** / **Core Problem** cards does **not** trigger a seek.
4. **AC-4 Middle player**: When a video is selected, the middle column shows the `<video>` element with the player's URL. The chat panel is no longer in the middle.
5. **AC-5 Empty state**: When no video is selected (e.g., series-home), the middle shows a "选择视频以开始预览" placeholder block.
6. **AC-6 Toolbar button**: A 💬 button on the toolbar toggles the chat drawer. When open, the button has an active style (matches the settings button's open style). Esc and backdrop click both close the drawer.
7. **AC-7 Drawer behavior**: When open, the chat drawer overlays the right pane (≤420px wide). The middle player stays visible. The settings overlay still covers the drawer when opened.
8. **AC-8 Tool tile removed**: The tool grid in AI概况 / 笔记 / 思维导图 / 知识卡片 no longer shows the 媒体预览 tile. Trying to navigate to `preview` (e.g., via stale state) renders a placeholder, not the old preview view.
9. **AC-9 Auto-play**: After any seek triggered by clicking, the video's `currentTime` matches the requested seconds and the `play()` promise is invoked. Failures (e.g., past-end) are silent — the user can press ▶.
10. **AC-10 Audio source**: Audio sources show "音频文件暂不支持预览" and ignore seeks (existing behavior preserved).
11. **AC-11 Chat citation flow still works**: Clicking a citation inside a chat message still seeks the player. The chat's `openSeekReference` dispatch uses the new action name and reaches the middle player.
12. **AC-12 No regressions**: `npm test` (frontend) and `python -m pytest tests/backend` both pass. The backend is untouched.
13. **AC-13 Boundary discipline**: `model/*` does not import from `ui/*`. The new `ui/WorkspaceVideoPlayer.jsx` and `ui/ChatDrawer.jsx` are **not** in `ui/views/`. The new `ui/views/WorkspaceOverviewView.jsx` still receives `onSeek` only as a prop.

---

## File Structure

### Files to create
- `src/frontend/src/features/workspace/ui/WorkspaceVideoPlayer.jsx` — renamed from `views/WorkspacePreviewView.jsx`; auto-play on seek
- `src/frontend/src/features/workspace/ui/ChatDrawer.jsx` — slide-out wrapper around `WorkspaceChatPanel`
- `tests/frontend/features/workspace/ui/WorkspaceVideoPlayer.test.jsx` — auto-play + audio behavior
- `tests/frontend/features/workspace/ui/ChatDrawer.test.jsx` — open/close/esc/backdrop
- `tests/frontend/features/workspace/ui/views/WorkspaceOverviewView.test.jsx` — chapter/transcript/key_points click routing
- `tests/frontend/features/workspace/ui/WorkspaceToolbar.test.jsx` — 💬 button toggle

### Files to modify
- `src/frontend/src/features/workspace/model/workspaceState.js` — rename field, add `chatDrawerOpen`
- `src/frontend/src/features/workspace/model/workspaceReducer.js` — rename action, rename reset fields, add 3 chat-drawer cases
- `src/frontend/src/features/workspace/model/useWorkspaceController.js` — rename returned field, add 4 new functions
- `src/frontend/src/features/workspace/model/workspaceChatActions.js` — update 2 dispatch sites
- `src/frontend/src/features/workspace/ui/workspacePageModel.js` — group player + drawer fields
- `src/frontend/src/features/workspace/ui/WorkspacePage.jsx` — rewire middle column, mount drawer
- `src/frontend/src/features/workspace/ui/WorkspaceToolbar.jsx` — 💬 button
- `src/frontend/src/features/workspace/ui/WorkspaceReadingPane.jsx` — drop preview props, add `onSeek`
- `src/frontend/src/features/workspace/ui/views/WorkspaceOverviewView.jsx` — chapter + transcript click handlers
- `src/frontend/src/features/workspace/ui/workspaceToolMeta.js` — remove `TOOL_TILES.preview` and the `describeToolState` `preview` branch

### Files to delete
- `src/frontend/src/features/workspace/ui/views/WorkspacePreviewView.jsx` (moved to `ui/WorkspaceVideoPlayer.jsx`)
- `tests/frontend/features/workspace/ui/WorkspacePreviewView.test.jsx` (replaced by `WorkspaceVideoPlayer.test.jsx`)

### Test files to extend
- `tests/frontend/features/workspace/model/workspaceReducer.test.js` — new cases for `player_seek_requested`, `chat_drawer_*`
- `tests/frontend/features/workspace/ui/workspacePageModel.test.jsx` — fixture updates + new cases for player + drawer

---

## Task 1: Rename `previewSeekRequest` → `playerSeekRequest` in state layer

**Files:**
- Modify: `src/frontend/src/features/workspace/model/workspaceState.js:506, 591` (2 reset sites in helpers)
- Modify: `src/frontend/src/features/workspace/model/workspaceReducer.js:448, 478, 516, 562, 753, 756` (4 reset sites + 1 case label + 1 field write)

**Acceptance criteria:** All occurrences of `previewSeekRequest` are renamed to `playerSeekRequest`. The shape of the seek-request object is **unchanged**. No other behavior changes.

- [ ] **Step 1: Run grep to confirm all call sites**

```bash
cd src/frontend
grep -rn "previewSeekRequest" src/features tests
```

Expected: list of all sites (we'll change every one). Document the count.

- [ ] **Step 2: Edit `workspaceState.js`**

In `src/frontend/src/features/workspace/model/workspaceState.js`:
- Line 506: change `previewSeekRequest: null,` → `playerSeekRequest: null,`
- Line 591: change `previewSeekRequest: null,` → `playerSeekRequest: null,`

(After this step, the file has 2 occurrences of `playerSeekRequest: null` and 0 of `previewSeekRequest: null`.)

- [ ] **Step 3: Edit `workspaceReducer.js`**

In `src/frontend/src/features/workspace/model/workspaceReducer.js`:
- Line 448, 478, 516, 562: `previewSeekRequest: null,` → `playerSeekRequest: null,`
- Line 753: `case "preview_seek_requested":` → `case "player_seek_requested":`
- Line 756: `previewSeekRequest: {` → `playerSeekRequest: {`

(The case body keeps the same shape — only the action name and the field name change.)

- [ ] **Step 4: Run grep to confirm zero remaining in state files**

```bash
cd src/frontend
grep -n "previewSeekRequest\|preview_seek_requested" src/features/workspace/model
```

Expected: no matches (the only sites left are in `workspaceChatActions.js` and the prop name in `useWorkspaceController.js` / page files, which we change in subsequent tasks).

- [ ] **Step 5: Run frontend tests**

```bash
cd src/frontend
npm test
```

Expected: same pass/fail set as before this task. **Some tests will fail** because the action name in dispatch sites has not been updated yet. That's expected — the next task fixes it. Do not panic; note which tests fail and proceed.

- [ ] **Step 6: Commit**

```bash
cd src/frontend/..
git add src/frontend/src/features/workspace/model/workspaceState.js \
        src/frontend/src/features/workspace/model/workspaceReducer.js
git commit --only -- src/frontend/src/features/workspace/model/workspaceState.js \
                     src/frontend/src/features/workspace/model/workspaceReducer.js \
        -m "refactor(state): rename previewSeekRequest to playerSeekRequest"
```

---

## Task 2: Update `workspaceChatActions.js` dispatch sites

**Files:**
- Modify: `src/frontend/src/features/workspace/model/workspaceChatActions.js:139, 165`

**Acceptance criteria:** Both dispatch sites use `player_seek_requested` instead of `preview_seek_requested`. No behavior change.

- [ ] **Step 1: Edit `workspaceChatActions.js`**

In `src/frontend/src/features/workspace/model/workspaceChatActions.js`:
- Line 139: change `type: "preview_seek_requested",` → `type: "player_seek_requested",`
- Line 165: change `type: "preview_seek_requested",` → `type: "player_seek_requested",`

- [ ] **Step 2: Run grep across model/ to confirm zero `preview_*` references**

```bash
cd src/frontend
grep -rn "previewSeekRequest\|preview_seek_requested" src/features/workspace/model tests/frontend/features/workspace/model
```

Expected: no matches. (Some test files might still reference the old name in fixtures — they'll be fixed in Task 3.)

- [ ] **Step 3: Run frontend tests**

```bash
cd src/frontend
npm test
```

Expected: most tests pass. Any test still failing should be a test fixture that hard-codes the old action name; fix those as part of Task 3 (reducer tests) or Task 4 (page-model tests).

- [ ] **Step 4: Commit**

```bash
cd src/frontend/..
git add src/frontend/src/features/workspace/model/workspaceChatActions.js
git commit --only -- src/frontend/src/features/workspace/model/workspaceChatActions.js \
        -m "refactor(chat-actions): dispatch player_seek_requested"
```

---

## Task 3: Add reducer cases for `chat_drawer_*` and `player_seek_requested` test coverage

**Files:**
- Modify: `src/frontend/src/features/workspace/model/workspaceReducer.js` (add 3 new cases)
- Modify: `src/frontend/src/features/workspace/model/workspaceState.js` (add `chatDrawerOpen` to default state)
- Modify: `tests/frontend/features/workspace/model/workspaceReducer.test.js` (add new `describe` block)

**Acceptance criteria:**
- A new `chatDrawerOpen: false` field exists in initial state.
- `chat_drawer_toggled` flips the field; `chat_drawer_opened` sets it to `true`; `chat_drawer_closed` sets it to `false`.
- Video/series switch still resets `playerSeekRequest` to `null` and **does not** touch `chatDrawerOpen`.
- `player_seek_requested` action writes the new field with the same shape as the old `preview_seek_requested` did.

- [ ] **Step 1: Write the failing tests**

Append to `tests/frontend/features/workspace/model/workspaceReducer.test.js`:

```js
describe("workspaceReducer chat drawer", () => {
  it("starts with chatDrawerOpen=false in initial state", () => {
    const state = createInitialWorkspaceState();
    expect(state.chatDrawerOpen).toBe(false);
  });

  it("chat_drawer_toggled flips the field", () => {
    const start = createInitialWorkspaceState();
    const opened = workspaceReducer(start, { type: "chat_drawer_toggled" });
    expect(opened.chatDrawerOpen).toBe(true);
    const closed = workspaceReducer(opened, { type: "chat_drawer_toggled" });
    expect(closed.chatDrawerOpen).toBe(false);
  });

  it("chat_drawer_opened sets the field to true", () => {
    const state = workspaceReducer(createInitialWorkspaceState(), { type: "chat_drawer_opened" });
    expect(state.chatDrawerOpen).toBe(true);
  });

  it("chat_drawer_closed sets the field to false", () => {
    const opened = workspaceReducer(createInitialWorkspaceState(), { type: "chat_drawer_opened" });
    const closed = workspaceReducer(opened, { type: "chat_drawer_closed" });
    expect(closed.chatDrawerOpen).toBe(false);
  });

  it("video_selected resets playerSeekRequest but keeps chatDrawerOpen", () => {
    const start = workspaceReducer(createInitialWorkspaceState(), { type: "chat_drawer_opened" });
    const request = { seconds: 5, endSeconds: null, query: "", matchedText: "", chapterTitle: "x", requestId: 1 };
    const withRequest = workspaceReducer(start, { type: "player_seek_requested", ...request });
    expect(withRequest.playerSeekRequest).toEqual(request);
    const afterVideo = workspaceReducer(withRequest, { type: "video_selected", seriesId: "s", videoId: "v" });
    expect(afterVideo.playerSeekRequest).toBeNull();
    expect(afterVideo.chatDrawerOpen).toBe(true);
  });
});
```

- [ ] **Step 2: Run the new tests to confirm they fail**

```bash
cd src/frontend
npx vitest run tests/frontend/features/workspace/model/workspaceReducer.test.js
```

Expected: the new `describe` block tests fail because `chatDrawerOpen` is not in the state and the chat-drawer cases don't exist.

- [ ] **Step 3: Add `chatDrawerOpen` to initial state**

In `src/frontend/src/features/workspace/model/workspaceState.js`, find the `createInitialWorkspaceState` function. Add `chatDrawerOpen: false,` as a top-level field (anywhere in the returned object, but keep it grouped with other UI shell fields).

Also add it to any reset-object helpers (e.g., `loadChatSessionsState` neighbors) — but **not** to the action handlers that reset `playerSeekRequest` on video switch. The test in step 1 asserts this.

- [ ] **Step 4: Add the 3 reducer cases**

In `src/frontend/src/features/workspace/model/workspaceReducer.js`, add these cases (anywhere in the switch, e.g., right after the `preview_seek_requested` → `player_seek_requested` case you already renamed):

```js
case "chat_drawer_toggled":
  return { ...state, chatDrawerOpen: !state.chatDrawerOpen };
case "chat_drawer_opened":
  return { ...state, chatDrawerOpen: true };
case "chat_drawer_closed":
  return { ...state, chatDrawerOpen: false };
```

- [ ] **Step 5: Run the new tests to confirm they pass**

```bash
cd src/frontend
npx vitest run tests/frontend/features/workspace/model/workspaceReducer.test.js
```

Expected: all tests in the file pass (the new `describe` block and the existing `describe` blocks).

- [ ] **Step 6: Commit**

```bash
cd src/frontend/..
git add src/frontend/src/features/workspace/model/workspaceState.js \
        src/frontend/src/features/workspace/model/workspaceReducer.js \
        tests/frontend/features/workspace/model/workspaceReducer.test.js
git commit --only -- src/frontend/src/features/workspace/model/workspaceState.js \
                     src/frontend/src/features/workspace/model/workspaceReducer.js \
                     tests/frontend/features/workspace/model/workspaceReducer.test.js \
        -m "feat(state): add chatDrawerOpen field and toggle/open/close actions"
```

---

## Task 4: Add `onSeekToTime` and chat-drawer controls to controller

**Files:**
- Modify: `src/frontend/src/features/workspace/model/useWorkspaceController.js`
  - Rename `previewSeekRequest: state.previewSeekRequest` → `playerSeekRequest: state.playerSeekRequest` (line 149)
  - Add 4 new functions: `onSeekToTime`, `onToggleChatDrawer`, `onOpenChatDrawer`, `onCloseChatDrawer`
  - Add the 4 new functions to the returned object

**Acceptance criteria:**
- `onSeekToTime({ seconds, endSeconds, chapterTitle })` dispatches `player_seek_requested` with a unique `requestId` (using `Date.now()`).
- `onSeekToTime` early-returns when `seconds` is not finite (e.g., `NaN`, `undefined`).
- The 3 chat-drawer functions dispatch the matching actions.

- [ ] **Step 1: Create a new test file**

Create `tests/frontend/features/workspace/model/useWorkspaceController.test.js`:

```js
import { act, renderHook } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { useWorkspaceController } from "@src/features/workspace/model/useWorkspaceController";

describe("useWorkspaceController.onSeekToTime", () => {
  it("dispatches player_seek_requested with the provided payload", () => {
    const { result } = renderHook(() => useWorkspaceController());
    act(() => {
      result.current.onSeekToTime({ seconds: 42.5, endSeconds: 50, chapterTitle: "Intro" });
    });
    expect(result.current.playerSeekRequest).toMatchObject({
      seconds: 42.5,
      endSeconds: 50,
      chapterTitle: "Intro",
    });
    expect(typeof result.current.playerSeekRequest.requestId).toBe("number");
  });

  it("defaults endSeconds to null and chapterTitle to empty string", () => {
    const { result } = renderHook(() => useWorkspaceController());
    act(() => {
      result.current.onSeekToTime({ seconds: 10 });
    });
    expect(result.current.playerSeekRequest).toMatchObject({
      seconds: 10,
      endSeconds: null,
      chapterTitle: "",
    });
  });

  it("early-returns on non-finite seconds", () => {
    const { result } = renderHook(() => useWorkspaceController());
    act(() => {
      result.current.onSeekToTime({ seconds: NaN });
    });
    expect(result.current.playerSeekRequest).toBeNull();
  });

  it("early-returns when called with no argument", () => {
    const { result } = renderHook(() => useWorkspaceController());
    act(() => {
      result.current.onSeekToTime();
    });
    expect(result.current.playerSeekRequest).toBeNull();
  });
});

describe("useWorkspaceController chat-drawer actions", () => {
  it("onToggleChatDrawer flips chatDrawerOpen", () => {
    const { result } = renderHook(() => useWorkspaceController());
    expect(result.current.chatDrawerOpen).toBe(false);
    act(() => result.current.onToggleChatDrawer());
    expect(result.current.chatDrawerOpen).toBe(true);
    act(() => result.current.onToggleChatDrawer());
    expect(result.current.chatDrawerOpen).toBe(false);
  });

  it("onOpenChatDrawer and onCloseChatDrawer set the field", () => {
    const { result } = renderHook(() => useWorkspaceController());
    act(() => result.current.onOpenChatDrawer());
    expect(result.current.chatDrawerOpen).toBe(true);
    act(() => result.current.onCloseChatDrawer());
    expect(result.current.chatDrawerOpen).toBe(false);
  });
});
```

- [ ] **Step 2: Run the new tests to confirm they fail**

```bash
cd src/frontend
npx vitest run tests/frontend/features/workspace/model/useWorkspaceController.test.js
```

Expected: all tests fail because `onSeekToTime` / `onToggleChatDrawer` / etc. don't exist on the controller, and `playerSeekRequest` / `chatDrawerOpen` aren't returned.

- [ ] **Step 3: Edit `useWorkspaceController.js`**

In `src/frontend/src/features/workspace/model/useWorkspaceController.js`:

1. Line 149: change
   ```js
   previewSeekRequest: state.previewSeekRequest,
   ```
   to
   ```js
   playerSeekRequest: state.playerSeekRequest,
   ```

2. Add these functions just before the `return { ... }` block (around line 117, before `onClearError`):

```js
function onSeekToTime({ seconds, endSeconds = null, chapterTitle = "" } = {}) {
  if (!Number.isFinite(seconds)) {
    return;
  }
  dispatch({
    type: "player_seek_requested",
    seconds,
    endSeconds,
    chapterTitle,
    requestId: Date.now(),
  });
}

function onToggleChatDrawer() {
  dispatch({ type: "chat_drawer_toggled" });
}

function onOpenChatDrawer() {
  dispatch({ type: "chat_drawer_opened" });
}

function onCloseChatDrawer() {
  dispatch({ type: "chat_drawer_closed" });
}
```

3. Add these entries to the returned object (any logical position; group them near related functions):

```js
playerSeekRequest: state.playerSeekRequest,   // (the line you renamed above; keep this as-is)
onSeekToTime,
onToggleChatDrawer,
onOpenChatDrawer,
onCloseChatDrawer,
```

- [ ] **Step 4: Run the new tests to confirm they pass**

```bash
cd src/frontend
npx vitest run tests/frontend/features/workspace/model/useWorkspaceController.test.js
```

Expected: all tests pass.

- [ ] **Step 5: Run all frontend tests to catch regressions**

```bash
cd src/frontend
npm test
```

Expected: same pass/fail set as before Task 1 plus the new tests. The only failures, if any, are in `workspacePageModel.test.jsx` (still references the old `previewSeekRequest` name in its fake-controller fixture). Note them.

- [ ] **Step 6: Commit**

```bash
cd src/frontend/..
git add src/frontend/src/features/workspace/model/useWorkspaceController.js \
        tests/frontend/features/workspace/model/useWorkspaceController.test.js
git commit --only -- src/frontend/src/features/workspace/model/useWorkspaceController.js \
                     tests/frontend/features/workspace/model/useWorkspaceController.test.js \
        -m "feat(controller): add onSeekToTime and chat-drawer actions"
```

---

## Task 5: Update `workspacePageModel.js` to expose player + drawer fields

**Files:**
- Modify: `src/frontend/src/features/workspace/ui/workspacePageModel.js:33, 34, 51, 52` (rename + group)
- Modify: `tests/frontend/features/workspace/ui/workspacePageModel.test.jsx` (fixture + new cases)

**Acceptance criteria:**
- `pageModel.shell.previewUrl` is still present.
- `pageModel.shell.previewSeekRequest` is **gone**; replaced by `pageModel.shell.playerSeekRequest`.
- `pageModel.shell.player.seekToTime` exists and equals the controller's `onSeekToTime`.
- `pageModel.chat.drawerOpen`, `pageModel.chat.toggleDrawer`, `pageModel.chat.openDrawer`, `pageModel.chat.closeDrawer` exist and map to the matching controller fields.

- [ ] **Step 1: Edit `workspacePageModel.js`**

In `src/frontend/src/features/workspace/ui/workspacePageModel.js`:

1. Line 33: change
   ```js
   previewSeekRequest: controller.previewSeekRequest,
   ```
   to
   ```js
   playerSeekRequest: controller.playerSeekRequest,
   player: {
     seekToTime: controller.onSeekToTime,
   },
   ```

2. Line 51 (in the `chat` block): add (alongside existing `openSeekReference` and friends):

   ```js
   drawerOpen: controller.chatDrawerOpen,
   toggleDrawer: controller.onToggleChatDrawer,
   openDrawer: controller.onOpenChatDrawer,
   closeDrawer: controller.onCloseChatDrawer,
   ```

- [ ] **Step 2: Update the page-model test fixture**

In `tests/frontend/features/workspace/ui/workspacePageModel.test.jsx`, the `createController` factory at the top of the file references the old field names. Update:

- Line 27: `previewSeekRequest: null,` → `playerSeekRequest: null,`
- Add to the controller object (anywhere):
  ```js
  chatDrawerOpen: false,
  onSeekToTime: () => {},
  onToggleChatDrawer: () => {},
  onOpenChatDrawer: () => {},
  onCloseChatDrawer: () => {},
  ```

- [ ] **Step 3: Add new page-model tests**

Append to the same test file:

```js
import { vi } from "vitest";

describe("buildWorkspacePageModel shell.player", () => {
  it("exposes playerSeekRequest and player.seekToTime", () => {
    const seekToTime = vi.fn();
    const controller = { ...createController(null), playerSeekRequest: { seconds: 7 }, onSeekToTime: seekToTime };
    const model = buildWorkspacePageModel(controller);
    expect(model.shell.playerSeekRequest).toEqual({ seconds: 7 });
    expect(model.shell.player.seekToTime).toBe(seekToTime);
  });
});

describe("buildWorkspacePageModel chat.drawer", () => {
  it("exposes drawer state and controls from the controller", () => {
    const toggle = vi.fn();
    const open = vi.fn();
    const close = vi.fn();
    const controller = {
      ...createController(null),
      chatDrawerOpen: true,
      onToggleChatDrawer: toggle,
      onOpenChatDrawer: open,
      onCloseChatDrawer: close,
    };
    const model = buildWorkspacePageModel(controller);
    expect(model.chat.drawerOpen).toBe(true);
    expect(model.chat.toggleDrawer).toBe(toggle);
    expect(model.chat.openDrawer).toBe(open);
    expect(model.chat.closeDrawer).toBe(close);
  });
});
```

- [ ] **Step 4: Run the page-model tests**

```bash
cd src/frontend
npx vitest run tests/frontend/features/workspace/ui/workspacePageModel.test.jsx
```

Expected: all tests pass (the existing "generation overlay" tests + the two new `describe` blocks).

- [ ] **Step 5: Commit**

```bash
cd src/frontend/..
git add src/frontend/src/features/workspace/ui/workspacePageModel.js \
        tests/frontend/features/workspace/ui/workspacePageModel.test.jsx
git commit --only -- src/frontend/src/features/workspace/ui/workspacePageModel.js \
                     tests/frontend/features/workspace/ui/workspacePageModel.test.jsx \
        -m "feat(page-model): expose player.seekToTime and chat drawer controls"
```

---

## Task 6: Create `WorkspaceVideoPlayer.jsx` (rename + auto-play) and delete old `WorkspacePreviewView.jsx`

**Files:**
- Create: `src/frontend/src/features/workspace/ui/WorkspaceVideoPlayer.jsx`
- Delete: `src/frontend/src/features/workspace/ui/views/WorkspacePreviewView.jsx`
- Create: `tests/frontend/features/workspace/ui/WorkspaceVideoPlayer.test.jsx`
- Delete: `tests/frontend/features/workspace/ui/WorkspacePreviewView.test.jsx`

**Acceptance criteria:**
- File moved to `ui/` (not `ui/views/`) — it's a layout-level slot, not a tool view.
- `videoSource` and `playerSeekRequest` are the prop names (replacing `previewSource` and `previewSeekRequest`).
- A new `play()` call happens after `currentTime` is set. Play failures are silently caught.
- The audio-source "音频文件暂不支持预览" placeholder still works.
- The "已定位到 …" info block reads from `playerSeekRequest` and still shows `chapterTitle` / `query` / `matchedText`.

- [ ] **Step 1: Create `WorkspaceVideoPlayer.jsx`**

Create `src/frontend/src/features/workspace/ui/WorkspaceVideoPlayer.jsx`:

```jsx
import { useEffect, useRef } from "react";

import { formatRange } from "../../../shared/lib/time";

export function WorkspaceVideoPlayer({ videoSource, playerSeekRequest, videoSourceType = "video" }) {
  const videoRef = useRef(null);
  const isAudioSource = videoSourceType === "audio";

  useEffect(() => {
    if (isAudioSource || !playerSeekRequest || !videoRef.current) {
      return;
    }

    const video = videoRef.current;
    const seekTo = () => {
      if (!Number.isFinite(playerSeekRequest.seconds)) {
        return;
      }
      const duration = Number.isFinite(video.duration) ? video.duration : null;
      const nextSeconds =
        duration == null
          ? Math.max(0, playerSeekRequest.seconds)
          : Math.min(Math.max(0, playerSeekRequest.seconds), duration);
      video.currentTime = nextSeconds;
      video.play().catch(() => { /* user-gesture rules; ignore failures (e.g., past-end) */ });
    };

    if (video.readyState >= 1) {
      seekTo();
      return;
    }

    video.addEventListener("loadedmetadata", seekTo, { once: true });
    return () => {
      video.removeEventListener("loadedmetadata", seekTo);
    };
  }, [isAudioSource, playerSeekRequest, videoSource]);

  return (
    <div className="flex flex-col gap-4">
      <div className="workspace-muted-panel rounded-3xl border p-4">
        <p className="mb-2 text-xs font-bold uppercase text-stone-500 dark:text-stone-400">Media Preview</p>
        {playerSeekRequest ? (
          <div className="mt-3 rounded-2xl border border-info/20 bg-info-subtle px-4 py-3 text-sm text-stone-800 dark:text-stone-100">
            <p className="font-semibold">
              已定位到 {formatRange(playerSeekRequest.seconds, playerSeekRequest.endSeconds ?? playerSeekRequest.seconds)}
              {playerSeekRequest.chapterTitle ? ` · ${playerSeekRequest.chapterTitle}` : ""}
            </p>
            {playerSeekRequest.query ? (
              <p className="mt-1 text-stone-600 dark:text-stone-300">检索问题：{playerSeekRequest.query}</p>
            ) : null}
            {playerSeekRequest.matchedText ? (
              <p className="mt-2 line-clamp-3 text-stone-700 dark:text-stone-200">{playerSeekRequest.matchedText}</p>
            ) : null}
          </div>
        ) : null}
      </div>
      {isAudioSource ? (
        <div className="workspace-elevated-panel rounded-3xl border p-8 text-center text-sm font-semibold text-stone-600 shadow-sm dark:text-zinc-300">
          音频文件暂不支持预览
        </div>
      ) : (
        <div className="workspace-elevated-panel overflow-hidden rounded-3xl border bg-black shadow-sm">
          <video key={videoSource} ref={videoRef} className="h-full w-full max-h-[72vh] bg-black" controls preload="metadata">
            <source src={videoSource} />
          </video>
        </div>
      )}
    </div>
  );
}
```

Differences from the old `WorkspacePreviewView.jsx`:
- Function name `WorkspaceVideoPlayer` and file path `ui/WorkspaceVideoPlayer.jsx`.
- Props: `videoSource` (was `previewSource`), `playerSeekRequest` (was `previewSeekRequest`).
- `video.play().catch(() => {})` added after `video.currentTime = nextSeconds`.
- `useEffect` deps updated to use the renamed prop name.

- [ ] **Step 2: Delete the old `WorkspacePreviewView.jsx` and its test**

```bash
cd src/frontend
rm src/features/workspace/ui/views/WorkspacePreviewView.jsx
rm tests/frontend/features/workspace/ui/WorkspacePreviewView.test.jsx
```

- [ ] **Step 3: Create the new test file**

Create `tests/frontend/features/workspace/ui/WorkspaceVideoPlayer.test.jsx`:

```jsx
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { WorkspaceVideoPlayer } from "@src/features/workspace/ui/WorkspaceVideoPlayer";

describe("WorkspaceVideoPlayer", () => {
  it("shows an unavailable preview message for audio files", () => {
    render(<WorkspaceVideoPlayer videoSource="/api/videos/series-1/audio-1/preview" videoSourceType="audio" />);
    expect(screen.getByText("音频文件暂不支持预览")).toBeInTheDocument();
    expect(screen.queryByRole("video")).toBeNull();
  });

  it("seeks the <video> and calls play() when playerSeekRequest arrives", () => {
    const playMock = vi.fn(() => Promise.resolve());
    const refSpy = vi.spyOn(HTMLMediaElement.prototype, "play").mockImplementation(playMock);

    const { rerender } = render(<WorkspaceVideoPlayer videoSource="/api/videos/s1/v1/preview" playerSeekRequest={null} />);
    const video = screen.getByRole("video") as HTMLVideoElement;
    // jsdom: readyState is 0 by default; the effect attaches a one-time 'loadedmetadata' listener.
    expect(video).toBeInTheDocument();

    rerender(
      <WorkspaceVideoPlayer
        videoSource="/api/videos/s1/v1/preview"
        playerSeekRequest={{
          seconds: 12.5,
          endSeconds: 18,
          query: "",
          matchedText: "",
          chapterTitle: "Chapter 1",
          requestId: 1,
        }}
      />,
    );

    // Simulate metadata loaded → triggers the seek handler.
    Object.defineProperty(video, "readyState", { value: 1, configurable: true });
    Object.defineProperty(video, "duration", { value: 60, configurable: true });
    fireEvent.loadedMetadata(video);

    expect(video.currentTime).toBe(12.5);
    expect(playMock).toHaveBeenCalled();
    refSpy.mockRestore();
  });

  it("clamps the seek to the video duration", () => {
    const playMock = vi.fn(() => Promise.resolve());
    vi.spyOn(HTMLMediaElement.prototype, "play").mockImplementation(playMock);

    const { rerender } = render(<WorkspaceVideoPlayer videoSource="/api/videos/s1/v1/preview" playerSeekRequest={null} />);
    const video = screen.getByRole("video") as HTMLVideoElement;
    Object.defineProperty(video, "readyState", { value: 1, configurable: true });
    Object.defineProperty(video, "duration", { value: 30, configurable: true });
    fireEvent.loadedMetadata(video);

    rerender(
      <WorkspaceVideoPlayer
        videoSource="/api/videos/s1/v1/preview"
        playerSeekRequest={{ seconds: 999, endSeconds: null, query: "", matchedText: "", chapterTitle: "", requestId: 2 }}
      />,
    );

    fireEvent.loadedMetadata(video);
    expect(video.currentTime).toBe(30);
  });

  it("ignores non-finite seconds without throwing", () => {
    const playMock = vi.fn(() => Promise.resolve());
    vi.spyOn(HTMLMediaElement.prototype, "play").mockImplementation(playMock);

    const { rerender } = render(<WorkspaceVideoPlayer videoSource="/api/videos/s1/v1/preview" playerSeekRequest={null} />);
    const video = screen.getByRole("video") as HTMLVideoElement;
    Object.defineProperty(video, "readyState", { value: 1, configurable: true });

    rerender(
      <WorkspaceVideoPlayer
        videoSource="/api/videos/s1/v1/preview"
        playerSeekRequest={{ seconds: NaN, endSeconds: null, query: "", matchedText: "", chapterTitle: "", requestId: 3 }}
      />,
    );

    expect(() => fireEvent.loadedMetadata(video)).not.toThrow();
    expect(playMock).not.toHaveBeenCalled();
  });
});
```

- [ ] **Step 4: Run the new test file**

```bash
cd src/frontend
npx vitest run tests/frontend/features/workspace/ui/WorkspaceVideoPlayer.test.jsx
```

Expected: all 4 tests pass.

- [ ] **Step 5: Run all frontend tests to catch stale references**

```bash
cd src/frontend
npm test
```

Expected: any test that still imports the old `WorkspacePreviewView` will fail. Grep for the old import path to find them:

```bash
cd src/frontend
grep -rn "WorkspacePreviewView\|views/WorkspacePreviewView" src tests
```

Each match must be updated. Likely sites: `WorkspacePage.jsx` (will be fixed in Task 11) and the test file we deleted. The next task (Task 11) is the right time to fix `WorkspacePage.jsx`; if any other test still references it, fix it inline.

- [ ] **Step 6: Commit**

```bash
cd src/frontend/..
git add -A src/frontend/src/features/workspace/ui/WorkspaceVideoPlayer.jsx \
         src/frontend/src/features/workspace/ui/views/WorkspacePreviewView.jsx \
         tests/frontend/features/workspace/ui/WorkspaceVideoPlayer.test.jsx \
         tests/frontend/features/workspace/ui/WorkspacePreviewView.test.jsx
git rm src/frontend/src/features/workspace/ui/views/WorkspacePreviewView.jsx \
       tests/frontend/features/workspace/ui/WorkspacePreviewView.test.jsx 2>/dev/null || true
git add src/frontend/src/features/workspace/ui/views/WorkspacePreviewView.jsx \
        tests/frontend/features/workspace/ui/WorkspacePreviewView.test.jsx 2>/dev/null
# If `git rm` succeeded above, the files are already staged for deletion.
# If you used `rm` in step 2 (which we did), then add as deletions:
git add -u src/frontend/src/features/workspace/ui/views/WorkspacePreviewView.jsx \
         tests/frontend/features/workspace/ui/WorkspacePreviewView.test.jsx
git commit -m "feat(player): move to ui/WorkspaceVideoPlayer, auto-play on seek"
```

If `git add -u` doesn't stage deletions (because the files were never tracked), use:

```bash
git add -A src/frontend/
git reset src/frontend/src/features/workspace/ui/views/WorkspacePreviewView.jsx
git checkout -- src/frontend/src/features/workspace/ui/views/WorkspacePreviewView.jsx 2>/dev/null || true
```

In that case manually commit with the right paths.

---

## Task 7: Create `ChatDrawer.jsx` component

**Files:**
- Create: `src/frontend/src/features/workspace/ui/ChatDrawer.jsx`
- Create: `tests/frontend/features/workspace/ui/ChatDrawer.test.jsx`

**Acceptance criteria:**
- Renders nothing when `isOpen={false}`.
- Renders a backdrop and a side panel when `isOpen={true}`; the panel mounts the `WorkspaceChatPanel` with the passed props.
- Click on the backdrop calls `onClose`.
- Pressing Esc while the drawer is open calls `onClose`.
- Click on the explicit ✕ button calls `onClose`.

- [ ] **Step 1: Create the test file**

Create `tests/frontend/features/workspace/ui/ChatDrawer.test.jsx`:

```jsx
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ChatDrawer } from "@src/features/workspace/ui/ChatDrawer";

vi.mock("@src/features/workspace/ui/WorkspaceChatPanel", () => ({
  WorkspaceChatPanel: ({ workspaceTitle }) => <div data-testid="chat-panel">{workspaceTitle}</div>,
}));

describe("ChatDrawer", () => {
  const baseProps = {
    workspaceTitle: "我的工作台",
    onClose: vi.fn(),
  };

  it("renders nothing when closed", () => {
    render(<ChatDrawer isOpen={false} {...baseProps} />);
    expect(screen.queryByTestId("chat-panel")).toBeNull();
  });

  it("renders the chat panel when open and forwards workspaceTitle", () => {
    render(<ChatDrawer isOpen={true} {...baseProps} />);
    expect(screen.getByTestId("chat-panel")).toHaveTextContent("我的工作台");
  });

  it("calls onClose when the backdrop is clicked", () => {
    const onClose = vi.fn();
    render(<ChatDrawer isOpen={true} {...baseProps} onClose={onClose} />);
    // Backdrop is a div with role-less click handler; find by class fragment.
    const backdrop = document.querySelector("div.fixed.inset-0.z-30");
    expect(backdrop).toBeTruthy();
    fireEvent.click(backdrop);
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("calls onClose when Esc is pressed", () => {
    const onClose = vi.fn();
    render(<ChatDrawer isOpen={true} {...baseProps} onClose={onClose} />);
    fireEvent.keyDown(window, { key: "Escape" });
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("calls onClose when the ✕ button is clicked", () => {
    const onClose = vi.fn();
    render(<ChatDrawer isOpen={true} {...baseProps} onClose={onClose} />);
    fireEvent.click(screen.getByRole("button", { name: "关闭对话" }));
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("does not register an Esc listener when closed", () => {
    const onClose = vi.fn();
    render(<ChatDrawer isOpen={false} {...baseProps} onClose={onClose} />);
    fireEvent.keyDown(window, { key: "Escape" });
    expect(onClose).not.toHaveBeenCalled();
  });
});
```

- [ ] **Step 2: Run the new tests to confirm they fail**

```bash
cd src/frontend
npx vitest run tests/frontend/features/workspace/ui/ChatDrawer.test.jsx
```

Expected: all tests fail because `ChatDrawer` doesn't exist.

- [ ] **Step 3: Create `ChatDrawer.jsx`**

Create `src/frontend/src/features/workspace/ui/ChatDrawer.jsx`:

```jsx
import { useEffect } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { X } from "lucide-react";

import { WorkspaceChatPanel } from "./WorkspaceChatPanel";

export function ChatDrawer({ isOpen, onClose, ...chatPanelProps }) {
  useEffect(() => {
    if (!isOpen) {
      return undefined;
    }
    function handleKey(event) {
      if (event.key === "Escape") {
        onClose();
      }
    }
    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
  }, [isOpen, onClose]);

  return (
    <AnimatePresence>
      {isOpen ? (
        <>
          <motion.div
            className="fixed inset-0 z-30 bg-black/20"
            onClick={onClose}
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.18 }}
            aria-hidden="true"
          />
          <motion.aside
            className="workspace-panel fixed right-0 top-0 bottom-0 z-40 w-[min(420px,90vw)] border-l border-stone-200/80 shadow-xl dark:border-stone-800"
            initial={{ x: "100%" }}
            animate={{ x: 0 }}
            exit={{ x: "100%" }}
            transition={{ type: "tween", duration: 0.22 }}
            role="dialog"
            aria-label="分析助手"
          >
            <div className="flex items-center justify-end border-b border-stone-200/70 px-4 py-2 dark:border-stone-800">
              <button
                type="button"
                onClick={onClose}
                aria-label="关闭对话"
                className="inline-flex h-8 w-8 items-center justify-center rounded-full text-stone-500 transition-colors hover:bg-stone-100 dark:text-stone-400 dark:hover:bg-stone-800"
              >
                <X size={16} />
              </button>
            </div>
            <div className="h-[calc(100%-3rem)]">
              <WorkspaceChatPanel {...chatPanelProps} />
            </div>
          </motion.aside>
        </>
      ) : null}
    </AnimatePresence>
  );
}
```

- [ ] **Step 4: Run the new tests**

```bash
cd src/frontend
npx vitest run tests/frontend/features/workspace/ui/ChatDrawer.test.jsx
```

Expected: all 6 tests pass.

- [ ] **Step 5: Commit**

```bash
cd src/frontend/..
git add src/frontend/src/features/workspace/ui/ChatDrawer.jsx \
        tests/frontend/features/workspace/ui/ChatDrawer.test.jsx
git commit --only -- src/frontend/src/features/workspace/ui/ChatDrawer.jsx \
                     tests/frontend/features/workspace/ui/ChatDrawer.test.jsx \
        -m "feat(ui): add ChatDrawer slide-out component"
```

---

## Task 8: Make chapter headers and transcript segments clickable in `WorkspaceOverviewView`

**Files:**
- Modify: `src/frontend/src/features/workspace/ui/views/WorkspaceOverviewView.jsx` (add `onSeek` prop, wrap chapter header in `<button>`, wrap each transcript segment in `<button>`)
- Create: `tests/frontend/features/workspace/ui/views/WorkspaceOverviewView.test.jsx`

**Acceptance criteria:**
- Clicking the chapter header (eyebrow + title + time badge) calls `onSeek({ seconds: chapter.start_seconds, endSeconds: chapter.end_seconds, chapterTitle: chapter.title })`.
- Clicking a transcript segment row calls `onSeek({ seconds: segment.start_seconds, endSeconds: segment.end_seconds, chapterTitle: chapter.title })`.
- Clicking on `summary` text or `key_points` does **not** call `onSeek`.
- The view renders without crashing when `onSeek` is `undefined`.
- The `selectedChapterId` highlight logic still works (visual regression test via snapshot is not required).

- [ ] **Step 1: Create the test file**

Create `tests/frontend/features/workspace/ui/views/WorkspaceOverviewView.test.jsx`:

```jsx
import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { WorkspaceOverviewView } from "@src/features/workspace/ui/views/WorkspaceOverviewView";

const summary = {
  title: "视频标题",
  core_problem: "核心问题",
  key_takeaways: ["要点 1", "要点 2"],
  chapters: [
    {
      id: "ch-1",
      title: "第一章 入门",
      start_seconds: 5,
      end_seconds: 60,
      summary: "本章讲了一些东西",
      key_points: ["点 A", "点 B"],
      transcript_segments: [
        { start_seconds: 5, end_seconds: 10, text: "段落一" },
        { start_seconds: 12, end_seconds: 18, text: "段落二" },
      ],
    },
  ],
};

const selectedVideo = { id: "v1", title: "视频标题" };
const tools = { overview: { generated: true } };

function renderView(overrides = {}) {
  const onSeek = vi.fn();
  render(
    <WorkspaceOverviewView
      ui={{ showTakeaways: true }}
      tools={tools}
      summary={summary}
      selectedVideo={selectedVideo}
      selectedChapterId={null}
      summaryLoading={false}
      isGeneratingSelectedVideo={false}
      onSeek={onSeek}
      {...overrides}
    />,
  );
  return { onSeek };
}

describe("WorkspaceOverviewView chapter + transcript clicks", () => {
  it("does not crash when onSeek is omitted", () => {
    render(
      <WorkspaceOverviewView
        ui={{ showTakeaways: true }}
        tools={tools}
        summary={summary}
        selectedVideo={selectedVideo}
        selectedChapterId={null}
        summaryLoading={false}
        isGeneratingSelectedVideo={false}
      />,
    );
    expect(screen.getByText("第一章 入门")).toBeInTheDocument();
  });

  it("chapter header click calls onSeek with chapter timestamps", () => {
    const { onSeek } = renderView();
    const chapter = screen.getByText("第一章 入门").closest("button");
    expect(chapter).toBeTruthy();
    fireEvent.click(chapter);
    expect(onSeek).toHaveBeenCalledWith({
      seconds: 5,
      endSeconds: 60,
      chapterTitle: "第一章 入门",
    });
  });

  it("transcript segment click calls onSeek with segment timestamps", () => {
    const { onSeek } = renderView();
    // Open the <details> for chapter 1
    const details = document.querySelector("details");
    fireEvent.click(within(details).getByText("查看本章原文"));
    const seg1 = within(details).getByText("段落一").closest("button");
    expect(seg1).toBeTruthy();
    fireEvent.click(seg1);
    expect(onSeek).toHaveBeenCalledWith({
      seconds: 5,
      endSeconds: 10,
      chapterTitle: "第一章 入门",
    });
  });

  it("clicking on summary or key_points does NOT call onSeek", () => {
    const { onSeek } = renderView();
    fireEvent.click(screen.getByText("本章讲了一些东西"));
    fireEvent.click(screen.getByText("点 A"));
    fireEvent.click(screen.getByText("点 B"));
    expect(onSeek).not.toHaveBeenCalled();
  });

  it("clicking on Key Takeaways bullets does NOT call onSeek", () => {
    const { onSeek } = renderView();
    fireEvent.click(screen.getByText("要点 1"));
    fireEvent.click(screen.getByText("要点 2"));
    expect(onSeek).not.toHaveBeenCalled();
  });
});
```

- [ ] **Step 2: Run the tests to confirm they fail**

```bash
cd src/frontend
npx vitest run tests/frontend/features/workspace/ui/views/WorkspaceOverviewView.test.jsx
```

Expected: most tests fail (no buttons, so `closest("button")` returns null and the click never fires `onSeek`).

- [ ] **Step 3: Edit `WorkspaceOverviewView.jsx`**

In `src/frontend/src/features/workspace/ui/views/WorkspaceOverviewView.jsx`:

1. Add `onSeek` to the function's parameter list:
   ```js
   export function WorkspaceOverviewView({
     ui,
     tools,
     summary,
     selectedVideo,
     selectedChapterId,
     summaryLoading,
     isGeneratingSelectedVideo,
     onSeek,            // ← add
   }) {
   ```

2. Replace the chapter `<article>` block. Find the existing structure (around the `(summary.chapters ?? []).map((chapter, index) => ...)` block). Restructure to:

   ```jsx
   <article
     key={chapter.id}
     id={chapter.id}
     className={`workspace-elevated-panel flex flex-col gap-4 rounded-3xl border p-5 transition-all duration-300 ${
       chapter.id === selectedChapterId
         ? "border-accent shadow-md ring-2 ring-accent/10"
         : "border-stone-200/70 dark:border-stone-800 hover:border-stone-300 dark:hover:border-stone-700 hover:bg-white dark:hover:bg-neutral-800 hover:-translate-y-0.5 hover:shadow-[0_8px_20px_rgba(15,23,42,0.05)] dark:hover:shadow-[0_8px_20px_rgba(0,0,0,0.2)]"
     }`}
   >
     <button
       type="button"
       onClick={() => onSeek?.({
         seconds: chapter.start_seconds,
         endSeconds: chapter.end_seconds,
         chapterTitle: chapter.title,
       })}
       className="flex w-full items-start justify-between gap-3 rounded-2xl px-2 py-2 text-left transition-colors hover:bg-stone-100/60 dark:hover:bg-neutral-800/60"
     >
       <div>
         <p className="mb-1.5 text-xs font-bold uppercase tracking-widest text-stone-600 dark:text-zinc-400">Chapter {index + 1}</p>
         <h3 className="text-lg font-bold leading-tight text-stone-900 dark:text-stone-100">{chapter.title}</h3>
       </div>
       <span className="shrink-0 rounded-lg bg-stone-100 px-2 py-1 text-xs font-mono font-bold text-stone-500 dark:bg-stone-900 dark:text-stone-400">
         {formatRange(chapter.start_seconds, chapter.end_seconds)}
       </span>
     </button>

     <p className="text-sm leading-relaxed text-stone-600 dark:text-stone-400">{chapter.summary}</p>

     <div className="mt-2 flex flex-col gap-2.5">
       {chapter.key_points.map((point) => (
         <div key={point} className="flex items-start gap-3">
           <span className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-accent"></span>
           <p className="text-sm leading-relaxed text-stone-700 dark:text-stone-300">{point}</p>
         </div>
       ))}
     </div>

     {chapter.transcript_segments.length ? (
       <details className="group mt-1 rounded-2xl border border-stone-200/80 bg-stone-50/80 dark:border-stone-800 dark:bg-stone-950/60">
         <summary className="flex cursor-pointer list-none items-center justify-between gap-4 px-4 py-3">
           <div className="flex items-center gap-3">
             <span className="flex h-8 w-8 items-center justify-center rounded-xl bg-white text-accent shadow-sm dark:bg-stone-900">
               <Captions size={16} />
             </span>
             <div>
               <p className="text-sm font-semibold text-stone-900 dark:text-stone-100">查看本章原文</p>
               <p className="text-xs text-stone-500 dark:text-stone-400">{chapter.transcript_segments.length} 段转写</p>
             </div>
           </div>
           <span className="text-xs font-semibold text-stone-500 dark:text-stone-400">
             {formatRange(chapter.start_seconds, chapter.end_seconds)}
           </span>
         </summary>

         <div className="border-t border-stone-200/80 px-4 py-4 dark:border-stone-800">
           <div className="flex flex-col gap-3">
             {chapter.transcript_segments.map((segment) => (
               <button
                 key={`${chapter.id}-${segment.start_seconds}-${segment.end_seconds}`}
                 type="button"
                 onClick={() => onSeek?.({
                   seconds: segment.start_seconds,
                   endSeconds: segment.end_seconds,
                   chapterTitle: chapter.title,
                 })}
                 className="block w-full rounded-2xl bg-white/90 px-3 py-3 text-left transition-colors hover:bg-accent/5 dark:bg-neutral-900 dark:hover:bg-accent/10"
               >
                 <p className="text-[11px] font-bold uppercase tracking-widest text-stone-500 dark:text-stone-400">
                   {formatTimestamp(segment.start_seconds)} - {formatTimestamp(segment.end_seconds)}
                 </p>
                 <p className="mt-2 text-sm leading-relaxed text-stone-700 dark:text-stone-300">{segment.text}</p>
               </button>
             ))}
           </div>
         </div>
       </details>
     ) : null}
   </article>
   ```

- [ ] **Step 4: Run the new tests**

```bash
cd src/frontend
npx vitest run tests/frontend/features/workspace/ui/views/WorkspaceOverviewView.test.jsx
```

Expected: all 5 tests pass.

- [ ] **Step 5: Commit**

```bash
cd src/frontend/..
git add src/frontend/src/features/workspace/ui/views/WorkspaceOverviewView.jsx \
        tests/frontend/features/workspace/ui/views/WorkspaceOverviewView.test.jsx
git commit --only -- src/frontend/src/features/workspace/ui/views/WorkspaceOverviewView.jsx \
                     tests/frontend/features/workspace/ui/views/WorkspaceOverviewView.test.jsx \
        -m "feat(overview): chapter and transcript click to seek"
```

---

## Task 9: Add 💬 button to `WorkspaceToolbar`

**Files:**
- Modify: `src/frontend/src/features/workspace/ui/WorkspaceToolbar.jsx`
- Create: `tests/frontend/features/workspace/ui/WorkspaceToolbar.test.jsx`

**Acceptance criteria:**
- A 💬 button is rendered between the workspace title block and the settings button.
- Clicking the button calls `onToggleChatDrawer`.
- When `chatDrawerOpen` is `true`, the button has the active style (background, border, shadow) matching the settings button's open state.
- The button has `aria-label="打开分析助手"` and `aria-expanded` reflects `chatDrawerOpen`.

- [ ] **Step 1: Create the test file**

Create `tests/frontend/features/workspace/ui/WorkspaceToolbar.test.jsx`:

```jsx
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { WorkspaceToolbar } from "@src/features/workspace/ui/WorkspaceToolbar";

const baseProps = {
  activeSeries: { id: "s1", title: "我的系列" },
  onEnterLibraryHome: vi.fn(),
  settingsOpen: false,
  onToggleSettingsPanel: vi.fn(),
  isSidebarOpen: true,
  onToggleSidebar: vi.fn(),
  onToggleChatDrawer: vi.fn(),
  chatDrawerOpen: false,
};

describe("WorkspaceToolbar chat button", () => {
  it("renders a chat toggle button", () => {
    render(<WorkspaceToolbar {...baseProps} />);
    expect(screen.getByRole("button", { name: "打开分析助手" })).toBeInTheDocument();
  });

  it("calls onToggleChatDrawer when the chat button is clicked", () => {
    const onToggleChatDrawer = vi.fn();
    render(<WorkspaceToolbar {...baseProps} onToggleChatDrawer={onToggleChatDrawer} />);
    fireEvent.click(screen.getByRole("button", { name: "打开分析助手" }));
    expect(onToggleChatDrawer).toHaveBeenCalledTimes(1);
  });

  it("aria-expanded reflects chatDrawerOpen", () => {
    const { rerender } = render(<WorkspaceToolbar {...baseProps} chatDrawerOpen={false} />);
    expect(screen.getByRole("button", { name: "打开分析助手" })).toHaveAttribute("aria-expanded", "false");
    rerender(<WorkspaceToolbar {...baseProps} chatDrawerOpen={true} />);
    expect(screen.getByRole("button", { name: "打开分析助手" })).toHaveAttribute("aria-expanded", "true");
  });
});
```

- [ ] **Step 2: Run the tests to confirm they fail**

```bash
cd src/frontend
npx vitest run tests/frontend/features/workspace/ui/WorkspaceToolbar.test.jsx
```

Expected: all tests fail (no `打开分析助手` button exists yet).

- [ ] **Step 3: Edit `WorkspaceToolbar.jsx`**

In `src/frontend/src/features/workspace/ui/WorkspaceToolbar.jsx`:

1. Add `MessageSquare` to the lucide-react import:
   ```js
   import { BookOpenText, MessageSquare, Settings2, PanelLeftClose, PanelLeftOpen } from "lucide-react";
   ```

2. Add the two new props to the function signature:
   ```js
   export function WorkspaceToolbar({
     activeSeries,
     onEnterLibraryHome,
     settingsOpen,
     onToggleSettingsPanel,
     isSidebarOpen,
     onToggleSidebar,
     onToggleChatDrawer,
     chatDrawerOpen,
   }) {
   ```

3. Inside the right-side `<div className="flex items-center gap-3">`, add a new button **before** the settings button:
   ```jsx
   <button
     type="button"
     className={`inline-flex items-center justify-center w-10 h-10 rounded-full transition-colors ${
       chatDrawerOpen
         ? "bg-stone-200 dark:bg-stone-800 text-stone-900 dark:text-white border border-stone-300 dark:border-stone-700 shadow-sm"
         : "text-stone-500 dark:text-zinc-400 hover:bg-stone-100 dark:hover:bg-neutral-900 hover:text-stone-900 dark:hover:text-white"
     }`}
     onClick={onToggleChatDrawer}
     title="打开分析助手"
     aria-label="打开分析助手"
     aria-expanded={chatDrawerOpen ?? false}
   >
     <MessageSquare size={18} strokeWidth={2.2} />
   </button>
   ```

- [ ] **Step 4: Run the tests**

```bash
cd src/frontend
npx vitest run tests/frontend/features/workspace/ui/WorkspaceToolbar.test.jsx
```

Expected: all 3 tests pass.

- [ ] **Step 5: Commit**

```bash
cd src/frontend/..
git add src/frontend/src/features/workspace/ui/WorkspaceToolbar.jsx \
        tests/frontend/features/workspace/ui/WorkspaceToolbar.test.jsx
git commit --only -- src/frontend/src/features/workspace/ui/WorkspaceToolbar.jsx \
                     tests/frontend/features/workspace/ui/WorkspaceToolbar.test.jsx \
        -m "feat(toolbar): add chat drawer toggle button"
```

---

## Task 10: Remove `TOOL_TILES.preview` and its `describeToolState` branch

**Files:**
- Modify: `src/frontend/src/features/workspace/ui/workspaceToolMeta.js`

**Acceptance criteria:**
- `TOOL_TILES.preview` entry is gone. The tool grid no longer offers a "媒体预览" tile.
- `getToolState(tools, "preview")` still returns `null` (the helper already handles missing entries).
- `describeToolState("preview", ...)` no longer returns "随时可查看" (it falls through to the default `getToolState`/general branch).
- The `PlaySquare` icon is no longer imported by this file (since `preview` was the only consumer).

- [ ] **Step 1: Grep for references to `preview` in the codebase**

```bash
cd src/frontend
grep -rn "TOOL_TILES.preview\|\"preview\"\|'preview'" src/features tests
```

Expected: only `workspaceToolMeta.js` references the `preview` tool ID directly. Note any other matches — they should be in tests for tool-meta behavior.

- [ ] **Step 2: Edit `workspaceToolMeta.js`**

In `src/frontend/src/features/workspace/ui/workspaceToolMeta.js`:

1. Update the lucide-react import to remove `PlaySquare`:
   ```js
   import {
     BrainCircuit,
     FileText,
     FolderKanban,
     ListChecks,
     Network,
     StickyNote,
     MessageSquare,
   } from "lucide-react";
   ```
   (Drop `PlaySquare` from the list.)

2. Remove the entire `preview` block from `TOOL_TILES`:
   ```js
   // DELETE THIS BLOCK:
   preview: {
     label: "媒体预览",
     description: "查看原始媒体内容",
     icon: PlaySquare,
     palette: "...",
     iconShell: "...",
     arrowShell: "...",
   },
   ```

3. In `describeToolState`, remove the special case:
   ```js
   // DELETE THIS BLOCK:
   if (toolId === "preview") {
     return "随时可查看";
   }
   ```

- [ ] **Step 3: Run all frontend tests**

```bash
cd src/frontend
npm test
```

Expected: same pass/fail set as before this task (no test should fail purely because of the `preview` removal — the relevant tests are the ones we'll add in Task 11 for the page rewire). If any test does fail, fix inline.

- [ ] **Step 4: Commit**

```bash
cd src/frontend/..
git add src/frontend/src/features/workspace/ui/workspaceToolMeta.js
git commit --only -- src/frontend/src/features/workspace/ui/workspaceToolMeta.js \
        -m "refactor(tool-meta): remove 媒体预览 tool tile"
```

---

## Task 11: Rewire `WorkspaceReadingPane.jsx` (drop preview props, add `onSeek`)

**Files:**
- Modify: `src/frontend/src/features/workspace/ui/WorkspaceReadingPane.jsx`
- Modify: `tests/frontend/features/workspace/ui/WorkspaceReadingPaneExport.test.jsx` (rename fixture props)

**Acceptance criteria:**
- `WorkspaceReadingPane` no longer accepts `previewUrl` or `previewSeekRequest` props.
- `WorkspaceReadingPane` accepts an `onSeek` prop and forwards it to `WorkspaceOverviewView`.
- Existing `WorkspaceReadingPane` tests pass with the updated fixture.

- [ ] **Step 1: Edit `WorkspaceReadingPane.jsx`**

In `src/frontend/src/features/workspace/ui/WorkspaceReadingPane.jsx`:

1. Remove `previewUrl` and `previewSeekRequest` from the function's parameter list. Remove the `const previewSource = ...` line (currently line 96).

2. Add `onSeek` to the function's parameter list:
   ```js
   export function WorkspaceReadingPane({
     ui,
     tools,
     chat,
     summary,
     mindmap,
     knowledgeCards,
     knowledgeCardsGenerating,
     knowledgeCardsFeedback,
     notes,
     activeSeries,
     selectedVideo,
     selectedContextType,
     selectedNode,
     selectedToolId,
     selectedChapterId,
     toolsLoading,
     summaryLoading,
     mindmapLoading,
     knowledgeCardsLoading,
     notesLoading,
     savingNote,
     isGeneratingMindmapSelectedVideo,
     isGeneratingSelectedVideo,
     onSelectTool,
     onFocusNode,
     onSeek,                  // ← add
     onGenerateMindmap,
     onGenerateKnowledgeCards,
     onClearKnowledgeCardsFeedback,
     onCreateNote,
     onUpdateNote,
     onDeleteNote,
   }) {
   ```

3. In the `<WorkspaceOverviewView ... />` JSX, add the `onSeek` prop:
   ```jsx
   {selectedToolId === "overview" ? (
     <WorkspaceOverviewView
       ui={ui}
       tools={tools}
       summary={summary}
       selectedVideo={selectedVideo}
       selectedChapterId={selectedChapterId}
       summaryLoading={summaryLoading}
       isGeneratingSelectedVideo={isGeneratingSelectedVideo}
       onSeek={onSeek}              // ← add
     />
   ) : null}
   ```

4. **Delete** the now-unused `WorkspacePreviewView` tool branch. The block:
   ```jsx
   {selectedToolId === "preview" ? (
     <WorkspacePreviewView
       previewSource={previewSource}
       previewSeekRequest={previewSeekRequest}
       previewSourceType={selectedVideo?.sourceType}
     />
   ) : null}
   ```
   should be removed entirely.

5. **Delete** the lazy import of `WorkspacePreviewView` (around line 35):
   ```js
   const WorkspacePreviewView = lazy(() =>
     import("./views/WorkspacePreviewView").then((module) => ({
       default: module.WorkspacePreviewView,
     })),
   );
   ```

- [ ] **Step 2: Update the existing test fixture**

In `tests/frontend/features/workspace/ui/WorkspaceReadingPaneExport.test.jsx`:

- Line 37: remove `previewUrl={null},`
- Line 38: remove `previewSeekRequest={null},`
- Add `onSeek={vi.fn()},` somewhere in the props.

- [ ] **Step 3: Run the reading-pane test**

```bash
cd src/frontend
npx vitest run tests/frontend/features/workspace/ui/WorkspaceReadingPaneExport.test.jsx
```

Expected: all tests pass.

- [ ] **Step 4: Commit**

```bash
cd src/frontend/..
git add src/frontend/src/features/workspace/ui/WorkspaceReadingPane.jsx \
        tests/frontend/features/workspace/ui/WorkspaceReadingPaneExport.test.jsx
git commit --only -- src/frontend/src/features/workspace/ui/WorkspaceReadingPane.jsx \
                     tests/frontend/features/workspace/ui/WorkspaceReadingPaneExport.test.jsx \
        -m "refactor(reading-pane): drop preview props, forward onSeek"
```

---

## Task 12: Rewire `WorkspacePage.jsx` (player lands in middle, drawer mounts)

**Files:**
- Modify: `src/frontend/src/features/workspace/ui/WorkspacePage.jsx`
- Create or extend: an integration-style test that mounts `WorkspacePage` and asserts the new layout

**Acceptance criteria:**
- The middle `<section>` (when `activeSeries` exists and not in playground-home) renders `<WorkspaceVideoPlayer>` instead of `<WorkspaceChatPanel>`.
- The middle shows a "选择视频以开始预览" placeholder when `activeSeries` exists but no `selectedVideo` is selected.
- `<ChatDrawer>` is mounted as a sibling of `<main>`, wired to `page.chat.drawerOpen` and `page.chat.closeDrawer`.
- `<WorkspaceToolbar>` receives `onToggleChatDrawer={page.chat.toggleDrawer}` and `chatDrawerOpen={page.chat.drawerOpen}`.
- `<WorkspaceReadingPane>` receives `onSeek={page.shell.player.seekToTime}` and no longer receives `previewUrl` / `previewSeekRequest`.
- The `WorkspacePage` itself still destructures `previewUrl` and `playerSeekRequest` (it needs them to feed the middle player).
- `WorkspacePage` no longer imports `WorkspaceChatPanel` or `WorkspacePreviewView` directly.

- [ ] **Step 1: Write a smoke test for the new layout**

Create `tests/frontend/features/workspace/ui/WorkspacePageLayout.test.jsx`:

```jsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

vi.mock("@src/features/workspace/ui/WorkspaceToolbar", () => ({
  WorkspaceToolbar: ({ onToggleChatDrawer }) => (
    <button onClick={onToggleChatDrawer} aria-label="打开分析助手">toolbar</button>
  ),
}));
vi.mock("@src/features/workspace/ui/WorkspaceLibraryPanel", () => ({
  WorkspaceLibraryPanel: () => <div>library</div>,
}));
vi.mock("@src/features/workspace/ui/WorkspaceSeriesGrid", () => ({
  WorkspaceSeriesGrid: () => <div>series-grid</div>,
}));
vi.mock("@src/features/workspace/ui/WorkspaceReadingPane", () => ({
  WorkspaceReadingPane: ({ onSeek }) => <div data-testid="reading-pane" data-on-seek={Boolean(onSeek)}>reading</div>,
}));
vi.mock("@src/features/workspace/ui/WorkspaceVideoPlayer", () => ({
  WorkspaceVideoPlayer: ({ videoSource }) => <div data-testid="video-player" data-source={videoSource}>player</div>,
}));
vi.mock("@src/features/workspace/ui/ChatDrawer", () => ({
  ChatDrawer: ({ isOpen }) => <div data-testid="chat-drawer" data-open={String(isOpen)}>drawer</div>,
}));
vi.mock("@src/features/workspace/ui/WorkspaceImportModal", () => ({
  WorkspaceImportModal: () => null,
}));
vi.mock("@src/features/workspace/ui/shared/WorkspaceConfirmDialog", () => ({
  WorkspaceConfirmDialog: () => null,
}));
vi.mock("@src/features/workspace/ui/WorkspaceLibraryHomePane", () => ({
  WorkspaceLibraryHomePane: () => null,
}));
vi.mock("@src/features/workspace/ui/WorkspaceSettingsPanel", () => ({
  WorkspaceSettingsPanel: () => null,
}));
vi.mock("@src/features/workspace/ui/WorkspaceGenerationOverlay", () => ({
  WorkspaceGenerationOverlay: () => null,
}));

import { WorkspacePage } from "@src/features/workspace/ui/WorkspacePage";

function makePage(overrides = {}) {
  return {
    shell: {
      state: {
        loading: false,
        backendReady: true,
        settingsPanelOpen: false,
        knowledgeMemorySnapshot: null,
        selectedToolId: "studio",
        selectedChapterId: null,
        toolsLoading: false,
        summaryLoading: false,
        mindmapLoading: false,
      },
      ui: {},
      library: { workspace: { title: "我的工作台" } },
      activeSeries: { id: "s1", title: "我的系列" },
      selectedVideo: { id: "v1", title: "第一讲", sourceType: "video" },
      selectedContextType: "video",
      selectedNode: null,
      previewUrl: "/api/videos/s1/v1/preview",
      playerSeekRequest: { seconds: 10, requestId: 1 },
      summary: null,
      mindmap: null,
      knowledgeCards: null,
      knowledgeCardsGenerating: false,
      knowledgeCardsFeedback: null,
      notes: null,
      tools: {},
      ...overrides.shell,
    },
    chat: {
      messages: [], sessions: [], activeSessionId: null, pending: false,
      contextUsage: null, contextUsageLoading: false,
      drawerOpen: false, toggleDrawer: vi.fn(), openDrawer: vi.fn(), closeDrawer: vi.fn(),
      startNewChat: vi.fn(), selectChatSession: vi.fn(), openSeekReference: vi.fn(), clearChat: vi.fn(), submit: vi.fn(),
      ...overrides.chat,
    },
    generation: {
      isGeneratingSummary: false, isGeneratingSeries: false, seriesGenerationQueue: null,
      isGeneratingMindmap: false, knowledgeCardsLoading: false, notesLoading: false, savingNote: false,
      fasterWhisperModels: [], fasterWhisperModelsLoading: false, ragModels: [], ragModelsLoading: false,
      downloadingRagModelKey: null, downloadingModelId: null, modelDownloadsById: {},
      modelDownloadStatus: null, modelDownloadProgress: null, modelDownloadErrorModelId: null, modelDownloadError: null,
      progress: null, snapshot: null, showOverlay: false, videoDownloadProgress: null, downloadingVideoKey: null,
      ...overrides.generation,
    },
    actions: new Proxy({}, { get: () => vi.fn() }),
  };
}

describe("WorkspacePage new layout", () => {
  it("renders the video player in the middle when a video is selected", () => {
    render(<WorkspacePage page={makePage()} />);
    const player = screen.getByTestId("video-player");
    expect(player).toBeInTheDocument();
    expect(player.getAttribute("data-source")).toBe("/api/videos/s1/v1/preview");
  });

  it("forwards onSeek to WorkspaceReadingPane", () => {
    render(<WorkspacePage page={makePage()} />);
    const pane = screen.getByTestId("reading-pane");
    expect(pane.getAttribute("data-on-seek")).toBe("true");
  });

  it("mounts ChatDrawer with isOpen reflecting chat.drawerOpen", () => {
    const page = makePage();
    page.chat.drawerOpen = true;
    render(<WorkspacePage page={page} />);
    const drawer = screen.getByTestId("chat-drawer");
    expect(drawer.getAttribute("data-open")).toBe("true");
  });
});
```

- [ ] **Step 2: Run the new tests to confirm they fail**

```bash
cd src/frontend
npx vitest run tests/frontend/features/workspace/ui/WorkspacePageLayout.test.jsx
```

Expected: most tests fail because the page still renders `WorkspaceChatPanel` in the middle and doesn't mount `ChatDrawer` at all.

- [ ] **Step 3: Edit `WorkspacePage.jsx`**

In `src/frontend/src/features/workspace/ui/WorkspacePage.jsx`:

1. Update the import block:
   - **Remove** the import of `WorkspaceChatPanel`.
   - **Add** imports for `WorkspaceVideoPlayer` and `ChatDrawer`:
     ```js
     import { WorkspaceVideoPlayer } from "./WorkspaceVideoPlayer";
     import { ChatDrawer } from "./ChatDrawer";
     ```
   - Keep the lazy imports of `WorkspaceLibraryHomePane`, `WorkspaceSettingsPanel`, `WorkspaceGenerationOverlay` (unchanged).

2. Update the destructure (around line 50-54):
   - Rename `previewSeekRequest` → `playerSeekRequest`.
   - Add `previewUrl` and `playerSeekRequest` to the destructure (they were already there; just rename the second one).

3. In the JSX, find the middle `<section>` block that currently renders `<WorkspaceChatPanel>` (around lines 260-286). Replace it with:

   ```jsx
   {activeSeries && !isPlaygroundHome ? (
     <section
       style={hasRightPane ? { width: `${layout.middleWidth}px` } : undefined}
       className="shrink-0 min-w-[320px] h-full overflow-hidden block border-r border-stone-200/70 dark:border-stone-800/90"
     >
       <div className="flex h-full items-center justify-center p-8">
         <WorkspaceStateBlock
           eyebrow="Player"
           title="选择视频以开始预览"
           description="选中左侧的视频后,这里会显示可跳转的视频播放器。"
           dashed
         />
       </div>
     </section>
   ) : null}
   ```

   Wait — this is the **placeholder** branch (no `selectedVideo`). Restructure as:
   - If `selectedVideo` is present → render `<WorkspaceVideoPlayer>`.
   - If `selectedVideo` is missing (but `activeSeries` is present and not playground-home) → render the placeholder.
   - Otherwise → render nothing.

   ```jsx
   {activeSeries && !isPlaygroundHome ? (
     <section
       style={hasRightPane ? { width: `${layout.middleWidth}px` } : undefined}
       className="shrink-0 min-w-[320px] h-full overflow-hidden block border-r border-stone-200/70 dark:border-stone-800/90"
     >
       {selectedVideo ? (
         <WorkspaceVideoPlayer
           videoSource={tools?.preview?.previewUrl ?? previewUrl}
           playerSeekRequest={playerSeekRequest}
           videoSourceType={selectedVideo?.sourceType}
         />
       ) : (
         <div className="flex h-full items-center justify-center p-8">
           <WorkspaceStateBlock
             eyebrow="Player"
             title="选择视频以开始预览"
             description="选中左侧的视频后,这里会显示可跳转的视频播放器。"
             dashed
           />
         </div>
       )}
     </section>
   ) : null}
   ```

4. In the `<WorkspaceReadingPane>` JSX (around line 327-362), find the props and:
   - Remove `previewUrl={previewUrl}` and `previewSeekRequest={previewSeekRequest}`.
   - Add `onSeek={shell.player.seekToTime}` (the prop name on the page is the `shell` object passed in `page`; read from `page.shell.player.seekToTime`).

5. In the `<WorkspaceToolbar>` JSX (around line 229-236), add:
   ```jsx
   <WorkspaceToolbar
     settingsOpen={state.settingsPanelOpen}
     activeSeries={activeSeries}
     onEnterLibraryHome={actions.enterLibraryHome}
     onToggleSettingsPanel={actions.toggleSettingsPanel}
     isSidebarOpen={isSidebarOpen}
     onToggleSidebar={() => setIsSidebarOpen(!isSidebarOpen)}
     onToggleChatDrawer={chat.toggleDrawer}
     chatDrawerOpen={chat.drawerOpen}
   />
   ```

6. **Add** the `<ChatDrawer>` as a sibling of `<main>`, right before the import modal:
   ```jsx
   <ChatDrawer
     isOpen={chat.drawerOpen}
     onClose={chat.closeDrawer}
     workspaceTitle={library?.workspace?.title}
     activeSeries={activeSeries}
     selectedVideo={selectedVideo}
     selectedContextType={selectedContextType}
     selectedToolId={state.selectedToolId}
     tools={tools}
     chatMessages={chat.messages}
     chatSessions={chat.sessions}
     activeSessionId={chat.activeSessionId}
     chatPending={chat.pending}
     contextUsage={chat.contextUsage}
     contextUsageLoading={chat.contextUsageLoading}
     ragModels={generation.ragModels}
     knowledgeMemorySnapshot={state.knowledgeMemorySnapshot}
     onSelectChatSession={chat.selectChatSession}
     onOpenSeekReference={chat.openSeekReference}
     onOpenSettings={() => actions.openSettingsPanel("network")}
     onSubmitChat={chat.submit}
   />
   ```

- [ ] **Step 4: Run the new test file**

```bash
cd src/frontend
npx vitest run tests/frontend/features/workspace/ui/WorkspacePageLayout.test.jsx
```

Expected: all 3 tests pass.

- [ ] **Step 5: Run all frontend tests**

```bash
cd src/frontend
npm test
```

Expected: every test passes. The earlier `WorkspacePreviewView` test file is gone; any test that referenced the old preview URL/field through `WorkspaceReadingPane` or `WorkspacePage` should be updated. If any fails, fix inline.

- [ ] **Step 6: Commit**

```bash
cd src/frontend/..
git add src/frontend/src/features/workspace/ui/WorkspacePage.jsx \
        tests/frontend/features/workspace/ui/WorkspacePageLayout.test.jsx
git commit --only -- src/frontend/src/features/workspace/ui/WorkspacePage.jsx \
                     tests/frontend/features/workspace/ui/WorkspacePageLayout.test.jsx \
        -m "feat(page): player lands in middle column, chat moves to drawer"
```

---

## Task 13: Final smoke pass

**Files:** none (verification only)

**Acceptance criteria:** AC-1 through AC-13 (the end-to-end list at the top) all hold.

- [ ] **Step 1: Run all frontend tests one more time**

```bash
cd src/frontend
npm test
```

Expected: every test passes. The run should be green across all `tests/frontend/**/*.test.{js,jsx}` files.

- [ ] **Step 2: Run all backend tests**

```bash
python -m pytest tests/backend
```

Expected: same pass set as before this plan started. Backend was untouched, so no backend test should have changed.

- [ ] **Step 3: Run the dev server and do a manual smoke test**

```bash
# Terminal 1 — backend
PYTHONPATH=src python -m uvicorn backend.api.app:app --host 127.0.0.1 --port 8001 --reload

# Terminal 2 — frontend
cd src/frontend && npm run dev
```

Then in the browser at `http://127.0.0.1:4173`:

- [ ] **AC-1**: Select a video, switch to AI 概况, click a chapter header. The video player (middle) seeks and starts playing.
- [ ] **AC-2**: Expand a chapter's "查看本章原文", click any transcript row. The player seeks to that row and plays.
- [ ] **AC-3**: Click a chapter's `summary` text or a `key_points` bullet. Nothing happens.
- [ ] **AC-4**: With a video selected, the middle column shows the `<video>` player. The chat is no longer in the middle.
- [ ] **AC-5**: With no video selected (e.g., on series-home), the middle shows the "选择视频以开始预览" placeholder.
- [ ] **AC-6**: Click the 💬 button on the toolbar. The chat drawer slides in from the right. Click it again — it slides out. With the drawer open, the button is in the active style.
- [ ] **AC-7**: With the drawer open, press Esc. The drawer closes. Click the backdrop. The drawer closes.
- [ ] **AC-8**: The tool grid (e.g., on AI概况's home tile) does not show 媒体预览. Try changing the URL to drive an unknown tool ID — it falls back to a placeholder.
- [ ] **AC-9**: After any click-triggered seek, the video's current time matches the requested seconds and the video is playing (or, if the user seeks past the end, it stays paused silently).
- [ ] **AC-10**: If the source is audio, the player shows the "音频文件暂不支持预览" block.
- [ ] **AC-11**: In the chat drawer, type a question. When the AI replies with citations, click a citation. The middle player seeks.
- [ ] **AC-12**: All `npm test` and `pytest` results are green.
- [ ] **AC-13**: `model/*` does not import any file under `ui/`. Run `grep -r "from \"@src/features/workspace/ui" src/frontend/src/features/workspace/model` and confirm zero hits.

- [ ] **Step 4: Final commit (only if step 1-3 required test-fixture tweaks)**

If you needed to fix anything during step 1-3, commit those fixes now. Otherwise there's nothing to commit.

---

## Self-Review Notes (filled in by author)

**Spec coverage:**
- Goal 1 (Card jump) → Task 8. ✓
- Goal 2 (Player landing) → Tasks 5, 6, 7, 9, 10, 11, 12. ✓
- Module boundaries → Task 13 step 3 AC-13. ✓
- YAGNI deletions (媒体预览, fullscreen mode) → Task 10, 12. ✓

**Type / name consistency:**
- `playerSeekRequest` is used consistently from Task 1 onward. ✓
- `player_seek_requested` is the only action name for seeks. ✓
- `chatDrawerOpen` field name is consistent across reducer, state, controller, page-model, ChatDrawer prop, WorkspaceToolbar prop, and ChatDrawer JSX. ✓
- `onSeek` prop on `WorkspaceOverviewView` and `WorkspaceReadingPane` — the only places that read it. ✓
- `videoSource` prop on `WorkspaceVideoPlayer` (renamed from `previewSource`). ✓

**Placeholder scan:** No "TBD" / "TODO" / "implement later" / "fill in details" / "add appropriate error handling" without specifics. All code shown is complete and runnable.

**Test coverage per acceptance criterion:**
- AC-1: Task 8 "chapter header click calls onSeek with chapter timestamps"
- AC-2: Task 8 "transcript segment click calls onSeek with segment timestamps"
- AC-3: Task 8 "clicking on summary or key_points does NOT call onSeek" + "clicking on Key Takeaways bullets does NOT call onSeek"
- AC-4: Task 12 "renders the video player in the middle when a video is selected"
- AC-5: Task 12 step 3 placeholder JSX; manual smoke AC-5
- AC-6: Task 9 "renders a chat toggle button" + "calls onToggleChatDrawer when the chat button is clicked" + "aria-expanded reflects chatDrawerOpen"; manual smoke AC-6
- AC-7: Task 7 "calls onClose when the backdrop is clicked" + "calls onClose when Esc is pressed"; manual smoke AC-7
- AC-8: Task 10 step 1 grep + step 3 all-tests run; manual smoke AC-8
- AC-9: Task 6 "seeks the <video> and calls play() when playerSeekRequest arrives" + "clamps the seek to the video duration"
- AC-10: Task 6 "shows an unavailable preview message for audio files"
- AC-11: Task 2 step 2 grep + Task 4 controller tests + Task 6 player test (the chain: chat dispatches `player_seek_requested` → reducer writes `playerSeekRequest` → player effect seeks)
- AC-12: Task 13 step 1+2
- AC-13: Task 13 step 3 AC-13 grep

No gaps.
