import { useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import rehypeKatex from "rehype-katex";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";

const CITATION_PREVIEW_TEXT_MAX_LENGTH = 300;
const CITATION_PREVIEW_WIDTH = 360;
const CITATION_PREVIEW_ESTIMATED_MAX_HEIGHT = 260;
const CITATION_PREVIEW_GAP = 8;
const CITATION_PREVIEW_VIEWPORT_PADDING = 16;
const THINK_BLOCK_PATTERN = /<think>([\s\S]*?)(?:<\/think>|$)/gi;

function normalizeCitations(citations) {
  if (!Array.isArray(citations)) {
    return [];
  }
  return citations.filter((citation) => citation && typeof citation === "object" && typeof citation.id === "string");
}

function truncateCitationText(text) {
  if (typeof text !== "string") {
    return "";
  }
  const normalizedText = text.trim();
  if (normalizedText.length <= CITATION_PREVIEW_TEXT_MAX_LENGTH) {
    return normalizedText;
  }
  return `${normalizedText.slice(0, CITATION_PREVIEW_TEXT_MAX_LENGTH).trimEnd()}...`;
}

function injectCitationLinks(content, citations) {
  if (typeof content !== "string" || !content) {
    return "";
  }
  if (!citations.length) {
    return content;
  }
  const citationIds = new Set(citations.map((citation) => citation.id));
  return content.replace(/\[(\d+(?:\.\d+)?)\]/g, (match, citationId) => {
    if (!citationIds.has(citationId)) {
      return match;
    }
    return `[${citationId}](#citation-${citationId})`;
  });
}

function normalizeMathDelimiters(content) {
  if (typeof content !== "string" || !content) {
    return "";
  }
  return content
    .replace(/\\\[([\s\S]*?)\\\]/g, (_match, expression) => `\n\n$$\n${expression.trim()}\n$$\n\n`)
    .replace(/\\\(([\s\S]*?)\\\)/g, (_match, expression) => `$${expression.trim()}$`)
    .replace(/^[ \t]*\[\s*([^\]\n]*(?:\\[A-Za-z]+|[A-Za-z]\([^)]*\)|[A-Za-z]\s*[=+\-*/^]|[=+\-*/^]\s*[A-Za-z]|[{}_^])[^\]\n]*)\s*\][ \t]*$/gm, (_match, expression) => `$$\n${expression.trim()}\n$$`);
}

function splitThinkBlocks(content) {
  if (typeof content !== "string" || !content) {
    return [];
  }
  const parts = [];
  let cursor = 0;
  let match;
  THINK_BLOCK_PATTERN.lastIndex = 0;
  while ((match = THINK_BLOCK_PATTERN.exec(content)) !== null) {
    if (match.index > cursor) {
      parts.push({ type: "answer", content: content.slice(cursor, match.index) });
    }
    parts.push({ type: "think", content: match[1] ?? "" });
    cursor = THINK_BLOCK_PATTERN.lastIndex;
  }
  if (cursor < content.length) {
    parts.push({ type: "answer", content: content.slice(cursor) });
  }
  return parts.filter((part) => part.content.trim());
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
  if (typeof slot.url === "string" && slot.url.trim()) {
    parts.push(slot.url.trim());
  }
  return parts.join(" · ");
}

function buildCitationPreview(citation) {
  if (!citation || typeof citation !== "object") {
    return null;
  }
  const slots = Array.isArray(citation.slots) ? citation.slots.filter((slot) => slot && typeof slot === "object") : [];
  const firstSlot = slots[0] ?? null;
  const textSlot = slots.find((slot) => typeof slot.text === "string" && slot.text.trim()) ?? firstSlot;
  const detail = formatCitationSlot(firstSlot);
  const text = truncateCitationText(textSlot?.text);
  const url = typeof firstSlot?.url === "string" ? firstSlot.url.trim() : "";
  return {
    title: `[${citation.id}] ${citation.label}`,
    sourceType: typeof citation.source_type === "string" ? citation.source_type : "",
    detail,
    text,
    url,
  };
}

