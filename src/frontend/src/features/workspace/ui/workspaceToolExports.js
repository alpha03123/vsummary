export function buildWorkspaceToolExportActions({ activeSeries, notes, summary, toolId, selectedVideo, tools }) {
  if (toolId === "series-overview") {
    return buildSeriesExportActions(activeSeries);
  }
  if (toolId === "series-mindmap" && activeSeries) {
    return buildMindmapExportActions(`/api/series/${encodeURIComponent(activeSeries.id)}/mindmap/export`);
  }
  if (!activeSeries || !selectedVideo) {
    return [];
  }
  if (toolId === "overview") {
    const overviewGenerated = tools?.overview?.generated === true;
    const screenshotsGenerated = Array.isArray(summary?.chapters) && summary.chapters.some((chapter) => chapter.image_url);
    return [
      { href: videoExportUrl(activeSeries.id, selectedVideo.id, "summary"), enabled: overviewGenerated, label: "概况导出", disabledReason: "AI 概况生成后才能导出" },
      { href: videoExportUrl(activeSeries.id, selectedVideo.id, "summary-with-screenshots.zip"), enabled: screenshotsGenerated, label: "概况与截图导出", disabledReason: "AI 概况和章节截图生成后才能导出" },
      { href: videoExportUrl(activeSeries.id, selectedVideo.id, "transcript"), enabled: overviewGenerated, label: "转写导出", disabledReason: "AI 概况生成后才能导出" },
      { href: videoExportUrl(activeSeries.id, selectedVideo.id, "subtitles.srt"), enabled: selectedVideo.hasTranscript === true, label: "SRT 字幕导出", disabledReason: "获取字幕后才能导出" },
      { href: videoExportUrl(activeSeries.id, selectedVideo.id, "mixed"), enabled: overviewGenerated, label: "混合导出", disabledReason: "AI 概况生成后才能导出" },
    ];
  }
  if (toolId === "knowledge-cards") {
    return [{ href: videoExportUrl(activeSeries.id, selectedVideo.id, "knowledge-cards"), enabled: tools?.knowledgeCards?.generated === true, label: "知识卡片导出", disabledReason: "知识卡片生成后才能导出" }];
  }
  if (toolId === "mindmap") {
    return buildMindmapExportActions(`/api/videos/${encodeURIComponent(activeSeries.id)}/${encodeURIComponent(selectedVideo.id)}/mindmap/export`);
  }
  if (toolId === "notes") {
    return [{ href: videoExportUrl(activeSeries.id, selectedVideo.id, "notes"), enabled: Boolean(notes?.notes?.length), label: "笔记导出", disabledReason: "有笔记后才能导出" }];
  }
  return [];
}

function buildMindmapExportActions(baseUrl) {
  return [
    { href: `${baseUrl}?format=md`, enabled: true, label: "Markdown (.md)" },
    { href: `${baseUrl}?format=html`, enabled: true, label: "HTML (.html)" },
  ];
}

function buildSeriesExportActions(activeSeries) {
  if (!activeSeries) return [];
  return [
    { href: seriesExportUrl(activeSeries.id, "mixed"), enabled: true, label: "AI 概括混合导出" },
    { href: seriesExportUrl(activeSeries.id, "knowledge-cards"), enabled: true, label: "知识卡片导出" },
    { href: seriesExportUrl(activeSeries.id, "mindmaps"), enabled: true, label: "导图导出" },
  ];
}

function videoExportUrl(seriesId, videoId, exportName) {
  if (exportName.endsWith(".zip") || exportName.endsWith(".srt")) {
    return `/api/videos/${encodeURIComponent(seriesId)}/${encodeURIComponent(videoId)}/exports/${exportName}`;
  }
  return `/api/videos/${encodeURIComponent(seriesId)}/${encodeURIComponent(videoId)}/exports/${exportName}.md`;
}

function seriesExportUrl(seriesId, exportName) {
  return `/api/series/${encodeURIComponent(seriesId)}/exports/${exportName}.zip`;
}
