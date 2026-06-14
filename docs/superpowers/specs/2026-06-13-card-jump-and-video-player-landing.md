# Spec: 章节卡片跳转 + 视频播放器上中栏

**Date:** 2026-06-13
**Status:** Draft, awaiting user review
**Scope:** Frontend only (no backend / data-model changes)

---

## 1. Goal

Two product behaviors, shipped as one feature:

1. **Card-jump:** In the **AI 概况 (overview)** view, every chapter card and every transcript segment inside a chapter can be clicked to seek the video player to the corresponding timestamp and auto-play. Other items in AI 概况 (Core Problem / Key Takeaways) are not clickable.
2. **Player landing:** The video player is the default page in the middle column (replacing the Analysis Assistant chat). Chat is moved to a right-side slide-out drawer opened from the toolbar. The "媒体预览" tool entry is removed from the tool tiles.

The chat panel's existing `onOpenSeekReference` flow (click a citation in a chat message) keeps working — it dispatches the same seek action and the player (now in the middle) responds.

## 2. Non-Goals (YAGNI)

- No chat drawer visual redesign — keep `WorkspaceChatPanel` internals untouched.
- No fullscreen "focus player" mode (was an option we discarded when removing the 媒体预览 entry).
- No keyboard shortcuts beyond Esc-to-close the drawer.
- No backend / data schema changes. We only rename state fields and action types; the wire format is identical.
- No extraction of `useVideoSeek` hook or shared `<ChapterCard>` / `<TranscriptSegmentRow>` components — the seek is currently used in exactly one place.
- No loading/skeleton state changes for chapter cards.
- No LLM / generation changes.

## 3. Architecture & Module Boundaries

The frontend is layered. Edits respect the existing layers and add at most one new file per layer.

```
model/                      (state, reducer, controller — no JSX)
  ├─ workspaceState.js      ← add chatDrawerOpen default
  ├─ workspaceReducer.js    ← rename action + state field, add 3 chat-drawer actions
  ├─ useWorkspaceController.js  ← expose onSeekToTime + onToggleChatDrawer/On/Off
  ├─ workspaceChatActions.js    ← update 2 dispatch sites to new action name
  └─ (no new files in model/)

ui/                          (presentational + container React)
  ├─ WorkspacePage.jsx       ← rewire middle column to player, mount ChatDrawer
  ├─ WorkspaceToolbar.jsx    ← add 💬 button bound to chat drawer toggle
  ├─ WorkspaceReadingPane.jsx ← drop previewUrl/previewSeekRequest props
  ├─ workspacePageModel.js   ← expose player.seekToTime + chat.drawer* props
  ├─ views/WorkspacePreviewView.jsx → renamed to WorkspaceVideoPlayer.jsx
  ├─ views/WorkspaceOverviewView.jsx ← add onSeek prop, wire chapter + transcript clicks
  ├─ ChatDrawer.jsx          ← NEW: slide-out wrapper around WorkspaceChatPanel
  └─ workspaceToolMeta.js    ← remove TOOL_TILES.preview entry
```

### 3.1 Boundary rules this design respects

| Layer | Owns | May import from | Must NOT import from |
|---|---|---|---|
| `model/` | state, actions, controller hooks, API wrapper, side effects | sibling `model/*` | `ui/*`, React DOM |
| `ui/` (page, panels, toolbar, page model) | layout, panel composition, prop wiring | `model/*`, `ui/shared/*`, `ui/views/*` | (none — top of the stack) |
| `ui/views/*` | single-purpose tool view (or single-purpose feature view) | `ui/shared/*` | `model/*` (data flows in via props), `ui/WorkspacePage*` |
| `ui/shared/*` | cross-cutting presentational primitives | (no app imports) | `model/*`, `ui/views/*` |
| `ui/WorkspacePreviewView` → `ui/WorkspaceVideoPlayer` | moved up to `ui/` (peer of `WorkspaceChatPanel`), **no longer a "view"** | `ui/shared/*` | `model/*` (seek request flows in as prop) |

