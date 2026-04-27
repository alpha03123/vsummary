export function WorkspaceSeriesOverviewView({ activeSeries }) {
  const seriesVideos = activeSeries?.videos ?? [];

  return (
    <div className="w-full max-w-4xl">
      <article className="workspace-muted-panel rounded-[2rem] border p-7">
        <p className="text-xs font-bold uppercase tracking-widest text-stone-500 dark:text-stone-400">Series Overview</p>
        <h3 className="mt-3 text-3xl font-bold text-stone-900 dark:text-stone-100">{activeSeries.title}</h3>
        <p className="mt-4 text-sm leading-relaxed text-stone-600 dark:text-stone-400">
          这是系列级上下文。后续 AI 可以基于整个 series 理解主题范围、视频分布和知识覆盖，而不是被锁定在单一视频上。
        </p>
        <div className="mt-6 flex flex-col gap-3">
          {seriesVideos.map((video) => (
            <div key={video.id} className="workspace-elevated-panel rounded-2xl border px-4 py-3">
              <div className="flex items-center justify-between gap-3">
                <strong className="text-sm font-semibold text-stone-900 dark:text-stone-100">{video.title}</strong>
                <span className={`text-xs font-semibold ${video.processed ? "text-accent dark:text-accent" : "text-stone-500"}`}>
                  {video.processed ? "已处理" : "未处理"}
                </span>
              </div>
            </div>
          ))}
        </div>
      </article>
    </div>
  );
}
