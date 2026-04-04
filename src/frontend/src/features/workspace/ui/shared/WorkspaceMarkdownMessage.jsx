import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

export function WorkspaceMarkdownMessage({ content }) {
  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      components={{
        a: ({ node: _node, ...props }) => <a {...props} target="_blank" rel="noreferrer" />,
      }}
    >
      {content}
    </ReactMarkdown>
  );
}
