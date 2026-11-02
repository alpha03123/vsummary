import { motion } from "framer-motion";

export function WorkspaceSeriesHomeView({ activeSeries }) {
  const seriesVideos = activeSeries?.videos ?? [];
  const processedSeriesVideos = seriesVideos.filter((video) => video.processed);
  const percent = seriesVideos.length ? Math.round((processedSeriesVideos.length / seriesVideos.length) * 100) : 0;

  return (
    <div className="flex flex-col w-full">
      <div className="workspace-panel rounded-2xl border p-5 shadow-sm">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-3">
            <span className="text-xs font-bold uppercase tracking-widest text-subtle">转化进度</span>
            <span className="px-2.5 py-1 rounded-full bg-soft border border-line/50 text-xs font-bold text-subtle">
              {processedSeriesVideos.length} / {seriesVideos.length} 视频
            </span>
          </div>
          <strong className="text-xl font-black text-accent">{percent}%</strong>
        </div>
        
        <div className="w-full h-2 bg-soft rounded-full overflow-hidden border border-line/50 shadow-inner">
          <motion.div
            initial={{ width: 0 }}
            animate={{ width: `${percent}%` }}
            transition={{ duration: 1, ease: "easeOut" }}
            className="h-full bg-accent rounded-full relative"
          >
            <div className="absolute inset-0 bg-white/20 dark:bg-soft w-full h-full" style={{ backgroundImage: 'linear-gradient(45deg, rgba(255,255,255,0.15) 25%, transparent 25%, transparent 50%, rgba(255,255,255,0.15) 50%, rgba(255,255,255,0.15) 75%, transparent 75%, transparent)', backgroundSize: '0.5rem 0.5rem' }} />
          </motion.div>
        </div>
      </div>
    </div>
  );
}