function buildCitationSeekReference(citation) {
  if (!citation || typeof citation !== "object") {
    return null;
  }
  const slots = Array.isArray(citation.slots) ? citation.slots.filter((slot) => slot && typeof slot === "object") : [];
  const videoSlot = slots.find((slot) => slot.target_type === "video" && typeof slot.start_seconds === "number");
  if (!videoSlot) {
    return null;
  }
  const transcriptSlot = slots.find((slot) => slot.target_type === "transcript" && typeof slot.text === "string" && slot.text.trim());
  const matchedText = transcriptSlot?.text?.trim() ?? "";
  return {
    seconds: videoSlot.start_seconds,
    endSeconds: typeof videoSlot.end_seconds === "number" ? videoSlot.end_seconds : null,
    matchedText,
    chapterTitle: typeof videoSlot.video_title === "string" ? videoSlot.video_title.trim() : "",
    query: "",
  };
}

function resolveCitationPreviewPosition(anchor) {
  const rect = anchor.getBoundingClientRect();
  const viewportWidth = window.innerWidth || document.documentElement.clientWidth || CITATION_PREVIEW_WIDTH;
  const viewportHeight = window.innerHeight || document.documentElement.clientHeight || CITATION_PREVIEW_ESTIMATED_MAX_HEIGHT;
  const maxLeft = Math.max(
    CITATION_PREVIEW_VIEWPORT_PADDING,
    viewportWidth - CITATION_PREVIEW_WIDTH - CITATION_PREVIEW_VIEWPORT_PADDING,
  );
  const belowTop = rect.bottom + CITATION_PREVIEW_GAP;
  const aboveTop = rect.top - CITATION_PREVIEW_ESTIMATED_MAX_HEIGHT - CITATION_PREVIEW_GAP;
  const shouldShowBelow = viewportHeight - belowTop >= CITATION_PREVIEW_ESTIMATED_MAX_HEIGHT;
  const preferredLeft = rect.left;
  return {
    left: Math.min(Math.max(preferredLeft, CITATION_PREVIEW_VIEWPORT_PADDING), maxLeft),
    top: shouldShowBelow ? belowTop : Math.max(CITATION_PREVIEW_VIEWPORT_PADDING, aboveTop),
    anchorTop: rect.top,
    placement: shouldShowBelow ? "below" : "above",
  };
}

function CitationPreviewCard({ preview, position }) {
  const cardRef = useRef(null);
  const [measuredTop, setMeasuredTop] = useState(position.top);

  useLayoutEffect(() => {
    if (position.placement !== "above" || cardRef.current === null) {
      setMeasuredTop(position.top);
      return;
    }
    const cardHeight = cardRef.current.getBoundingClientRect().height;
    setMeasuredTop(Math.max(
      CITATION_PREVIEW_VIEWPORT_PADDING,
      position.anchorTop - cardHeight - CITATION_PREVIEW_GAP,
    ));
  }, [position]);

  return createPortal(
    <span
      ref={cardRef}
      className="pointer-events-none fixed z-50 w-[22.5rem] rounded-2xl border border-stone-200/90 bg-white/95 px-4 py-3 text-left text-xs text-stone-600 shadow-xl shadow-stone-900/10 backdrop-blur dark:border-stone-700 dark:bg-stone-950/95 dark:text-stone-300 dark:shadow-black/30"
      style={{ left: `${position.left}px`, top: `${measuredTop}px` }}
    >
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
      {preview.url ? (
        <span className="mt-2 block break-all text-[11px] text-accent">{preview.url}</span>
      ) : null}
    </span>,
    document.body,
  );
}