Key boundary decisions:

- **`ChatDrawer` is a `ui/` component**, not a `ui/views/*` tool. The chat is a layout-level slot, not a tool page. This keeps `ui/views/*` reserved for things routed through `WorkspaceReadingPane`.
- **`WorkspaceVideoPlayer` lives in `ui/`, not `ui/views/`.** It is no longer a tool view — the player is a layout slot. Other tools reference the player by name (Player is in middle), not by selecting it.
- **State layer doesn't know about React.** The `player_seek_requested` action and `playerSeekRequest` state field are pure data. The player view subscribes via prop; the chat action dispatcher (in `workspaceChatActions.js`) and the new `onSeekToTime` controller (in `useWorkspaceController.js`) both dispatch it.
- **Overview view knows nothing about the player.** It only knows it has an `onSeek({seconds, endSeconds, chapterTitle})` prop. The page wires `onSeek` to `onSeekToTime` from the controller. This is the same pattern as `onFocusNode` today.

### 3.2 Data flow

```
[User clicks chapter card in WorkspaceOverviewView]
    │ onSeek({seconds, endSeconds, chapterTitle})
    ▼
[WorkspaceReadingPane onSeek prop] ──wired in WorkspacePage──▶
    │ pageModel.player.seekToTime(...)
    ▼
[useWorkspaceController.onSeekToTime(payload)]
    │ dispatch({type: "player_seek_requested", ...payload, requestId: <unique>})
    ▼
[workspaceReducer: state.playerSeekRequest = {seconds, endSeconds, chapterTitle, requestId, ...}]
    │
    │ (state slice exposed as `playerSeekRequest` in pageModel)
    ▼
[WorkspacePage passes playerSeekRequest to WorkspaceVideoPlayer]
    │
    │ useEffect on [playerSeekRequest, previewSource]
    ▼
[videoRef.current.currentTime = seconds]
[videoRef.current.play() .catch(() => {})]   // user-gesture: OK
```

The `requestId` is the existing dedup mechanism. Each new action gets a new `requestId`, the player effect re-runs on it, and identical consecutive seeks are not deduped (they re-apply). This is unchanged from current behavior.

## 4. State Changes (model layer)

### 4.1 Rename (mechanical)

| Old | New | Files |
|---|---|---|
| `state.previewSeekRequest` | `state.playerSeekRequest` | `workspaceReducer.js`, `workspaceState.js` |
| `dispatch("preview_seek_requested")` | `dispatch("player_seek_requested")` | `workspaceReducer.js`, `workspaceChatActions.js` (2 sites) |
| prop `previewSeekRequest` | prop `playerSeekRequest` | `WorkspacePage.jsx` (destructuring + JSX), `workspacePageModel.js` (rename field), `useWorkspaceController.js` (rename returned field) |
| controller field `previewSeekRequest` | controller field `playerSeekRequest` | `useWorkspaceController.js` (line 149) |

The shape of the seek request object itself is **unchanged**:
```ts
{ seconds: number, endSeconds: number | null, query: string, matchedText: string, chapterTitle: string, requestId: string|number }
```

### 4.2 New state fields

In `createInitialWorkspaceState` (in `workspaceState.js`):
```js
chatDrawerOpen: false,
```

The drawer is not persisted. (If we ever want it persisted, the `workspaceLayout` module already exists for this — defer until needed.)

### 4.3 New actions

In `workspaceReducer.js`:
```js
case "chat_drawer_toggled":
  return { ...state, chatDrawerOpen: !state.chatDrawerOpen };
case "chat_drawer_opened":
  return { ...state, chatDrawerOpen: true };
case "chat_drawer_closed":
  return { ...state, chatDrawerOpen: false };
```

### 4.4 Default-state resets

Find all `previewSeekRequest: null` reset sites in the reducer (4 sites: `video_selected`, `series_context_selected`, `playground_selected`, `library_home_selected` — lines 448, 478, 516, 562). Rename to `playerSeekRequest: null`. Same for `workspaceState.js:506, 591`.

