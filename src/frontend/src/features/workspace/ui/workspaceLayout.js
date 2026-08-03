export const WORKSPACE_LAYOUT_STORAGE_KEY = "video-include.workspace-layout";

export const WORKSPACE_LAYOUT_LIMITS = {
  sidebarDefaultWidth: 320,
  sidebarExpandedWidth: 380,
  sidebarMinWidth: 260,
  chatDrawerDefaultWidth: 480,
  chatDrawerMinWidth: 360,
  chatDrawerMaxWidth: 960,
  chatDrawerViewportMaxShare: 0.85,
  middleDefaultWidth: 640,
  middleMinWidth: 320,
  middleMaxShare: 0.72,
  rightMinWidth: 320,
  contentMinWidth: 480,
};

export function loadWorkspaceLayout() {
  if (typeof window === "undefined") {
    return {
      sidebarWidth: WORKSPACE_LAYOUT_LIMITS.sidebarDefaultWidth,
      chatDrawerWidth: WORKSPACE_LAYOUT_LIMITS.chatDrawerDefaultWidth,
      middleWidth: WORKSPACE_LAYOUT_LIMITS.middleDefaultWidth,
    };
  }

  try {
    const raw = window.localStorage.getItem(WORKSPACE_LAYOUT_STORAGE_KEY);
    if (!raw) {
      return {
        sidebarWidth: WORKSPACE_LAYOUT_LIMITS.sidebarDefaultWidth,
        chatDrawerWidth: WORKSPACE_LAYOUT_LIMITS.chatDrawerDefaultWidth,
        middleWidth: WORKSPACE_LAYOUT_LIMITS.middleDefaultWidth,
      };
    }
    const parsed = JSON.parse(raw);
    return {
      sidebarWidth: normalizeDimension(parsed?.sidebarWidth, WORKSPACE_LAYOUT_LIMITS.sidebarDefaultWidth),
      chatDrawerWidth: normalizeDimension(parsed?.chatDrawerWidth, WORKSPACE_LAYOUT_LIMITS.chatDrawerDefaultWidth),
      middleWidth: normalizeDimension(parsed?.middleWidth, WORKSPACE_LAYOUT_LIMITS.middleDefaultWidth),
    };
  } catch {
    return {
      sidebarWidth: WORKSPACE_LAYOUT_LIMITS.sidebarDefaultWidth,
      chatDrawerWidth: WORKSPACE_LAYOUT_LIMITS.chatDrawerDefaultWidth,
      middleWidth: WORKSPACE_LAYOUT_LIMITS.middleDefaultWidth,
    };
  }
}

export function persistWorkspaceLayout(layout) {
  if (typeof window === "undefined") {
    return;
  }
  window.localStorage.setItem(WORKSPACE_LAYOUT_STORAGE_KEY, JSON.stringify(layout));
}

export function clampSidebarWidth({ proposedWidth, containerWidth, hasRightPane }) {
  const limits = WORKSPACE_LAYOUT_LIMITS;
  const minimumRemaining = hasRightPane
    ? limits.middleMinWidth + limits.rightMinWidth
    : limits.contentMinWidth;
  const maxWidth = Math.max(limits.sidebarMinWidth, containerWidth - minimumRemaining);
  return clamp(proposedWidth, limits.sidebarMinWidth, maxWidth);
}

export function clampMiddleWidth({ proposedWidth, containerWidth, sidebarWidth }) {
  const limits = WORKSPACE_LAYOUT_LIMITS;
  const availableWidth = containerWidth - sidebarWidth;
  const maxWidth = Math.max(
    limits.middleMinWidth,
    Math.min(
      availableWidth - limits.rightMinWidth,
      availableWidth * limits.middleMaxShare,
    ),
  );
  return clamp(proposedWidth, limits.middleMinWidth, maxWidth);
}

export function clampChatDrawerWidth({ proposedWidth, viewportWidth }) {
  const limits = WORKSPACE_LAYOUT_LIMITS;
  const maxWidth = Math.max(
    limits.chatDrawerMinWidth,
    Math.min(limits.chatDrawerMaxWidth, viewportWidth * limits.chatDrawerViewportMaxShare),
  );
  return clamp(proposedWidth, limits.chatDrawerMinWidth, maxWidth);
}

function normalizeDimension(value, fallback) {
  if (typeof value === "number" && Number.isFinite(value) && value > 0) {
    return Math.round(value);
  }
  return fallback;
}

function clamp(value, min, max) {
  return Math.min(Math.max(Math.round(value), min), max);
}
