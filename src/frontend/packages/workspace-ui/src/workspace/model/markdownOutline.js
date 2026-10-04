import { toString } from "mdast-util-to-string";
import remarkGfm from "remark-gfm";
import remarkParse from "remark-parse";
import { unified } from "unified";

const parser = unified().use(remarkParse).use(remarkGfm);

export function buildMarkdownOutline(content, idPrefix) {
  if (typeof content !== "string" || !content.trim() || !idPrefix) {
    return { items: [], headingIds: {} };
  }

  const headingIds = {};
  const items = [];
  const tree = parser.parse(content);
  visit(tree, (node) => {
    if (node.type !== "heading" || (node.depth !== 2 && node.depth !== 3)) {
      return;
    }
    const label = toString(node).trim();
    const line = node.position?.start?.line;
    if (!label || !Number.isInteger(line)) {
      return;
    }
    const id = `${idPrefix}-${line}`;
    headingIds[line] = id;
    items.push({ id, label, depth: node.depth });
  });
  return { items, headingIds };
}

function visit(node, callback) {
  if (!node || typeof node !== "object") {
    return;
  }
  callback(node);
  if (Array.isArray(node.children)) {
    node.children.forEach((child) => visit(child, callback));
  }
}
