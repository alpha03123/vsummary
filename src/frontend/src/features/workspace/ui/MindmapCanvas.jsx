export function MindmapCanvas({ root, selectedNodeId, onSelectNode }) {
  if (!root) {
    return <div className="empty-note">当前没有导图数据。</div>;
  }

  function renderNode(node, depth) {
    const hasChildren = node.children && node.children.length > 0;
    const isRoot = depth === 0;

    return (
      <li key={node.id}>
        <div className="css-tree-node-wrapper">
          <button
            type="button"
            className={`mindmap-node depth-${depth}${node.id === selectedNodeId ? " is-active" : ""}`}
            onClick={() => onSelectNode(node)}
          >
            <span className="mindmap-label">{node.title}</span>
            {!isRoot && hasChildren ? <span className="mindmap-badge">{node.children.length}</span> : null}
          </button>
        </div>
        {hasChildren ? (
          <ul>
            {node.children.map((child) => renderNode(child, depth + 1))}
          </ul>
        ) : null}
      </li>
    );
  }

  return (
    <div className="mindmap-scroll">
      <div className="css-tree">
        <ul>{renderNode(root, 0)}</ul>
      </div>
    </div>
  );
}
