function asRecord(value, label) {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new Error(`${label} 格式不正确。`);
  }
  return value;
}

function asString(value, label) {
  if (typeof value !== "string" || !value.trim()) {
    throw new Error(`${label} 缺失或不是有效文本。`);
  }
  return value.trim();
}

function asOptionalString(value) {
  return typeof value === "string" ? value.trim() : "";
}

function asNumber(value, label) {
  if (typeof value !== "number" || Number.isNaN(value)) {
    throw new Error(`${label} 不是有效数字。`);
  }
  return value;
}

function asStringList(value, label) {
  if (!Array.isArray(value)) {
    throw new Error(`${label} 不是有效列表。`);
  }
  return value.map((item, index) => asString(item, `${label}[${index}]`));
}

function asVideoCard(value, label) {
  const record = asRecord(value, label);
  return {
    id: asString(record.id, `${label}.id`),
    title: asString(record.title, `${label}.title`),
    sourceName: asString(record.source_name, `${label}.source_name`),
    processed: Boolean(record.processed),
    status: asString(record.status, `${label}.status`),
  };
}

function asTool(value, label) {
  const record = asRecord(value, label);
  return {
    id: asString(record.id, `${label}.id`),
    title: asString(record.title, `${label}.title`),
    available: Boolean(record.available),
    generated: Boolean(record.generated),
    status: asString(record.status, `${label}.status`),
    previewUrl: typeof record.preview_url === "string" ? record.preview_url : null,
  };
}

function asChapterCard(value, label) {
  const record = asRecord(value, label);
  return {
    id: asString(record.id, `${label}.id`),
    title: asString(record.title, `${label}.title`),
    summary: asString(record.summary, `${label}.summary`),
    keyPoints: Array.isArray(record.key_points) ? asStringList(record.key_points, `${label}.key_points`) : [],
    startSeconds: typeof record.start_seconds === "number" ? record.start_seconds : null,
    endSeconds: typeof record.end_seconds === "number" ? record.end_seconds : null,
    kind: asString(record.kind, `${label}.kind`),
  };
}

function asKnowledgeCardSourceRef(value, label) {
  const record = asRecord(value, label);
  return {
    chapterId: typeof record.chapter_id === "string" ? record.chapter_id : null,
    startSeconds: typeof record.start_seconds === "number" ? record.start_seconds : null,
    endSeconds: typeof record.end_seconds === "number" ? record.end_seconds : null,
    quote: asString(record.quote, `${label}.quote`),
  };
}

function asKnowledgeCard(value, label) {
  const record = asRecord(value, label);
  return {
    id: asString(record.id, `${label}.id`),
    title: asString(record.title, `${label}.title`),
    kind: asString(record.kind, `${label}.kind`),
    summary: asString(record.summary, `${label}.summary`),
    details: asString(record.details, `${label}.details`),
    tags: Array.isArray(record.tags) ? asStringList(record.tags, `${label}.tags`) : [],
    keywords: Array.isArray(record.keywords) ? asStringList(record.keywords, `${label}.keywords`) : [],
    sourceRefs: Array.isArray(record.source_refs)
      ? record.source_refs.map((item, index) => asKnowledgeCardSourceRef(item, `${label}.source_refs[${index}]`))
      : [],
    relatedCardIds: Array.isArray(record.related_card_ids)
      ? asStringList(record.related_card_ids, `${label}.related_card_ids`)
      : [],
  };
}

function asNote(value, label) {
  const record = asRecord(value, label);
  return {
    id: asString(record.id, `${label}.id`),
    title: asString(record.title, `${label}.title`),
    content: asString(record.content, `${label}.content`),
    source: asString(record.source, `${label}.source`),
    createdAt: asString(record.created_at, `${label}.created_at`),
    updatedAt: asString(record.updated_at, `${label}.updated_at`),
  };
}

function asChapter(value, label) {
  const record = asRecord(value, label);
  return {
    id: asString(record.id, `${label}.id`),
    title: asString(record.title, `${label}.title`),
    summary: asString(record.summary, `${label}.summary`),
    key_points: asStringList(record.key_points, `${label}.key_points`),
    start_seconds: asNumber(record.start_seconds, `${label}.start_seconds`),
    end_seconds: asNumber(record.end_seconds, `${label}.end_seconds`),
    transcript_segments: asTranscriptSegments(record.transcript_segments, `${label}.transcript_segments`),
  };
}

function asTranscriptSegments(value, label) {
  if (value == null) {
    return [];
  }
  if (!Array.isArray(value)) {
    throw new Error(`${label} 不是有效列表。`);
  }

  return value.map((item, index) => {
    const record = asRecord(item, `${label}[${index}]`);
    return {
      start_seconds: asNumber(record.start_seconds, `${label}[${index}].start_seconds`),
      end_seconds: asNumber(record.end_seconds, `${label}[${index}].end_seconds`),
      text: asString(record.text, `${label}[${index}].text`),
    };
  });
}

