import { WorkspaceMetricCard } from "../shared/WorkspaceMetricCard";

export function WorkspaceSeriesHomeView({ activeSeries }) {
  const seriesVideos = activeSeries?.videos ?? [];
  const processedSeriesVideos = seriesVideos.filter((video) => video.processed);

  return (
    <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
      <WorkspaceMetricCard label="系列视频数" value={seriesVideos.length} />
      <WorkspaceMetricCard label="已处理视频" value={processedSeriesVideos.length} accent="accent" />
      <WorkspaceMetricCard label="当前焦点" value={`整个 ${activeSeries.title}`} valueClassName="text-xl dark:text-stone-100" />
    </div>
  );
}
