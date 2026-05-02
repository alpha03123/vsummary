import { BrainCircuit } from "lucide-react";

import { WorkspaceFeedbackBanner } from "../shared/WorkspaceFeedbackBanner";
import { WorkspaceStateBlock } from "../shared/WorkspaceStateBlock";

export function WorkspaceKnowledgeCardsView({
  tools,
  knowledgeCards,
  knowledgeCardsGenerating,
  knowledgeCardsFeedback,
  knowledgeCardsLoading,
  onGenerateKnowledgeCards,
}) {
  const hasKnowledgeCards = Boolean(knowledgeCards?.cards?.length);

  if (knowledgeCardsGenerating) {
    return (
      <WorkspaceStateBlock
        eyebrow="Knowledge Cards"
        title="正在生成知识卡片"
        description="正在把视频里的核心概念抽成可复习、可检索、可串联的知识原子。"
        loading
      >
        <div className="mt-6 h-2 overflow-hidden rounded-full bg-stone-200/80 dark:bg-stone-800">
          <div className="h-full w-1/2 animate-pulse rounded-full bg-accent" />
        </div>
        <p className="mt-3 text-xs text-stone-500 dark:text-stone-400">生成完成后会自动展示结果。</p>
      </WorkspaceStateBlock>
    );
  }

  if (!tools?.knowledgeCards.available) {
    return (
      <WorkspaceStateBlock
        eyebrow="Knowledge Cards"
        title="需要先生成 AI 概况"
        description="知识卡片依赖 AI 概况的结构化理解，没有概况就没有抽取基础。"
      />
    );
  }

  if (!tools.knowledgeCards.generated) {
    return (
      <WorkspaceStateBlock
        eyebrow="Knowledge Cards"
        title="知识卡片尚未生成"
        description="这里展示的是独立的知识资产，不是章节摘要换皮。生成后会落盘到 `knowledge_cards.json`。"
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
        eyebrow="Knowledge Cards"
        title="载入知识卡片"
        description="正在读取已生成的知识卡片。"
        loading
      />
    );
  }

  if (!hasKnowledgeCards) {
    return (
      <div className="flex flex-col gap-4">
        <WorkspaceFeedbackBanner feedback={knowledgeCardsFeedback} />
        <WorkspaceStateBlock
          eyebrow="Knowledge Cards"
          title="还没有可展示的卡片"
          description="当前视频还没有抽取出足够稳定的知识原子，可稍后重新生成。"
        />
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-4">
      <WorkspaceFeedbackBanner feedback={knowledgeCardsFeedback} />
      <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
        {knowledgeCards.cards.map((card) => (
          <article
            key={card.id}
            className="workspace-elevated-panel rounded-[2rem] border p-6 transition-all hover:-translate-y-0.5 hover:border-stone-300 dark:hover:border-white/16"
          >
            <div>
              <p className="text-[10px] font-bold uppercase tracking-widest text-stone-500 dark:text-stone-400">{card.kind}</p>
              <h3 className="mt-2 text-lg font-bold text-stone-900 dark:text-stone-100">{card.title}</h3>
            </div>
            <p className="mt-4 text-sm leading-relaxed text-stone-600 dark:text-stone-400">{card.summary}</p>
            <p className="mt-3 text-sm leading-relaxed text-stone-700 dark:text-stone-300">{card.details}</p>
            {card.tags.length ? (
              <div className="mt-4 flex flex-wrap gap-2">
                {card.tags.map((tag) => (
                  <span
                    key={tag}
                    className="rounded-full border border-stone-200/70 bg-stone-100/80 px-3 py-1 text-[11px] font-semibold text-stone-600 dark:border-stone-700 dark:bg-stone-800 dark:text-stone-300"
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
