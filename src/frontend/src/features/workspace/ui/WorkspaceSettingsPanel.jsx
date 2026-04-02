export function WorkspaceSettingsPanel({
  ui,
  onChangeSetting,
  onResetSettings,
  onClose,
}) {
  return (
    <section className="bg-white rounded-3xl p-6 shadow-xl border border-stone-200 w-full max-w-sm pointer-events-auto" aria-label="界面设置">
      <div className="flex justify-between items-start mb-6">
        <div>
          <p className="text-[10px] font-bold text-teal-700 tracking-widest uppercase mb-1">Workspace Settings</p>
          <h2 className="text-xl font-bold text-stone-900">阅读界面</h2>
        </div>
        <button 
          type="button" 
          className="inline-flex items-center justify-center px-3 py-1.5 rounded-full bg-stone-100 text-stone-600 text-xs font-semibold hover:bg-stone-200 transition-colors" 
          onClick={onClose} 
          aria-label="关闭设置面板"
        >
          关闭
        </button>
      </div>

      <div className="py-4 border-b border-stone-100 flex flex-col gap-3">
        <div>
          <strong className="block text-sm font-semibold text-stone-900 mb-0.5">正文宽度</strong>
          <span className="text-xs text-stone-500">标准适合专注阅读，舒展更适合横屏大屏。</span>
        </div>
        <div className="grid grid-cols-2 p-1 bg-stone-100 rounded-xl" role="group" aria-label="正文宽度">
          <button
            type="button"
            className={`py-2 px-3 rounded-lg text-sm font-medium transition-all ${ui.contentWidth === "regular" ? "bg-white text-stone-900 shadow-sm" : "text-stone-500 hover:text-stone-700 hover:bg-stone-200/50"}`}
            onClick={() => onChangeSetting("contentWidth", "regular")}
          >
            标准
          </button>
          <button
            type="button"
            className={`py-2 px-3 rounded-lg text-sm font-medium transition-all ${ui.contentWidth === "wide" ? "bg-white text-stone-900 shadow-sm" : "text-stone-500 hover:text-stone-700 hover:bg-stone-200/50"}`}
            onClick={() => onChangeSetting("contentWidth", "wide")}
          >
            舒展
          </button>
        </div>
      </div>

      <div className="py-4 border-b border-stone-100 flex flex-col gap-3">
        <div>
          <strong className="block text-sm font-semibold text-stone-900 mb-0.5">阅读密度</strong>
          <span className="text-xs text-stone-500">舒适更从容，紧凑更适合信息扫读。</span>
        </div>
        <div className="grid grid-cols-2 p-1 bg-stone-100 rounded-xl" role="group" aria-label="阅读密度">
          <button
            type="button"
            className={`py-2 px-3 rounded-lg text-sm font-medium transition-all ${ui.readingDensity === "comfortable" ? "bg-white text-stone-900 shadow-sm" : "text-stone-500 hover:text-stone-700 hover:bg-stone-200/50"}`}
            onClick={() => onChangeSetting("readingDensity", "comfortable")}
          >
            舒适
          </button>
          <button
            type="button"
            className={`py-2 px-3 rounded-lg text-sm font-medium transition-all ${ui.readingDensity === "compact" ? "bg-white text-stone-900 shadow-sm" : "text-stone-500 hover:text-stone-700 hover:bg-stone-200/50"}`}
            onClick={() => onChangeSetting("readingDensity", "compact")}
          >
            紧凑
          </button>
        </div>
      </div>

      <div className="py-4 border-b border-stone-100 flex items-center justify-between">
        <div>
          <strong className="block text-sm font-semibold text-stone-900 mb-0.5">关键收获</strong>
          <span className="text-xs text-stone-500">在正文顶部显示全局提炼要点。</span>
        </div>
        <button
          type="button"
          className={`relative inline-flex h-6 w-11 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none focus-visible:ring-2 focus-visible:ring-teal-500/50 ${ui.showTakeaways ? "bg-teal-500" : "bg-stone-200"}`}
          onClick={() => onChangeSetting("showTakeaways", !ui.showTakeaways)}
          aria-pressed={ui.showTakeaways}
        >
          <span className={`pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow ring-0 transition duration-200 ease-in-out ${ui.showTakeaways ? "translate-x-5" : "translate-x-0"}`} />
        </button>
      </div>

      <div className="mt-6 flex flex-col gap-4">
        <p className="text-xs text-stone-500 leading-relaxed text-center">这里只保留阅读相关设置，主页默认专注在系列浏览和视频处理流程。</p>
        <button 
          type="button" 
          className="w-full py-2.5 rounded-xl border border-stone-200 text-stone-600 text-sm font-semibold hover:bg-stone-50 hover:text-stone-900 transition-colors" 
          onClick={onResetSettings}
        >
          恢复默认
        </button>
      </div>
    </section>
  );
}