These resets fire when the user switches video/series. Important: do **not** reset `chatDrawerOpen` on video switch. The drawer is shell state, not video state.

## 5. Controller Layer Changes (`useWorkspaceController.js`)

### 5.1 Rename returned field
```js
playerSeekRequest: state.playerSeekRequest,   // was: previewSeekRequest: state.previewSeekRequest
```

### 5.2 New controller functions

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

Return them in the controller's return object alongside existing `onX` functions.

**Why these live in `useWorkspaceController.js` and not a new `createWorkspacePlayerActions.js`:** the seek action is a one-line dispatch with no async work and no cross-action dependencies. The existing pattern (`onClearError`, `onSelectTool`) keeps trivial single-dispatch actions in this file; the heavier ones (`onSubmitChat`, `onGenerateVideo`) live in their own `*Actions.js`. A 4-line `onSeekToTime` doesn't need its own factory.

**Why chat drawer actions are here too:** same reason — single dispatch, no async.

## 6. Page Model Layer (`workspacePageModel.js`)

Currently exposes:
```js
shell: { state, ui, library, activeSeries, selectedVideo, ..., previewUrl, previewSeekRequest, ... }
chat:  { messages, sessions, activeSessionId, pending, ..., openSeekReference, ..., submit }
```

New shape:
```js
shell: { state, ui, library, activeSeries, selectedVideo, ...,
         previewUrl,                // unchanged — URL plumbing, shell-level
         playerSeekRequest,         // renamed from previewSeekRequest
         player: {
           seekToTime: controller.onSeekToTime,   // NEW
         },
       }
chat:  { ..., drawerOpen, toggleDrawer, openDrawer, closeDrawer   // NEW
       }
```

