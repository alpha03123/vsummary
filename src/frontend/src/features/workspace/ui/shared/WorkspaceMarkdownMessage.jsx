import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

function normalizeCitations(citations) {
  if (!Array.isArray(citations)) {
    return [];
  }
  return citations.filter((citation) => citation && typeof citation === "object" && typeof citation.id === "string");
}

function injectCitationLinks(content, citations) {
  if (typeof content !== "string" || !content) {
    return "";
  }
  if (!citations.length) {
    return content;
  }
  const citationIds = new Set(citations.map((citation) => citation.id));
  return content.replace(/\[(\d+)\]/g, (match, citationId) => {
    if (!citationIds.has(citationId)) {
      return match;
    }
    return `[${citationId}](#citation-${citationId})`;
  });
}

function formatCitationSlot(slot) {
  if (!slot || typeof slot !== "object") {
    return "";
  }
  const parts = [];
  if (typeof slot.video_title === "string" && slot.video_title.trim()) {
    parts.push(slot.video_title.trim());
  } else if (typeof slot.video_id === "string" && slot.video_id.trim()) {
    parts.push(slot.video_id.trim());
  }
  if (typeof slot.chapter_id === "string" && slot.chapter_id.trim()) {
    parts.push(slot.chapter_id.trim());
  }
  if (typeof slot.start_seconds === "number") {
    const end = typeof slot.end_seconds === "number" ? `-${Math.round(slot.end_seconds)}s` : "";
    parts.push(`${Math.round(slot.start_seconds)}s${end}`);
  }
  return parts.join(" · ");
}

function buildCitationPreview(citation) {
  if (!citation || typeof citation !== "object") {
    return null;
  }
  const firstSlot = Array.isArray(citation.slots) ? citation.slots.find((slot) => slot && typeof slot === "object") : null;
  const detail = formatCitationSlot(firstSlot);
  const text = typeof firstSlot?.text === "string" ? firstSlot.text.trim() : "";
  return {
    title: `[${citation.id}] ${citation.label}`,
    sourceType: typeof citation.source_type === "string" ? citation.source_type : "",
    detail,
    text,
  };
}

export function WorkspaceMarkdownMessage({ content, citations = null }) {
  const normalizedCitations = normalizeCitations(citations);
  const renderedContent = injectCitationLinks(content, normalizedCitations);
  const citationMap = new Map(normalizedCitations.map((citation) => [citation.id, citation]));
  return (
    <div className="flex flex-col gap-4">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          a: ({ node: _node, href, children, ...props }) => {
            if (typeof href === "string" && href.startsWith("#citation-")) {
              const citationId = href.replace("#citation-", "");
              const preview = buildCitationPreview(citationMap.get(citationId));
              return (
                <span className="group relative inline-flex align-baseline">
                  <a
                    {...props}
                    href={href}
                    onClick={(event) => event.preventDefault()}
                    className="font-semibold text-sky-600 hover:text-sky-700 hover:underline focus:text-sky-700 focus:outline-none dark:text-sky-300 dark:hover:text-sky-200 dark:focus:text-sky-200"
                  >
                    [{children}]
                  </a>
                  {preview ? (
                    <span className="pointer-events-none absolute left-1/2 top-full z-20 mt-2 hidden w-72 -translate-x-1/2 rounded-2xl border border-stone-200/90 bg-white/95 px-4 py-3 text-left text-xs text-stone-600 shadow-xl shadow-stone-900/10 backdrop-blur group-hover:block group-focus-within:block dark:border-stone-700 dark:bg-stone-950/95 dark:text-stone-300 dark:shadow-black/30">
                      <span className="block font-semibold text-stone-900 dark:text-stone-100">{preview.title}</span>
                      {preview.sourceType ? (
                        <span className="mt-1 block text-[11px] uppercase tracking-wide text-stone-400 dark:text-stone-500">{preview.sourceType}</span>
                      ) : null}
                      {preview.detail ? (
                        <span className="mt-2 block text-[11px] text-stone-500 dark:text-stone-400">{preview.detail}</span>
                      ) : null}
                      {preview.text ? (
                        <span className="mt-2 block leading-relaxed text-stone-600 dark:text-stone-300">{preview.text}</span>
                      ) : null}
                    </span>
                  ) : null}
                </span>
              );
            }
            return (
              <a
                {...props}
                href={href}
                target="_blank"
                rel="noreferrer"
                className="text-sky-600 hover:text-sky-700 hover:underline dark:text-sky-300 dark:hover:text-sky-200"
              >
                {children}
              </a>
            );
          },
        }}
      >
        {renderedContent}
      </ReactMarkdown>
    </div>
  );
}
