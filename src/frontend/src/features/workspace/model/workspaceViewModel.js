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
  };
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

export function unwrapSummaryPayload(payload) {
  if (payload && typeof payload === "object" && payload.summary && typeof payload.summary === "object") {
    return payload.summary;
  }
  return payload;
}

export function toWorkspaceSummary(payload) {
  const record = asRecord(unwrapSummaryPayload(payload), "summary");

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
    mindmap: record.mindmap == null ? null : asMindmapNode(record.mindmap, "summary.mindmap"),
  };
}

export function toWorkspaceLibrary(payload) {
  const record = asRecord(payload, "library");
  const workspace = asRecord(record.workspace, "library.workspace");
  const series = record.series ?? [];
  const videos = record.videos ?? [];

  if (!Array.isArray(series)) {
    throw new Error("library.series 不是有效列表。");
  }
  if (!Array.isArray(videos)) {
    throw new Error("library.videos 不是有效列表。");
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
    videos: videos.map((video, index) => asVideoCard(video, `library.videos[${index}]`)),
  };
}