function CitationLink({ href, children, preview, seekReference, onOpenSeekReference, ...props }) {
  const [position, setPosition] = useState(null);

  function showPreview(event) {
    if (!preview) {
      return;
    }
    setPosition(resolveCitationPreviewPosition(event.currentTarget));
  }

  function hidePreview() {
    setPosition(null);
  }

  function handleClick(event) {
    event.preventDefault();
    if (seekReference) {
      onOpenSeekReference?.(seekReference);
    }
  }

  return (
    <span className="inline-flex align-baseline">
      <a
        {...props}
        href={href}
        onClick={handleClick}
        onMouseEnter={showPreview}
        onMouseLeave={hidePreview}
        onFocus={showPreview}
        onBlur={hidePreview}
        className="citation-marker ml-1 inline-flex h-5 min-w-5 items-center justify-center rounded-full bg-stone-900/10 px-1.5 text-xs font-semibold leading-none text-stone-900 no-underline shadow-none transition-colors hover:bg-stone-900/16 focus:bg-stone-900/16 focus:outline-none dark:bg-white/12 dark:text-white dark:hover:bg-white/18 dark:focus:bg-white/18"
      >
        {children}
      </a>
      {preview && position ? <CitationPreviewCard preview={preview} position={position} /> : null}
    </span>
  );
}

function ThinkBlock({ content }) {
  const [expanded, setExpanded] = useState(true);
  return (
    <section className="rounded-2xl border border-stone-200 bg-stone-50/70 px-4 py-3 text-sm text-stone-600 dark:border-stone-800 dark:bg-stone-900/60 dark:text-stone-300">
      <button
        type="button"
        aria-expanded={expanded}
        onClick={() => setExpanded((value) => !value)}
        className="flex w-full items-center justify-between text-left text-xs font-bold uppercase tracking-wide text-stone-500 dark:text-stone-400"
      >
        思考过程
        <span aria-hidden="true">{expanded ? "收起" : "展开"}</span>
      </button>
      {expanded ? <div className="mt-3 whitespace-pre-wrap leading-6">{content.trim()}</div> : null}
    </section>
  );
}

function MarkdownSegment({ content, citations, onOpenSeekReference }) {
  const normalizedCitations = normalizeCitations(citations);
  const renderedContent = injectCitationLinks(normalizeMathDelimiters(content), normalizedCitations);
  const citationMap = new Map(normalizedCitations.map((citation) => [citation.id, citation]));
  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm, remarkMath]}
      rehypePlugins={[rehypeKatex]}
      components={{
        a: ({ node: _node, href, children, ...props }) => {
          if (typeof href === "string" && href.startsWith("#citation-")) {
            const citationId = href.replace("#citation-", "");
            const citation = citationMap.get(citationId);
            const preview = buildCitationPreview(citation);
            const seekReference = buildCitationSeekReference(citation);
            return (
              <CitationLink
                {...props}
                href={href}
                preview={preview}
                seekReference={seekReference}
                onOpenSeekReference={onOpenSeekReference}
              >
                {children}
              </CitationLink>
            );
          }
          return (
            <a
              {...props}
              href={href}
              target="_blank"
              rel="noreferrer"
              className="text-accent hover:text-accent/80 hover:underline"
            >
              {children}
            </a>
          );
        },
      }}
    >
      {renderedContent}
    </ReactMarkdown>
  );
}

export function WorkspaceMarkdownMessage({ content, citations = null, onOpenSeekReference }) {
  const parts = splitThinkBlocks(content);
  return (
    <div className="flex flex-col gap-4">
      {(parts.length ? parts : [{ type: "answer", content }]).map((part, index) => (
        part.type === "think" ? (
          <ThinkBlock key={`${part.type}-${index}`} content={part.content} />
        ) : (
          <MarkdownSegment
            key={`${part.type}-${index}`}
            content={part.content}
            citations={citations}
            onOpenSeekReference={onOpenSeekReference}
          />
        )
      ))}
    </div>
  );
}