function asMindmapNode(value, label) {
  const record = asRecord(value, label);
  const children = record.children ?? [];
  if (!Array.isArray(children)) {
    throw new Error(`${label}.children 不是有效列表。`);
  }

  return {
    id: asString(record.id, `${label}.id`),
    title: asString(record.title, `${label}.title`),
    summary: asOptionalString(record.summary),
    start_seconds: typeof record.start_seconds === "number" ? record.start_seconds : 0,
    end_seconds: typeof record.end_seconds === "number" ? record.end_seconds : 0,
    children: children.map((child, index) => asMindmapNode(child, `${label}.children[${index}]`)),
  };
}

export function toWorkspaceSummary(payload) {
  const record = asRecord(payload, "summary");

  if (!Array.isArray(record.chapters)) {
    throw new Error("summary.chapters 不是有效列表。");
  }

  return {
    title: asString(record.title, "summary.title"),
    one_sentence_summary: asOptionalString(record.one_sentence_summary),
    core_problem: asOptionalString(record.core_problem),
    key_takeaways: Array.isArray(record.key_takeaways)
      ? asStringList(record.key_takeaways, "summary.key_takeaways")
      : [],
    chapters: record.chapters.map((chapter, index) => asChapter(chapter, `summary.chapters[${index}]`)),
  };
}

export function toWorkspaceMindmap(payload) {
  return asMindmapNode(asRecord(payload, "mindmap"), "mindmap");
}

export function toWorkspaceTools(payload) {
  const record = asRecord(payload, "tools");
  return {
    seriesId: asString(record.series_id, "tools.series_id"),
    videoId: asString(record.video_id, "tools.video_id"),
    overview: asTool(record.overview, "tools.overview"),
    knowledgeCards: asTool(record.knowledge_cards, "tools.knowledge_cards"),
    mindmap: asTool(record.mindmap, "tools.mindmap"),
    notes: asTool(record.notes, "tools.notes"),
    preview: asTool(record.preview, "tools.preview"),
    aiTodo: asOptionalString(record.ai_todo),
  };
}

export function toWorkspaceCards(payload) {
  const record = asRecord(payload, "cards");
  if (!Array.isArray(record.cards)) {
    throw new Error("cards.cards 不是有效列表。");
  }
  return {
    seriesId: asString(record.series_id, "cards.series_id"),
    videoId: asString(record.video_id, "cards.video_id"),
    title: asString(record.title, "cards.title"),
    cards: record.cards.map((item, index) => asChapterCard(item, `cards.cards[${index}]`)),
  };
}

export function toWorkspaceKnowledgeCards(payload) {
  const record = asRecord(payload, "knowledgeCards");
  if (!Array.isArray(record.cards)) {
    throw new Error("knowledgeCards.cards 不是有效列表。");
  }
  return {
    seriesId: asString(record.series_id, "knowledgeCards.series_id"),
    videoId: asString(record.video_id, "knowledgeCards.video_id"),
    title: asString(record.title, "knowledgeCards.title"),
    cards: record.cards.map((item, index) => asKnowledgeCard(item, `knowledgeCards.cards[${index}]`)),
  };
}

export function toWorkspaceNotes(payload) {
  const record = asRecord(payload, "notes");
  if (!Array.isArray(record.notes)) {
    throw new Error("notes.notes 不是有效列表。");
  }
  return {
    seriesId: asString(record.series_id, "notes.series_id"),
    videoId: asString(record.video_id, "notes.video_id"),
    title: asString(record.title, "notes.title"),
    notes: record.notes.map((item, index) => asNote(item, `notes.notes[${index}]`)),
  };
}

export function toWorkspaceNote(payload) {
  return asNote(payload, "note");
}

export function toWorkspaceLibrary(payload) {
  const record = asRecord(payload, "library");
  const workspace = asRecord(record.workspace, "library.workspace");
  const series = record.series ?? [];

  if (!Array.isArray(series)) {
    throw new Error("library.series 不是有效列表。");
  }

  return {
    workspace: {
      id: asString(workspace.id, "library.workspace.id"),
      title: asString(workspace.title, "library.workspace.title"),
    },
    series: series.map((item, index) => {
      const recordItem = asRecord(item, `library.series[${index}]`);
      const recordVideos = recordItem.videos ?? [];
      if (!Array.isArray(recordVideos)) {
        throw new Error(`library.series[${index}].videos 不是有效列表。`);
      }
      return {
        id: asString(recordItem.id, `library.series[${index}].id`),
        title: asString(recordItem.title, `library.series[${index}].title`),
        videos: recordVideos.map((video, videoIndex) =>
          asVideoCard(video, `library.series[${index}].videos[${videoIndex}]`),
        ),
      };
    }),
  };
}
