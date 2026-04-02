import { ArrowLeft, LoaderCircle, Sparkles, FileVideo, CheckCircle2, CircleDashed } from "lucide-react";

export function WorkspaceLibraryPanel({
  activeSeries,
  selectedVideo,
  isGeneratingSelectedVideo,
  onEnterLibraryHome,
  onSelectVideo,
  onGenerateVideo,
}) {
  return (
    <section className="flex flex-col h-full w-full bg-white relative">
      
      {/* Sidebar Header */}
      <div className="p-5 pb-4 border-b border-stone-100 flex-shrink-0">
        <div className="flex justify-between items-start mb-4">
          <div>
            <p className="text-[10px] font-bold text-teal-700 tracking-wider uppercase mb-1">Sources</p>
            <h2 className="text-lg font-bold text-stone-800 leading-tight">{activeSeries?.title ?? "未选择 series"}</h2>
          </div>
          <button 
            type="button" 
            className="inline-flex items-center justify-center w-8 h-8 rounded-full text-stone-500 hover:bg-stone-100 transition-colors" 
            onClick={onEnterLibraryHome}
            title="返回分类列表"
          >
            <ArrowLeft size={18} />
          </button>
        </div>

        {/* Quick Stats */}
        <div className="flex gap-2 text-xs">
          <div className="flex-1 bg-stone-50 rounded-xl p-2 border border-stone-100">
            <span className="block text-stone-400 mb-0.5">总视频数</span>
            <strong className="text-stone-700">{activeSeries?.videos?.length ?? 0} 个视频</strong>
          </div>
          <div className="flex-1 bg-teal-50 rounded-xl p-2 border border-teal-100/50">
            <span className="block text-teal-600/70 mb-0.5">已处理</span>
            <strong className="text-teal-700">{activeSeries?.videos?.filter((video) => video.processed).length ?? 0} 个视频</strong>
          </div>
        </div>
      </div>

      {/* Video / Source List */}
      <div className="flex-1 overflow-y-auto p-3 flex flex-col gap-2" aria-label="视频列表">
        {(activeSeries?.videos ?? []).map((video) => {
          const isActive = video.id === selectedVideo?.id;
          return (
            <button
              key={video.id}
              type="button"
              className={`text-left flex flex-col gap-2 p-3.5 rounded-2xl border transition-all duration-200 outline-none
                ${isActive 
                  ? "bg-teal-50/50 border-teal-500/50 shadow-sm ring-1 ring-teal-500/20" 
                  : "bg-white border-stone-200 hover:border-stone-300 hover:bg-stone-50"
                }`}
              onClick={() => onSelectVideo(activeSeries.id, video.id)}
            >
              <div className="flex justify-between items-start w-full gap-2">
                <span className={`inline-flex items-center gap-1 text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-md ${video.processed ? "bg-teal-100 text-teal-700" : "bg-stone-100 text-stone-500"}`}>
                  {video.processed ? <CheckCircle2 size={12} /> : <CircleDashed size={12} />}
                  {video.processed ? "已生成概况" : "未处理"}
                </span>
                <FileVideo size={16} className={isActive ? "text-teal-600" : "text-stone-400"} />
              </div>
              <div className="flex flex-col gap-0.5 mt-1">
                <strong className={`text-sm font-semibold line-clamp-2 ${isActive ? "text-teal-900" : "text-stone-800"}`}>
                  {video.title}
                </strong>
                <span className="text-xs text-stone-500 truncate">{video.sourceName}</span>
              </div>
            </button>
          );
        })}
      </div>

      {/* Footer Generate Action */}
      {selectedVideo ? (
        <div className="p-4 border-t border-stone-100 bg-stone-50/80 backdrop-blur-sm flex-shrink-0">
          <div className="mb-3">
            <p className="text-[10px] font-bold text-stone-500 tracking-wider uppercase mb-1 drop-shadow-sm">当前视频</p>
            <h3 className="text-sm font-bold text-stone-800 truncate" title={selectedVideo.title}>{selectedVideo.title}</h3>
          </div>
          <button
            type="button"
            className={`w-full inline-flex items-center justify-center gap-2 px-4 py-2.5 rounded-2xl font-semibold text-sm transition-all duration-200
              ${isGeneratingSelectedVideo 
                ? "bg-stone-200 text-stone-500 cursor-not-allowed" 
                : "bg-teal-600 text-white hover:bg-teal-700 shadow-sm shadow-teal-600/20 active:scale-[0.98]"
              }`}
            onClick={onGenerateVideo}
            disabled={isGeneratingSelectedVideo}
          >
            {isGeneratingSelectedVideo ? (
              <>
                <LoaderCircle size={16} strokeWidth={2.5} className="animate-spin text-stone-500" />
                正在生成 AI 概况...
              </>
            ) : (
              <>
                <Sparkles size={16} strokeWidth={2.5} />
                {selectedVideo.processed ? "重新生成 AI 概况" : "生成 AI 概况"}
              </>
            )}
          </button>
        </div>
      ) : (
         <div className="p-4 border-t border-stone-100 bg-stone-50/80 backdrop-blur-sm flex justify-center items-center h-[98px]">
            <p className="text-xs text-stone-400 font-medium">选择一个视频后再进入工具区</p>
         </div>
      )}
    </section>
  );
}