`previewUrl` stays in `shell` (it's URL plumbing, not player behavior). Only the **seek** request moves into `player.*`.

**Why `player.*` is a nested object instead of flat `onSeekToTime`:** the player slot may grow more behavior later (mute toggle, fullscreen, playback rate). Grouping now keeps the page prop-list readable.

**Why chat drawer lives under `chat.*`:** semantically it controls the chat panel; the toolbar and the drawer itself both read it. Co-locating with other `chat.*` props keeps it discoverable.

## 7. UI Layer

### 7.1 `WorkspacePage.jsx` (layout rewire)

The middle `<section>` currently renders `<WorkspaceChatPanel>`. Replace it with `<WorkspaceVideoPlayer>`.

- `WorkspacePage`'s own destructure still needs `previewUrl` and `playerSeekRequest` (renamed from `previewSeekRequest`) — they now feed the middle player instead of the right pane.
- Stop passing `previewUrl` and `playerSeekRequest` into `<WorkspaceReadingPane>` (it no longer needs them; see §8).
- The new `<ChatDrawer>` mounts as a sibling of `<main>` (so it can `position: fixed` over the right pane).

```jsx
<ChatDrawer
  isOpen={page.chat.drawerOpen}
  onClose={page.chat.closeDrawer}
  workspaceTitle={page.shell.library?.workspace?.title}
  activeSeries={page.shell.activeSeries}
  selectedVideo={page.shell.selectedVideo}
  selectedContextType={page.shell.selectedContextType}
  selectedToolId={page.shell.state.selectedToolId}
  tools={page.shell.tools}
  chatMessages={page.chat.messages}
  chatSessions={page.chat.sessions}
  activeSessionId={page.chat.activeSessionId}
  chatPending={page.chat.pending}
  contextUsage={page.chat.contextUsage}
  contextUsageLoading={page.chat.contextUsageLoading}
  ragModels={page.generation.ragModels}
  knowledgeMemorySnapshot={page.shell.state.knowledgeMemorySnapshot}
  onSelectChatSession={page.chat.selectChatSession}
  onOpenSeekReference={page.chat.openSeekReference}
  onOpenSettings={() => page.actions.openSettingsPanel("network")}
  onSubmitChat={page.chat.submit}
/>
```

When `chatDrawerOpen` is true, the drawer overlays the right pane (absolute, right-0, top-0, bottom-0, z above reading pane). The middle player is **not** occluded — the drawer is on the right side, ~400px wide, and the layout's middle player stays visible to its left.

When no `selectedVideo` is selected, the middle shows a placeholder:
```jsx
<div className="flex h-full items-center justify-center p-8">
  <WorkspaceStateBlock
    eyebrow="Player"
    title="选择视频以开始预览"
    description="选中左侧的视频后,这里会显示可跳转的视频播放器。"
    dashed
  />
</div>
```

This is the same pattern as the existing `isPlaygroundHome` placeholder at lines 287-297.

### 7.2 `WorkspaceVideoPlayer.jsx` (renamed from `WorkspacePreviewView.jsx`)

Internal changes from current `WorkspacePreviewView.jsx`:
- Prop names: `playerSeekRequest` (was `previewSeekRequest`), `videoSource` (was `previewSource`).
- Rename all locals accordingly.
- **Add auto-play** after seek (current code only seeks):
  ```js
  video.currentTime = nextSeconds;
  video.play().catch(() => { /* user-gesture rules; ignore failures */ });
  ```
  The play call is inside the same `loadedmetadata`-aware path. If the video was already past the end, `play()` rejects — we swallow silently. The user can press ▶ to retry.
- Keep the existing "已定位到 …" info block — it's useful feedback (chapter title, time range, query). The block reads from `playerSeekRequest`.

The `<video>` element, audio-source placeholder, and visual style stay identical to today.

### 7.3 `WorkspaceOverviewView.jsx` (new `onSeek` prop)

New prop:
```js
onSeek: PropTypes.func,   // ({seconds, endSeconds, chapterTitle}) => void
```

Wire it on:
- The chapter `<article>` wrapper. Convert the *header portion* (eyebrow + title + time badge) into a `<button>`; the body (summary, key_points, transcript details) stays in a non-clickable sibling. This way clicking the header seeks, but clicking the body text doesn't — preserves readability of summaries.
  ```jsx
  <article key={chapter.id} id={chapter.id} className="...article styles...">
    <button
      type="button"
      onClick={() => onSeek?.({
        seconds: chapter.start_seconds,
        endSeconds: chapter.end_seconds,
        chapterTitle: chapter.title,
      })}
      className="flex w-full items-start justify-between gap-3 rounded-2xl px-2 py-2 text-left cursor-pointer transition-colors hover:bg-stone-100/60 dark:hover:bg-neutral-800/60"
    >
      <div>
        <p>Chapter {index + 1}</p>
        <h3>{chapter.title}</h3>
      </div>
      <span className="...time badge (keep current classes)...">{formatRange(...)}</span>
    </button>
    <p>{chapter.summary}</p>
    ...key_points and transcript details unchanged...
  </article>
  ```
  Visual affordance: `cursor-pointer` + hover background. The article's existing border / shadow stays; only the inner header changes from `<div>` to `<button>`.

- Each transcript segment: convert the wrapping `<div>` into a `<button>`.
  ```jsx
  <button
    type="button"
    key={...}
    onClick={() => onSeek?.({
      seconds: segment.start_seconds,
      endSeconds: segment.end_seconds,
      chapterTitle: chapter.title,
    })}
    className="block w-full rounded-2xl bg-white/90 px-3 py-3 text-left cursor-pointer transition-colors hover:bg-accent/5 dark:bg-neutral-900 dark:hover:bg-accent/10"
  >
    <p>{formatTimestamp(segment.start_seconds)} - {formatTimestamp(segment.end_seconds)}</p>
    <p>{segment.text}</p>
  </button>
  ```
  `block w-full` makes the button fill the column; the inner `<p>`s are unchanged.

`onSeek` is called only when defined; the view remains usable in tests that don't supply it (e.g., existing snapshot tests).

### 7.4 `ChatDrawer.jsx` (NEW)

```jsx
// pseudocode
export function ChatDrawer({ isOpen, onClose, ...chatPanelProps }) {
  useEffect(() => {
    if (!isOpen) return;
    function onKey(e) { if (e.key === "Escape") onClose(); }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [isOpen, onClose]);

  return (
    <AnimatePresence>
      {isOpen && (
        <>
          <motion.div
            className="fixed inset-0 z-30 bg-black/20"
            onClick={onClose}
            initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
            transition={{ duration: 0.18 }}
          />
          <motion.aside
            className="fixed right-0 top-0 bottom-0 z-40 w-[min(420px,90vw)] workspace-panel border-l border-stone-200/80 dark:border-stone-800 shadow-xl"
            initial={{ x: "100%" }} animate={{ x: 0 }} exit={{ x: "100%" }}
            transition={{ type: "tween", duration: 0.22 }}
            role="dialog"
            aria-label="分析助手"
          >
            <div className="flex items-center justify-end px-4 py-2 border-b border-stone-200/70 dark:border-stone-800">
              <button
                onClick={onClose}
                aria-label="关闭对话"
                className="inline-flex h-8 w-8 items-center justify-center rounded-full text-stone-500 hover:bg-stone-100 dark:text-stone-400 dark:hover:bg-stone-800"
              >
                <X size={16} />
              </button>
            </div>
            <div className="h-[calc(100%-3rem)]">
              <WorkspaceChatPanel {...chatPanelProps} />
            </div>
          </motion.aside>
        </>
      )}
    </AnimatePresence>
  );
}
```

Note: the backdrop is `bg-black/20` (no blur). The settings overlay uses `bg-stone-900/20 dark:bg-black/50 backdrop-blur-md` because it covers the *whole* workspace; the chat drawer only covers the right side and the player must stay clearly visible on the left, so we deliberately use a lighter, non-blurring backdrop.

**Key boundary property:** `ChatDrawer` is a presentational wrapper that delegates all behavior to `WorkspaceChatPanel`. Chat internals are not changed. The drawer owns: mount/unmount animation, escape-key handling, click-outside-to-close, close button.

Framer Motion's `<AnimatePresence>` is already a project dependency (used in `WorkspacePage.jsx`).

### 7.5 `WorkspaceToolbar.jsx`

Add a chat icon button between the workspace title and the settings button. Mirror the existing settings button's styling so the row stays balanced:

```jsx
<button
  ref={chatButtonRef}
  className={`inline-flex items-center justify-center w-10 h-10 rounded-full transition-colors ${chatDrawerOpen ? "bg-stone-200 dark:bg-stone-800 text-stone-900 dark:text-white border border-stone-300 dark:border-stone-700 shadow-sm" : "text-stone-500 dark:text-zinc-400 hover:bg-stone-100 dark:hover:bg-neutral-900 hover:text-stone-900 dark:hover:text-white"}`}
  onClick={onToggleChatDrawer}
  title="打开分析助手"
  aria-label="打开分析助手"
  aria-expanded={chatDrawerOpen ?? false}
>
  <MessageSquare size={18} strokeWidth={2.2} />
</button>
```

Two new props on `WorkspaceToolbar`: `onToggleChatDrawer` (required) and `chatDrawerOpen` (optional, used to set the active styling and `aria-expanded`). The `lucide-react` `MessageSquare` icon is already a project dependency; import it from `lucide-react`.

### 7.6 `workspaceToolMeta.js`

Remove the entire `TOOL_TILES.preview` block (lines 56-60). The `getToolState` and `resolveToolMeta` helpers stay — they handle missing entries gracefully.

Also remove the `isAudioSource`-specific `describeToolState` branch for "preview" (line 95-97). Or leave it as dead code with a comment "kept for backward compat" — better: just remove it, it's pure data.

## 8. Wiring the new prop in `WorkspaceReadingPane.jsx`

The reading pane no longer needs `previewUrl` or `previewSeekRequest` props (they were only used by the now-removed `WorkspacePreviewView` tool). Drop them from the destructure.

It **does** need to receive and forward `onSeek` to `WorkspaceOverviewView` (and any other tool view that wants to seek — but for now only overview uses it).

Prop change in `WorkspaceReadingPane`:
- Remove: `previewUrl`, `previewSeekRequest` (and the `previewSource` derived value at line 96)
- Add: `onSeek` (forwarded to `WorkspaceOverviewView` only)
- Pass to `WorkspaceOverviewView`: `onSeek={onSeek}`

## 9. Error Handling

| Failure | Behavior |
|---|---|
| `onSeek` called with non-finite `seconds` | `useWorkspaceController.onSeekToTime` returns early (no dispatch) |
| `playerSeekRequest.seconds` is not finite in the player effect | Defensive `Number.isFinite` check (already present in current code) |
| `video.play()` rejects (e.g., seeked past end, autoplay blocked) | `.catch(() => {})` — silent. User can press ▶. |
| Audio source | `WorkspaceVideoPlayer` shows the existing "音频文件暂不支持预览" placeholder; seek effect is a no-op (existing behavior preserved) |
| Chat drawer open + user navigates to a different video | Drawer stays open; the player in middle updates with the new video's URL via `videoSource` prop change; chat panel receives the new `selectedVideo` prop |
| Chat drawer open + user opens settings | Settings overlay (`z-50`) covers the drawer (`z-40`); user closes settings → drawer is still there. No special handling needed. |
| Old `previewUrl` in `tools.preview.previewUrl` not present | Falls back to the controller-computed `previewUrl` (current behavior preserved) |

## 10. Testing

Frontend (vitest). Backend: no changes → no backend tests.

### 10.1 Unit / reducer
- `workspaceReducer` tests:
  - `player_seek_requested` writes the new field (rename); the state shape carries the same data as before.
  - `chat_drawer_toggled` flips `chatDrawerOpen`.
  - `chat_drawer_opened` / `_closed` set the field.
  - Video/series switch resets `playerSeekRequest: null` (renamed); does **not** reset `chatDrawerOpen`.

### 10.2 Controller
- `useWorkspaceController.onSeekToTime`:
  - dispatches the right action with `seconds`, `endSeconds`, `chapterTitle`, `requestId`.
  - early-returns on non-finite input.
- Chat drawer controllers dispatch the right actions.

### 10.3 Components (RTL)
- `WorkspaceVideoPlayer`:
  - Given a new `playerSeekRequest`, calls `video.currentTime = seconds` and `video.play()` (use a mocked video ref / jsdom does not implement HTMLMediaElement.play — use a `vi.fn()` stub).
  - The existing audio-source behavior is preserved.
- `WorkspaceOverviewView`:
  - Clicking a chapter header fires `onSeek({seconds, endSeconds, chapterTitle})`.
  - Clicking a transcript segment fires `onSeek` with that segment's timestamps.
  - Clicking on key_points (which live outside the clickable button) does **not** fire `onSeek`.
- `ChatDrawer`:
  - Renders nothing when `isOpen={false}`.
  - Renders `WorkspaceChatPanel` with the passed props when `isOpen={true}`.
  - Calls `onClose` on backdrop click and on Esc.
- `WorkspaceToolbar`:
  - Clicking the 💬 button calls `onToggleChatDrawer`.

### 10.4 Regression
- Existing chat-panel tests (the `openSeekReference` flow) keep passing — the action name change is the only edit; the chat panel itself is unchanged.
- The "media preview" tool-tile tests (if any) need to be deleted or updated to assert the tile no longer exists.

## 11. Out-of-scope / follow-up

These are explicitly **not** part of this spec; flagged for future work:

- "Player fullscreen / focus mode" — would re-add a 媒体预览 tool entry; not wanted now.
- Persisting `chatDrawerOpen` across reloads — defer until users complain.
- Keyboard shortcuts beyond Esc.
- Snackbar / toast on seek failure.

## 12. Open questions for the user

None. The user has already answered all clarifying questions (layout = C-with-drawer-A, cards = chapter+transcript, draw-er-UX = A, 媒体预览 = delete).
