import { BrainCircuit, RefreshCw } from "lucide-react";

import { CopyToClipboardButton } from "../shared/CopyToClipboardButton";
import { WorkspaceFeedbackBanner } from "../shared/WorkspaceFeedbackBanner";
import { WorkspaceStateBlock } from "../shared/WorkspaceStateBlock";
import { WorkspaceGenerationStatus } from "../shared/WorkspaceGenerationStatus";

export function buildCardMarkdown(card) {
  const lines = [];

  lines.push(`## ${card?.title ?? ""}`);
  lines.push("");

  const meta = [];
  if (card?.kind) {
    meta.push(`- 类型：${card.kind}`);
  }
  if (Array.isArray(card?.tags) && card.tags.length) {
    const validTags = card.tags.filter((t) => typeof t === "string");
    if (validTags.length) meta.push(`- 标签：${validTags.join("、")}`);
  }
  if (Array.isArray(card?.keywords) && card.keywords.length) {
    const validKeywords = card.keywords.filter((k) => typeof k === "string");
    if (validKeywords.length) meta.push(`- 关键词：${validKeywords.join("、")}`);
  }
  if (meta.length) {
    lines.push(...meta);
    lines.push("");
  }

  if (card?.summary) {
    lines.push("### 摘要");
    lines.push(card.summary);
    lines.push("");
  }

  if (card?.details) {
    lines.push("### 详情");
    lines.push(card.details);
  }

  while (lines.length && lines[lines.length - 1] === "") {
    lines.pop();
  }

  return lines.join("\n");
}

export function WorkspaceKnowledgeCardsView({
  tools,
  knowledgeCards,
  knowledgeCardsGenerating,
  knowledgeCardsGenerationProgress,
  knowledgeCardsFeedback,
  knowledgeCardsLoading,
  onGenerateKnowledgeCards,
  onClearKnowledgeCardsFeedback,
}) {
  const hasKnowledgeCards = Boolean(knowledgeCards?.cards?.length);

  if (knowledgeCardsGenerating) {
    return (
      <WorkspaceStateBlock
        title="正在生成知识卡片"
      >
        <WorkspaceGenerationStatus snapshot={knowledgeCardsGenerationProgress} label="正在提炼知识卡片" />
      </WorkspaceStateBlock>
    );
  }

  if (!tools?.knowledgeCards.available) {
    return (
      <WorkspaceStateBlock
        title="需要先生成 AI 概括"
        description="知识卡片从 AI 概括里提炼，请先生成 AI 概括。"
      />
    );
  }

  if (!tools.knowledgeCards.generated) {
    return (
      <WorkspaceStateBlock
        title="知识卡片尚未生成"
        description="把视频里的要点做成一张张卡片。"
      >
        <button
          type="button"
          onClick={onGenerateKnowledgeCards}
          className="inline-flex items-center gap-2 rounded-2xl bg-stone-900 px-5 py-3 text-sm font-semibold text-white transition hover:bg-accent dark:bg-white dark:text-black"
        >
          <BrainCircuit size={16} strokeWidth={2.2} />
          生成知识卡片
        </button>
      </WorkspaceStateBlock>
    );
  }

  if (knowledgeCardsLoading) {
    return (
      <WorkspaceStateBlock
        title="载入知识卡片"
        description="正在读取已生成的知识卡片。"
        loading
      />
    );
  }

  if (!hasKnowledgeCards) {
    return (
      <div className="flex flex-col gap-4">
        <WorkspaceFeedbackBanner feedback={knowledgeCardsFeedback} onDismiss={onClearKnowledgeCardsFeedback} />
        <WorkspaceStateBlock
          title="还没有可展示的卡片"
          description="这个视频能提炼的要点太少，可以稍后重新生成试试。"
        >
          <button
            type="button"
            onClick={onGenerateKnowledgeCards}
            className="inline-flex items-center gap-2 rounded-xl border border-accent/30 bg-accent/8 px-4 py-2.5 text-sm font-semibold text-accent transition-colors hover:bg-accent/14"
          >
            <RefreshCw size={16} strokeWidth={2.2} />
            重新生成知识卡片
          </button>
        </WorkspaceStateBlock>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-4">
      <WorkspaceFeedbackBanner feedback={knowledgeCardsFeedback} onDismiss={onClearKnowledgeCardsFeedback} />
      <div className="flex justify-end">
        <button
          type="button"
          onClick={onGenerateKnowledgeCards}
          className="inline-flex items-center gap-2 rounded-xl border border-stone-200 bg-white px-3 py-2 text-xs font-semibold text-stone-600 transition-colors hover:border-accent/30 hover:bg-accent/8 hover:text-accent dark:border-stone-700 dark:bg-neutral-900 dark:text-stone-300"
        >
          <RefreshCw size={14} strokeWidth={2.2} />
          重新生成知识卡片
        </button>
      </div>
      <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
        {knowledgeCards.cards.map((card) => (
          <article
            key={card.id}
            className="workspace-elevated-panel rounded-4xl border p-6 transition-all hover:-translate-y-0.5 hover:border-stone-300 dark:hover:border-white/16"
          >
            <div className="flex items-start justify-between gap-3">
              <div>
                <p className="text-xs font-bold uppercase tracking-widest text-stone-600 dark:text-stone-400">{card.kind}</p>
                <h3 className="mt-2 text-lg font-bold text-stone-900 dark:text-stone-100">{card.title}</h3>
              </div>
              <CopyToClipboardButton text={buildCardMarkdown(card)} className="shrink-0" />
            </div>
            <p className="mt-4 text-sm leading-relaxed text-stone-600 dark:text-stone-400">{card.summary}</p>
            <p className="mt-3 text-sm leading-relaxed text-stone-700 dark:text-stone-300">{card.details}</p>
            {card.tags?.length ? (
              <div className="mt-4 flex flex-wrap gap-2">
                {card.tags.map((tag) => (
                  <span
                    key={`${card.id}-${tag}`}
                    className="rounded-full border border-stone-200/70 bg-stone-100/80 px-3 py-1 text-xs font-semibold text-stone-600 dark:border-stone-700 dark:bg-stone-800 dark:text-stone-300"
                  >
                    {tag}
                  </span>
                ))}
              </div>
            ) : null}
          </article>
        ))}
      </div>
    </div>
  );
}
