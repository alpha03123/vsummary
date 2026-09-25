export const WORKSPACE_LAYOUT_STORAGE_KEY = "video-include.workspace-layout";

export const WORKSPACE_LAYOUT_LIMITS = {
  sidebarDefaultWidth: 320,
  sidebarExpandedWidth: 380,
  sidebarMinWidth: 260,
  panelMinWidth: 320,
  chatDrawerDefaultWidth: 480,
  chatDrawerMinWidth: 360,
  chatDrawerMaxWidth: 960,
  chatDrawerViewportMaxShare: 0.85,
  contentMinWidth: 480,
};

export const DEFAULT_STUDIO_PANELS = ["preview::default", "ai-summary::default"];
export const DEFAULT_SERIES_STUDIO_PANELS = ["ai-chat::default"];
export const STUDIO_PANEL_TYPES = new Set([
  "studio", "preview", "overview", "ai-summary", "mindmap", "knowledge-cards", "notes", "ai-chat", "series-overview", "series-mindmap",
]);

export function loadWorkspaceLayout(scope = "video") {
  const defaults = createDefaultWorkspaceLayout(scope);
  if (typeof window === "undefined") {
    return defaults;
  }

  try {
    const raw = window.localStorage.getItem(`${WORKSPACE_LAYOUT_STORAGE_KEY}:${scope}`);
    if (!raw) {
      return defaults;
    }
    return normalizeWorkspaceLayout(JSON.parse(raw), scope);
  } catch {
    return defaults;
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

export function clampChatDrawerWidth({ proposedWidth, viewportWidth }) {
  const limits = WORKSPACE_LAYOUT_LIMITS;
  return clamp(
    proposedWidth,
    limits.chatDrawerMinWidth,
    Math.max(limits.chatDrawerMinWidth, Math.min(limits.chatDrawerMaxWidth, viewportWidth * limits.chatDrawerViewportMaxShare)),
  );
}

export function getStudioPanelIds(layout) {
  if (typeof layout === "string") {
    return [layout];
  }
  if (!layout || typeof layout !== "object") {
    return [];
  }
  if (layout.type === "tabs") {
    return Array.isArray(layout.tabs) ? layout.tabs.filter((panelId) => typeof panelId === "string") : [];
  }
  if (layout.type !== "split" || !Array.isArray(layout.children)) {
    return [];
  }
  return layout.children.flatMap(getStudioPanelIds);
}

export function splitStudioPanel(layout, targetPanelId, newPanelId, direction) {
  if (!isSplitDirection(direction) || !targetPanelId || !newPanelId) {
    return layout;
  }
  return insertPanelAdjacentToTarget(layout, targetPanelId, newPanelId, direction) ?? layout;
}

export function removeStudioPanel(layout, panelId, scope, panelTools) {
  return normalizeStudioLayout(removePanelFromLayout(layout, panelId), scope, panelTools);
}

export function getPanelType(panelId) {
  return typeof panelId === "string" ? panelId.split("::", 1)[0] : "studio";
}

export function createPanelId(type) {
  return `${type}::${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 7)}`;
}

export function isPanelAllowedForScope(type, scope) {
  if (scope === "series") {
    return ["studio", "ai-chat", "series-overview", "series-mindmap"].includes(type);
  }
  return ["studio", "preview", "overview", "ai-summary", "mindmap", "knowledge-cards", "notes", "ai-chat"].includes(type);
}

function createDefaultWorkspaceLayout(scope) {
  const panels = scope === "series" ? DEFAULT_SERIES_STUDIO_PANELS : DEFAULT_STUDIO_PANELS;
  return {
    version: 2,
    sidebarWidth: WORKSPACE_LAYOUT_LIMITS.sidebarDefaultWidth,
    studioLayout: createBalancedStudioLayout(panels),
    panelTools: {},
    chatDrawerWidth: WORKSPACE_LAYOUT_LIMITS.chatDrawerDefaultWidth,
  };
}

function normalizeWorkspaceLayout(value, scope) {
  const defaults = createDefaultWorkspaceLayout(scope);
  const panelTools = normalizePanelTools(value?.panelTools);
  const legacyPanels = normalizeLegacyPanels(value?.studioPanels, scope, panelTools);
  const studioLayout = normalizeStudioLayout(
    value?.studioLayout ?? createBalancedStudioLayout(legacyPanels),
    scope,
    panelTools,
  ) ?? defaults.studioLayout;
  const panelIds = new Set(getStudioPanelIds(studioLayout));

  return {
    version: 2,
    sidebarWidth: normalizeDimension(value?.sidebarWidth, defaults.sidebarWidth),
    studioLayout,
    panelTools: Object.fromEntries(Object.entries(panelTools).filter(([panelId]) => panelIds.has(panelId))),
    chatDrawerWidth: normalizeDimension(value?.chatDrawerWidth, defaults.chatDrawerWidth),
  };
}

function normalizeLegacyPanels(value, scope, panelTools) {
  const defaults = scope === "series" ? DEFAULT_SERIES_STUDIO_PANELS : DEFAULT_STUDIO_PANELS;
  if (!Array.isArray(value)) {
    return defaults;
  }
  const seen = new Set();
  return value.filter((panelId) => {
    if (typeof panelId !== "string" || seen.has(panelId)) {
      return false;
    }
    const toolId = panelTools[panelId] ?? getPanelType(panelId);
    if (!isPanelAllowedForScope(toolId, scope)) {
      return false;
    }
    seen.add(panelId);
    return true;
  });
}

function createBalancedStudioLayout(panels) {
  if (panels.length === 0) {
    return null;
  }
  if (panels.length === 1) {
    return panels[0];
  }
  return {
    type: "split",
    direction: "row",
    children: panels,
  };
}

function normalizeStudioLayout(value, scope, panelTools, seen = new Set()) {
  if (typeof value === "string") {
    const toolId = panelTools[value] ?? getPanelType(value);
    if (!seen.has(value) && isPanelAllowedForScope(toolId, scope)) {
      seen.add(value);
      return value;
    }
    return null;
  }
  if (!value || typeof value !== "object") {
    return null;
  }
  if (value.type === "tabs") {
    const tabs = Array.isArray(value.tabs)
      ? value.tabs.map((panelId) => normalizeStudioLayout(panelId, scope, panelTools, seen)).filter(Boolean)
      : [];
    if (tabs.length === 0) {
      return null;
    }
    if (tabs.length === 1) {
      return tabs[0];
    }
    return {
      type: "tabs",
      tabs,
      activeTabIndex: clampIndex(value.activeTabIndex, tabs.length),
    };
  }
  if (value.type !== "split" || !isSplitDirection(value.direction) || !Array.isArray(value.children)) {
    return null;
  }
  const children = value.children
    .map((child) => normalizeStudioLayout(child, scope, panelTools, seen))
    .filter(Boolean);
  if (children.length === 0) {
    return null;
  }
  if (children.length === 1) {
    return children[0];
  }
  const splitPercentages = normalizeSplitPercentages(value.splitPercentages, children.length);
  return {
    type: "split",
    direction: value.direction,
    children,
    ...(splitPercentages ? { splitPercentages } : {}),
  };
}

function insertPanelAdjacentToTarget(node, targetPanelId, newPanelId, direction) {
  if (typeof node === "string") {
    return node === targetPanelId
      ? createSplit(direction, [node, newPanelId])
      : node;
  }
  if (!node || typeof node !== "object" || node.type === "tabs") {
    return node;
  }
  const directChildIndex = node.children.findIndex((child) => child === targetPanelId);
  if (directChildIndex >= 0 && node.direction === direction) {
    const children = [...node.children];
    children.splice(directChildIndex + 1, 0, newPanelId);
    const splitPercentages = splitPercentageAt(node.splitPercentages, directChildIndex, children.length);
    return { ...node, children, ...(splitPercentages ? { splitPercentages } : {}) };
  }
  return {
    ...node,
    children: node.children.map((child) => insertPanelAdjacentToTarget(child, targetPanelId, newPanelId, direction)),
  };
}

function removePanelFromLayout(node, panelId) {
  if (typeof node === "string") {
    return node === panelId ? null : node;
  }
  if (!node || typeof node !== "object") {
    return null;
  }
  if (node.type === "tabs") {
    const tabs = node.tabs.filter((tab) => tab !== panelId);
    if (tabs.length === 0) {
      return null;
    }
    if (tabs.length === 1) {
      return tabs[0];
    }
    return { ...node, tabs, activeTabIndex: clampIndex(node.activeTabIndex, tabs.length) };
  }
  const children = node.children
    .map((child) => removePanelFromLayout(child, panelId))
    .filter(Boolean);
  if (children.length === 0) {
    return null;
  }
  if (children.length === 1) {
    return children[0];
  }
  const splitPercentages = normalizeSplitPercentages(node.splitPercentages, children.length);
  return { ...node, children, ...(splitPercentages ? { splitPercentages } : {}) };
}

function createSplit(direction, children) {
  return { type: "split", direction, children };
}

function splitPercentageAt(percentages, index, childCount) {
  const existing = normalizeSplitPercentages(percentages, childCount - 1);
  if (!existing) {
    return null;
  }
  const shared = existing[index] / 2;
  const next = [...existing];
  next.splice(index, 1, shared, shared);
  return next;
}

function normalizePanelTools(value) {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return {};
  }
  return Object.fromEntries(
    Object.entries(value).filter(([panel, tool]) => (
      STUDIO_PANEL_TYPES.has(getPanelType(panel))
      && typeof tool === "string"
      && STUDIO_PANEL_TYPES.has(tool)
    )),
  );
}

function normalizeSplitPercentages(value, childCount) {
  if (!Array.isArray(value) || value.length !== childCount || value.some((item) => typeof item !== "number" || !Number.isFinite(item) || item <= 0)) {
    return null;
  }
  const total = value.reduce((sum, item) => sum + item, 0);
  return total > 0 ? value.map((item) => (item / total) * 100) : null;
}

function normalizeDimension(value, fallback) {
  if (typeof value === "number" && Number.isFinite(value) && value > 0) {
    return Math.round(value);
  }
  return fallback;
}

function clampIndex(value, length) {
  return typeof value === "number" && Number.isInteger(value)
    ? Math.min(Math.max(value, 0), length - 1)
    : 0;
}

function isSplitDirection(value) {
  return value === "row" || value === "column";
}

function clamp(value, min, max) {
  return Math.min(Math.max(Math.round(value), min), max);
}
