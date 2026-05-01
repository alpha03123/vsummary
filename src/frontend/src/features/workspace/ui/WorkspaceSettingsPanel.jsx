import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { popScaleVariant, blurVariant } from "../../../lib/animations";
import { Settings2, Cpu, Globe, Key, FileText, X, LoaderCircle, Download } from "lucide-react";
import {
  WorkspaceSegmentedControl,
  WorkspaceSettingRow,
  WorkspaceTextInput,
  WorkspaceToggleSwitch,
} from "./shared/WorkspaceSettingsControls";

export function WorkspaceSettingsPanel({
  ui,
  fasterWhisperModels,
  fasterWhisperModelsLoading,
  downloadingModelId,
  modelDownloadProgress,
  onChangeSetting,
  onSaveApiKey,
  onDownloadFasterWhisperModel,
  onCancelFasterWhisperModelDownload,
  onResetSettings,
  onClose,
}) {
  const [activeTab, setActiveTab] = useState("general");
  const [showResetConfirm, setShowResetConfirm] = useState(false);
  const [confirmDownloadModelId, setConfirmDownloadModelId] = useState(null);
  const [showApiKeyValue, setShowApiKeyValue] = useState(false);
  const hasApiKey = ui.hasOpenaiApiKey;
  const apiKeyStatus = ui.openaiApiKey.trim() || ui.openaiApiKeyMasked;

  const tabs = [
    { id: "general", label: "常规与显示", icon: Settings2 },
    { id: "ai", label: "AI 总结能力", icon: Cpu },
    { id: "keys", label: "模型供应商", icon: Key },
    { id: "network", label: "网络代理 (等待接入)", icon: Globe },
  ];
  return (
    <motion.section
      variants={popScaleVariant}
      initial="initial"
      animate="animate"
      exit="exit"
      className="bg-white dark:bg-neutral-950 rounded-[2rem] shadow-2xl border border-stone-200 dark:border-white/10 w-full max-w-5xl h-[80vh] flex overflow-hidden pointer-events-auto"
      aria-label="界面设置"
    >
      {/* Sidebar */}
      <div className="w-[250px] shrink-0 bg-stone-50/50 dark:bg-neutral-900 border-r border-stone-200/80 dark:border-white/5 p-6 flex flex-col relative z-20">
        <div className="mb-8 mt-2 px-2">
          <p className="text-[10px] font-bold text-accent tracking-widest uppercase mb-1">Preferences</p>
          <h2 className="text-2xl font-bold text-stone-900 dark:text-stone-100 tracking-tight">控制中心</h2>
        </div>
        <div className="flex flex-col gap-1.5 flex-1">
          {tabs.map(tab => {
            const Icon = tab.icon;
            const isActive = activeTab === tab.id;
            return (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={`flex items-center gap-3 px-3 py-3 rounded-xl text-sm font-medium transition-all duration-200 ${isActive
                  ? "bg-white dark:bg-stone-800/80 text-accent shadow-sm border border-stone-200/60 dark:border-stone-700/60"
                  : "text-stone-600 dark:text-stone-400 hover:bg-stone-100 dark:hover:bg-stone-800/40 hover:text-stone-900 dark:hover:text-stone-200 border border-transparent"
                  }`}
              >
                <Icon size={16} strokeWidth={isActive ? 2.5 : 2} />
                {tab.label}
              </button>
            )
          })}
        </div>

        {/* Reset Settings */}
        <div className="mt-auto pt-6 border-t border-stone-200/80 dark:border-stone-800/50">
          <button
            type="button"
            className="w-full text-left px-3 py-2 rounded-lg text-[13px] font-semibold text-stone-500 hover:text-red-600 dark:hover:text-red-400 hover:bg-red-50 dark:hover:bg-red-950/30 transition-colors"
            onClick={() => setShowResetConfirm(true)}
          >
            恢复默认设置
          </button>
        </div>
      </div>

      {/* Main Content Area */}
      <div className="flex-1 flex flex-col overflow-y-auto relative bg-white dark:bg-neutral-950 scroll-smooth">
        <div className="sticky top-0 bg-white/80 dark:bg-neutral-950/80 backdrop-blur-md z-30 p-6 flex justify-end">
          <button
            type="button"
            className="inline-flex items-center justify-center w-9 h-9 rounded-full bg-stone-100 dark:bg-stone-800 text-stone-500 hover:bg-stone-200 dark:hover:bg-stone-700 transition-colors shadow-sm"
            onClick={onClose}
            aria-label="关闭面板"
          >
            <X size={18} />
          </button>
        </div>

        <div className="px-10 pb-16 max-w-3xl">
          <motion.div
            key={activeTab}
            variants={blurVariant}
            initial="initial"
            animate="animate"
            className="flex flex-col gap-8"
          >
            {activeTab === "general" && (
              <>
                <div className="mb-2">
                  <h3 className="text-2xl font-bold text-stone-900 dark:text-stone-100">常规与显示</h3>
                  <p className="text-[13px] text-stone-500 dark:text-stone-400 mt-2">这里的配置会写入后端的 `settings.toml` 并实时生效</p>
                </div>

                {/* Theme Setting */}
                <WorkspaceSettingRow
                  title="深色模式"
                  description="切换整个工作区界面的明暗主题模式。"
                >
                  <WorkspaceSegmentedControl
                    value={ui.theme}
                    options={[
                      { id: "light", label: "浅色" },
                      { id: "dark", label: "深色" },
                    ]}
                    onChange={(nextValue) => onChangeSetting("theme", nextValue)}
                  />
                </WorkspaceSettingRow>

                <WorkspaceSettingRow
                  title="显示关键收获"
                  description="在详情正文顶部优先显示由 AI 提炼的全局“Key Takeaways”。"
                >
                  <WorkspaceToggleSwitch
                    checked={ui.showTakeaways}
                    onChange={() => onChangeSetting("showTakeaways", !ui.showTakeaways)}
                  />
                </WorkspaceSettingRow>
              </>
            )}

            {activeTab === "ai" && (
              <>
                <div className="mb-2">
                  <h3 className="text-2xl font-bold text-stone-900 dark:text-stone-100">AI 总结能力</h3>
                  <p className="text-[13px] text-stone-500 dark:text-stone-400 mt-2">控制总结流程，会写入 `settings.toml`。</p>
                </div>

                <WorkspaceSettingRow
                  title="AI 视频内容增强"
                  description="利用大模型理解上下文后纠正转写文本，让总结结果更加精确。关闭可提高处理速度但会降低准确率。"
                >
                  <WorkspaceToggleSwitch
                    checked={ui.transcriptEnhancementEnabled}
                    onChange={() => onChangeSetting("transcriptEnhancementEnabled", !ui.transcriptEnhancementEnabled)}
                  />
                </WorkspaceSettingRow>

                <WorkspaceSettingRow
                  title="转写模式"
                  description="控制 faster-whisper 的解码策略"
                >
                  <WorkspaceSegmentedControl
                    value={ui.transcriptionMode}
                    options={[
                      { id: "fast", label: "极速" },
                      { id: "balanced", label: "平衡" },
                      { id: "accurate", label: "高精度(建议)" },
                    ]}
                    onChange={(nextValue) => onChangeSetting("transcriptionMode", nextValue)}
                  />
                </WorkspaceSettingRow>

                <WorkspaceSettingRow
                  title="语音模型质量"
                  description="控制转写精确度"
                >
                  <div className="w-full min-w-[320px] flex flex-col gap-3">
                    {fasterWhisperModelsLoading ? (
                      <div className="flex items-center gap-2 text-sm text-stone-500 dark:text-stone-400">
                        <LoaderCircle size={16} className="animate-spin" />
                        正在读取模型状态...
                      </div>
                    ) : (
                      fasterWhisperModels.map((model) => {
                        const needsConfirm = confirmDownloadModelId === model.id;
                        const isCurrent = ui.asrModelQuality === model.id;
                        const isDownloading = downloadingModelId === model.id;
                        const isReady = model.downloaded === true;
                        const statusText = model.downloaded
                          ? "已下载到本地"
                          : isCurrent
                            ? "当前默认模型，需先下载"
                            : "尚未下载";
                        return (
                          <div
                            key={model.id}
                            className={`rounded-2xl border p-4 transition-colors ${isCurrent
                              ? "border-accent/30 bg-info-subtle dark:bg-info-subtle"
                              : "border-stone-200 dark:border-stone-800"
                              }`}
                          >
                            <div className="flex items-center justify-between gap-4">
                              <div>
                                <div className="flex items-center gap-2">
                                  <strong className="text-sm font-bold text-stone-900 dark:text-stone-100">{model.label}</strong>
                                  {model.recommended ? (
                                    <span className="rounded-full bg-accent/10 px-2 py-0.5 text-[11px] font-bold text-accent">
                                      推荐
                                    </span>
                                  ) : null}
                                </div>
                                <p className="mt-1 text-xs text-stone-500 dark:text-stone-400">
                                  {isDownloading
                                    ? `正在下载... ${typeof modelDownloadProgress === "number" ? `${Math.round(modelDownloadProgress)}%` : ""}`.trim()
                                    : statusText}
                                </p>
                                {isDownloading ? (
                                  <div className="mt-3 w-full h-1.5 bg-stone-200/70 dark:bg-stone-800 rounded-full overflow-hidden">
                                    <div
                                      className="h-full bg-accent transition-[width] duration-200 ease-out"
                                      style={{ width: `${typeof modelDownloadProgress === "number" ? modelDownloadProgress : 8}%` }}
                                    />
                                  </div>
                                ) : null}
                              </div>
                              {isDownloading ? (
                                <button
                                  type="button"
                                  onClick={() => onCancelFasterWhisperModelDownload(model.id)}
                                  className="rounded-xl border border-red-200 bg-white px-3 py-2 text-xs font-bold text-red-600 hover:bg-red-50 dark:border-red-900/70 dark:bg-stone-900 dark:text-red-300 dark:hover:bg-red-950/30"
                                >
                                  取消
                                </button>
                              ) : isCurrent && isReady ? (
                                <button
                                  type="button"
                                  disabled
                                  className="rounded-xl border border-stone-200 bg-white px-3 py-2 text-xs font-bold text-stone-500 dark:border-stone-700 dark:bg-stone-900 dark:text-stone-400"
                                >
                                  使用中
                                </button>
                              ) : isReady ? (
                                <button
                                  type="button"
                                  onClick={() => {
                                    setConfirmDownloadModelId(null);
                                    onChangeSetting("asrModelQuality", model.id);
                                  }}
                                  className="rounded-xl bg-accent px-3 py-2 text-xs font-bold text-white hover:bg-accent/90 transition-colors"
                                >
                                  使用
                                </button>
                              ) : (
                                <button
                                  type="button"
                                  onClick={() => {
                                    if (needsConfirm) {
                                      setConfirmDownloadModelId(null);
                                      onDownloadFasterWhisperModel(model.id);
                                      return;
                                    }
                                    setConfirmDownloadModelId(model.id);
                                  }}
                                  className={`inline-flex items-center gap-2 rounded-xl px-3 py-2 text-xs font-bold transition-colors ${needsConfirm
                                    ? "bg-warning text-white hover:opacity-85"
                                    : "bg-stone-900 text-white hover:bg-black dark:bg-stone-100 dark:text-stone-900 dark:hover:bg-white"
                                    }`}
                                >
                                  <Download size={14} />
                                  {needsConfirm ? "确认下载?" : (isCurrent ? "下载并使用" : "下载")}
                                </button>
                              )}
                            </div>
                          </div>
                        );
                      })
                    )}
                  </div>
                </WorkspaceSettingRow>

                <WorkspaceSettingRow
                  title="检索模型"
                  description="控制检索模型运行在 CPU 还是 GPU。建议CPU,除非你自行安装了GPU环境。"
                >
                  <WorkspaceSegmentedControl
                    value={ui.ragEmbeddingDevice}
                    options={[
                      { id: "cpu", label: "CPU" },
                      { id: "gpu", label: "GPU" },
                      { id: "auto", label: "自动" },
                    ]}
                    onChange={(nextValue) => onChangeSetting("ragEmbeddingDevice", nextValue)}
                  />
                </WorkspaceSettingRow>
              </>
            )}

            {activeTab === "keys" && (
              <>
                <div className="mb-2">
                  <h3 className="text-2xl font-bold text-stone-900 dark:text-stone-100">模型供应商</h3>
                </div>

                <WorkspaceSettingRow
                  title="供应商协议"
                  description="目前仅支持openai协议"
                >
                  <WorkspaceSegmentedControl
                    value="openai_compatible"
                    options={[{ id: "openai_compatible", label: "OpenAI 兼容" }]}
                    onChange={() => { }}
                  />
                </WorkspaceSettingRow>

                <WorkspaceSettingRow
                  title="API 根地址"
                  description="填写 OpenAI 兼容 API 根地址，例如 `https://api.deepseek.com` 或 `https://api.deepseek.com/v1`。"
                >
                  <WorkspaceTextInput
                    value={ui.openaiBaseUrl}
                    onChange={(nextValue) => onChangeSetting("openaiBaseUrl", nextValue)}
                    placeholder="https://api.openai.com/v1"
                    className="w-[340px]"
                  />
                </WorkspaceSettingRow>

                <WorkspaceSettingRow
                  title="模型名称"
                  description="例如 `gpt-5.4` 或你的 OpenAI 兼容服务实际支持的模型名。"
                >
                  <WorkspaceTextInput
                    value={ui.openaiModel}
                    onChange={(nextValue) => onChangeSetting("openaiModel", nextValue)}
                    placeholder="gpt-5.4"
                    className="w-[240px]"
                  />
                </WorkspaceSettingRow>

                <WorkspaceSettingRow
                  title="API Key"
                  description="写入项目根目录 `.env` 的 `OPENAI_API_KEY`。不会进入 `settings.toml`。"
                >
                  <div className="w-[340px] rounded-2xl border border-stone-200 bg-white px-4 py-3 dark:border-stone-700 dark:bg-stone-900">
                    <div className="flex items-center justify-between gap-3">
                      <div className="min-w-0">
                        <p className={`text-sm font-semibold ${hasApiKey ? "text-success" : "text-stone-500 dark:text-stone-400"}`}>
                          {hasApiKey ? "已配置" : "未配置"}
                        </p>
                        {apiKeyStatus ? (
                          <p className="mt-1 truncate text-xs text-stone-500 dark:text-stone-400">
                            当前状态：{ui.openaiApiKey.trim() ? "待保存的新密钥" : apiKeyStatus}
                          </p>
                        ) : null}
                      </div>
                      <button
                        type="button"
                        onClick={() => setShowApiKeyValue((value) => !value)}
                        disabled={!apiKeyStatus}
                        className="rounded-xl border border-stone-200 px-3 py-2 text-xs font-bold text-stone-600 transition-colors hover:bg-stone-50 disabled:cursor-not-allowed disabled:opacity-50 dark:border-stone-700 dark:text-stone-300 dark:hover:bg-stone-800"
                      >
                        {showApiKeyValue ? "隐藏" : "显示"}
                      </button>
                    </div>
                    <WorkspaceTextInput
                      type={showApiKeyValue ? "text" : "password"}
                      value={ui.openaiApiKey}
                      onChange={(nextValue) => onChangeSetting("openaiApiKey", nextValue)}
                      placeholder={hasApiKey ? "输入新 Key 以覆盖现有配置" : "sk-..."}
                      className="mt-3 w-full dark:bg-stone-950"
                    />
                    <div className="mt-3 flex justify-end">
                      <button
                        type="button"
                        onClick={onSaveApiKey}
                        disabled={!ui.openaiApiKey.trim()}
                        className="rounded-xl bg-stone-900 px-4 py-2 text-xs font-bold text-white transition-colors hover:bg-black disabled:cursor-not-allowed disabled:opacity-50 dark:bg-white dark:text-stone-900 dark:hover:bg-stone-100"
                      >
                        保存 Key
                      </button>
                    </div>
                  </div>
                </WorkspaceSettingRow>
              </>
            )}

            {activeTab === "network" && (
              <>
                <div className="mb-2">
                  <h3 className="text-2xl font-bold text-stone-900 dark:text-stone-100">网络与镜像</h3>
                  <p className="text-[13px] text-stone-500 dark:text-stone-400 mt-2">
                    这里的配置会写入项目根目录 `.env` 并实时生效。
                  </p>
                </div>

                <WorkspaceSettingRow
                  title="HuggingFace 镜像地址"
                  description="Huggingface镜像,如果无法下载模型请配置此设置,留空时默认使用 HuggingFace 官方源。"
                >
                  <WorkspaceTextInput
                    value={ui.hfEndpoint}
                    onChange={(nextValue) => onChangeSetting("hfEndpoint", nextValue)}
                    placeholder="https://hf-mirror.com"
                    className="w-[340px]"
                  />
                </WorkspaceSettingRow>
              </>
            )}
          </motion.div>
        </div>
      </div>

      {/* Reset Confirmation Overlay */}
      <AnimatePresence>
        {showResetConfirm && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="absolute inset-0 z-[100] bg-white/60 dark:bg-black/60 backdrop-blur-sm flex items-center justify-center p-6"
          >
            <motion.div
              initial={{ scale: 0.95, y: 10 }}
              animate={{ scale: 1, y: 0 }}
              exit={{ scale: 0.95, y: 10 }}
              className="bg-white dark:bg-neutral-900 border border-stone-200 dark:border-stone-700/60 p-7 rounded-[1.5rem] shadow-[0_20px_40px_rgba(0,0,0,0.15)] max-w-[340px] w-full text-center"
            >
              <h3 className="text-xl font-bold text-stone-900 dark:text-white mb-2">恢复默认设置？</h3>
              <p className="text-[13px] leading-relaxed text-stone-500 dark:text-stone-400 mb-6">
                此操作将恢复工作区默认设置，并立即覆盖真实的 <code className="bg-stone-100 dark:bg-stone-800 px-1 py-0.5 rounded text-stone-700 dark:text-stone-300">settings.toml</code>。`.env` 中的模型供应商配置不会被改动。确定继续？
              </p>
              <div className="flex gap-3 justify-center w-full">
                <button
                  type="button"
                  onClick={() => setShowResetConfirm(false)}
                  className="flex-1 py-2.5 rounded-xl text-[13px] font-bold text-stone-600 dark:text-stone-300 bg-stone-100 hover:bg-stone-200 dark:bg-stone-800 dark:hover:bg-stone-700 transition-colors"
                >
                  取消
                </button>
                <button
                  type="button"
                  onClick={() => {
                    onResetSettings();
                    setShowResetConfirm(false);
                  }}
                  className="flex-1 py-2.5 rounded-xl text-[13px] font-bold btn-danger shadow-sm transition-colors disabled:cursor-not-allowed disabled:opacity-50"
                >
                  确认恢复
                </button>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.section>
  );
}
