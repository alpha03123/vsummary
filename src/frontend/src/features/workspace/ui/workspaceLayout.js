export const WORKSPACE_LAYOUT_STORAGE_KEY = "video-include.workspace-layout";

export const WORKSPACE_LAYOUT_LIMITS = {
  sidebarDefaultWidth: 320,
  sidebarExpandedWidth: 380,
  sidebarMinWidth: 260,
  panelDefaultWidth: 560,
  panelMinWidth: 320,
  maxPanels: 3,
  chatDrawerDefaultWidth: 480,
  chatDrawerMinWidth: 360,
  chatDrawerMaxWidth: 960,
  chatDrawerViewportMaxShare: 0.85,
  contentMinWidth: 480,
};

export const DEFAULT_STUDIO_PANELS = ["preview::default", "overview::default"];
export const DEFAULT_SERIES_STUDIO_PANELS = ["series-overview::default"];
export const STUDIO_PANEL_TYPES = new Set([
  "studio", "preview", "overview", "mindmap", "knowledge-cards", "notes", "ai-chat", "series-overview", "series-mindmap",
]);

export function loadWorkspaceLayout(scope = "video") {
  const defaults = scope === "series" ? DEFAULT_SERIES_STUDIO_PANELS : DEFAULT_STUDIO_PANELS;
  if (typeof window === "undefined") {
    return {
      sidebarWidth: WORKSPACE_LAYOUT_LIMITS.sidebarDefaultWidth,
      studioPanels: defaults,
      panelWidths: {},
      panelTools: {},
      chatDrawerWidth: WORKSPACE_LAYOUT_LIMITS.chatDrawerDefaultWidth,
    };
  }

  try {
    const raw = window.localStorage.getItem(`${WORKSPACE_LAYOUT_STORAGE_KEY}:${scope}`);
    if (!raw) {
      return {
        sidebarWidth: WORKSPACE_LAYOUT_LIMITS.sidebarDefaultWidth,
        studioPanels: defaults,
        panelWidths: {},
        panelTools: {},
        chatDrawerWidth: WORKSPACE_LAYOUT_LIMITS.chatDrawerDefaultWidth,
      };
    }
    const parsed = JSON.parse(raw);
    return {
      sidebarWidth: normalizeDimension(parsed?.sidebarWidth, WORKSPACE_LAYOUT_LIMITS.sidebarDefaultWidth),
      studioPanels: normalizePanels(parsed?.studioPanels, scope),
      panelWidths: normalizePanelWidths(parsed?.panelWidths),
      panelTools: normalizePanelTools(parsed?.panelTools),
      chatDrawerWidth: normalizeDimension(parsed?.chatDrawerWidth, WORKSPACE_LAYOUT_LIMITS.chatDrawerDefaultWidth),
    };
  } catch {
    return {
      sidebarWidth: WORKSPACE_LAYOUT_LIMITS.sidebarDefaultWidth,
      studioPanels: defaults,
      panelWidths: {},
      panelTools: {},
      chatDrawerWidth: WORKSPACE_LAYOUT_LIMITS.chatDrawerDefaultWidth,
    };
  }
}

export function persistWorkspaceLayout(layout, scope = "video") {
  if (typeof window === "undefined") {
    return;
  }
  window.localStorage.setItem(`${WORKSPACE_LAYOUT_STORAGE_KEY}:${scope}`, JSON.stringify(layout));
}

export function clampSidebarWidth({ proposedWidth, containerWidth, hasRightPane }) {
  const limits = WORKSPACE_LAYOUT_LIMITS;
  const minimumRemaining = hasRightPane
    ? limits.panelMinWidth
    : limits.contentMinWidth;
  const maxWidth = Math.max(limits.sidebarMinWidth, containerWidth - minimumRemaining);
  return clamp(proposedWidth, limits.sidebarMinWidth, maxWidth);
}

export function clampPanelWidth({ proposedWidth, containerWidth, panelCount, sidebarWidth }) {
  const limits = WORKSPACE_LAYOUT_LIMITS;
  const maxWidth = Math.max(limits.panelMinWidth, containerWidth - sidebarWidth - Math.max(0, panelCount - 1) * limits.panelMinWidth);
  return clamp(proposedWidth, limits.panelMinWidth, maxWidth);
}

export function clampChatDrawerWidth({ proposedWidth, viewportWidth }) {
  const limits = WORKSPACE_LAYOUT_LIMITS;
  return clamp(
    proposedWidth,
    limits.chatDrawerMinWidth,
    Math.max(limits.chatDrawerMinWidth, Math.min(limits.chatDrawerMaxWidth, viewportWidth * limits.chatDrawerViewportMaxShare)),
  );
}

export function normalizePanels(value, scope = "video") {
  const defaults = scope === "series" ? DEFAULT_SERIES_STUDIO_PANELS : DEFAULT_STUDIO_PANELS;
  if (!Array.isArray(value)) return defaults;
  return value
    .filter((panel) => typeof panel === "string" && isPanelAllowedForScope(getPanelType(panel), scope))
    .slice(0, WORKSPACE_LAYOUT_LIMITS.maxPanels);
}

export function isPanelAllowedForScope(type, scope) {
  if (scope === "series") {
    return ["studio", "ai-chat", "series-overview", "series-mindmap"].includes(type);
  }
  return ["studio", "preview", "overview", "mindmap", "knowledge-cards", "notes", "ai-chat"].includes(type);
}

export function getPanelType(panelId) {
  return typeof panelId === "string" ? panelId.split("::", 1)[0] : "studio";
}

export function createPanelId(type) {
  return `${type}::${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 7)}`;
}

function normalizePanelTools(value) {
  if (!value || typeof value !== "object") return {};
  return Object.fromEntries(
    Object.entries(value).filter(([panel, tool]) => (
      STUDIO_PANEL_TYPES.has(getPanelType(panel))
      && typeof tool === "string"
      && STUDIO_PANEL_TYPES.has(tool)
    )),
  );
}

function normalizePanelWidths(value) {
  if (!value || typeof value !== "object") return {};
  return Object.fromEntries(
    Object.entries(value)
      .filter(([panel, width]) => STUDIO_PANEL_TYPES.has(getPanelType(panel)) && typeof width === "number" && Number.isFinite(width) && width > 0)
      .map(([panel, width]) => [panel, Math.round(width)]),
  );
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
