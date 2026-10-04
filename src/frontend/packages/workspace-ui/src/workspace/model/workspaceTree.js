export function findNodeById(root, targetId) {
  if (!root || !targetId) {
    return null;
  }

  let match = null;
  walkTree(root, (node) => {
    if (node.id === targetId) {
      match = node;
      return true;
    }
    return false;
  });
  return match;
}

export function findChapterForNode(chapters, node) {
  return (
    chapters.find(
      (chapter) =>
        node.start_seconds >= chapter.start_seconds && node.end_seconds <= chapter.end_seconds,
    ) ?? null
  );
}

function walkTree(root, visitor, ancestors = []) {
  if (!root) {
    return false;
  }
  if (visitor(root, ancestors)) {
    return true;
  }
  return (root.children ?? []).some((child) => walkTree(child, visitor, [...ancestors, root]));
}
