export function WorkspaceSettingsPanel({
  ui,
  onChangeSetting,
  onResetSettings,
  onClose,
}) {
  return (
    <section className="settings-panel" aria-label="界面设置">
      <div className="settings-panel-head">
        <div>
          <p className="eyebrow">Workspace Settings</p>
          <h2>阅读界面</h2>
        </div>
        <button type="button" className="settings-dismiss" onClick={onClose} aria-label="关闭设置面板">
          关闭
        </button>
      </div>

      <div className="settings-section">
        <div className="settings-copy">
          <strong>正文宽度</strong>
          <span>标准适合专注阅读，舒展更适合横屏大屏。</span>
        </div>
        <div className="segmented-control" role="group" aria-label="正文宽度">
          <button
            type="button"
            className={`segmented-option${ui.contentWidth === "regular" ? " is-active" : ""}`}
            onClick={() => onChangeSetting("contentWidth", "regular")}
          >
            标准
          </button>
          <button
            type="button"
            className={`segmented-option${ui.contentWidth === "wide" ? " is-active" : ""}`}
            onClick={() => onChangeSetting("contentWidth", "wide")}
          >
            舒展
          </button>
        </div>
      </div>

      <div className="settings-section is-block">
        <div className="settings-copy">
          <strong>阅读密度</strong>
          <span>舒适更从容，紧凑更适合信息扫读。</span>
        </div>
        <div className="segmented-control" role="group" aria-label="阅读密度">
          <button
            type="button"
            className={`segmented-option${ui.readingDensity === "comfortable" ? " is-active" : ""}`}
            onClick={() => onChangeSetting("readingDensity", "comfortable")}
          >
            舒适
          </button>
          <button
            type="button"
            className={`segmented-option${ui.readingDensity === "compact" ? " is-active" : ""}`}
            onClick={() => onChangeSetting("readingDensity", "compact")}
          >
            紧凑
          </button>
        </div>
      </div>

      <div className="settings-section">
        <div className="settings-copy">
          <strong>关键收获</strong>
          <span>在正文顶部显示全局提炼要点。</span>
        </div>
        <button
          type="button"
          className={`settings-switch${ui.showTakeaways ? " is-on" : ""}`}
          onClick={() => onChangeSetting("showTakeaways", !ui.showTakeaways)}
          aria-pressed={ui.showTakeaways}
        >
          <span className="settings-switch-handle" />
        </button>
      </div>

      <div className="settings-panel-foot">
        <p>这里只保留阅读相关设置，主页默认专注在系列浏览和视频处理流程。</p>
        <button type="button" className="settings-reset" onClick={onResetSettings}>
          恢复默认
        </button>
      </div>
    </section>
  );
}
