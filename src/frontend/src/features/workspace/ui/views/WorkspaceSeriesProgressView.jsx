export function WorkspaceSeriesProgressView({ activeSeries }) {
  const seriesVideos = activeSeries?.videos ?? [];

  return (
    <div className="w-full max-w-4xl">
      <article className="workspace-muted-panel rounded-[2rem] border p-7">
        <p className="text-xs font-bold uppercase tracking-widest text-stone-500 dark:text-stone-400">Series Progress</p>
        <h3 className="mt-3 text-3xl font-bold text-stone-900 dark:text-stone-100">处理进度</h3>
        <div className="mt-6 flex flex-col gap-3">
          {seriesVideos.map((video, index) => (
            <div key={video.id} className="workspace-elevated-panel rounded-2xl border px-4 py-4">
              <div className="flex items-center justify-between gap-4">
                <div>
                  <p className="text-xs font-bold uppercase tracking-widest text-stone-400 dark:text-stone-500">Video {index + 1}</p>
                  <strong className="mt-1 block text-sm font-semibold text-stone-900 dark:text-stone-100">{video.title}</strong>
                </div>
                <span className={`rounded-full px-3 py-1 text-xs font-semibold ${
                  video.processed
                    ? "bg-stone-100 text-stone-900 dark:bg-[#111111] dark:text-white border border-stone-200 dark:border-white/10"
                    : "bg-stone-100 text-stone-500 dark:bg-stone-800 dark:text-stone-300"
                }`}>
                  {video.processed ? "已完成" : "待处理"}
                </span>
              </div>
            </div>
          ))}
        </div>
      </article>
    </div>
  );
}
