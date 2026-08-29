import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { popScaleVariant, blurVariant } from "../../../lib/animations";
import { Settings2, Cpu, Globe, Key, FileText, X, LoaderCircle, Download, Check } from "lucide-react";
import {
  WorkspaceProviderSelect,
  WorkspaceSegmentedControl,
  WorkspaceSelect,
  WorkspaceSettingRow,
  WorkspaceTextInput,
  WorkspaceToggleSwitch,
} from "./shared/WorkspaceSettingsControls";
import { MODEL_DOWNLOAD_FAILED_MESSAGE } from "../model/modelDownloadMessages";

export function WorkspaceSettingsPanel({
  ui,
  initialTab = "general",
  fasterWhisperModels,
  fasterWhisperModelsLoading,
  ragModels = [],
  ragModelsLoading = false,
  downloadingRagModelKey = null,
  downloadingModelId,
  modelDownloadsById = {},
  modelDownloadStatus = null,
  modelDownloadProgress,
  modelDownloadErrorModelId = null,
  modelDownloadError = null,
  onChangeSetting,
  onOpenUsagePage,
  onSaveProviderSettings,
  onSelectProviderModel,
  onDiscoverProviderModels,
  onSaveApiKey,
  onSaveAsrSettings,
  onRevealAsrApiKey,
  onTestAsrConnection,
  onRevealOpenaiApiKey,
  onTestProviderConnection,
  onDownloadFasterWhisperModel,
  onCancelFasterWhisperModelDownload,
  onDownloadRagModel,
  onCancelRagModelDownload,
  onResetSettings,
  onClose,
}) {
  const [activeTab, setActiveTab] = useState(initialTab);
  const [showResetConfirm, setShowResetConfirm] = useState(false);
  const [confirmDownloadModelId, setConfirmDownloadModelId] = useState(null);
  const [showApiKeyValue, setShowApiKeyValue] = useState(false);
  const [showAsrApiKeyValue, setShowAsrApiKeyValue] = useState(false);
  const [apiKeyRevealLoading, setApiKeyRevealLoading] = useState(false);
  const [asrApiKeyRevealLoading, setAsrApiKeyRevealLoading] = useState(false);
  const [providerTest, setProviderTest] = useState({ status: "idle", message: "" });
  const [asrTest, setAsrTest] = useState({ status: "idle", message: "" });
  const [detectedProviderModels, setDetectedProviderModels] = useState([]);
  const [providerModelDiscovery, setProviderModelDiscovery] = useState("idle");
  const isOllamaProvider = ui.llmProvider === "ollama";
  const hasApiKey = ui.hasOpenaiApiKey;
  const draftApiKey = ui.openaiApiKey.trim();
  const apiKeyDisplayValue = draftApiKey
    ? (showApiKeyValue ? draftApiKey : ui.openaiApiKeyMasked || "待保存的新密钥")
    : ui.openaiApiKeyMasked;
  const apiKeyStatus = draftApiKey || ui.openaiApiKeyMasked;
  const currentAsrProvider = ["faster_whisper", "whisper_cpp", "aliyun_bailian"].includes(ui.asrProvider)
    ? ui.asrProvider
    : "faster_whisper";
  const asrCloudModel = ui.asrCloudModel || "paraformer-v2";
  const asrBaseUrl = ui.asrBaseUrl || "https://dashscope.aliyuncs.com";
  const draftAsrApiKey = (ui.asrApiKey || "").trim();
  const asrApiKeyMasked = ui.asrApiKeyMasked || "";
  const asrApiKeyDisplayValue = draftAsrApiKey
    ? (showAsrApiKeyValue ? draftAsrApiKey : asrApiKeyMasked || "待保存的新密钥")
    : asrApiKeyMasked;
  const asrApiKeyStatus = draftAsrApiKey || asrApiKeyMasked;
  const runtimeCapabilities = ui.runtimeCapabilities;
  const fasterWhisperAvailable = runtimeCapabilities?.fasterWhisperAvailable !== false;
  const gpuEmbeddingAvailable = runtimeCapabilities?.gpuEmbeddingAvailable !== false;
  const unavailableReason = runtimeCapabilities?.unavailableReason || "当前运行环境不支持 NVIDIA CUDA 加速。";
  const rerankerModel = ragModels.find((model) => model.key === "reranker") ?? null;
  const rerankerNeedsDownload = rerankerModel != null && !rerankerModel.downloaded;
  const isRerankerDownloading = (
    rerankerModel?.status === "running" ||
    rerankerModel?.status === "cancelling" ||
    downloadingRagModelKey === "reranker"
  );
  const effectiveRerankEnabled = !rerankerNeedsDownload && ui.ragRerankEnabled;
  const providerModelOptions = [...new Set([...detectedProviderModels, ui.openaiModel].filter(Boolean))]
    .map((model) => ({ id: model, label: model }));
  const isProviderModelSelectActive = providerModelDiscovery === "ready";
  const saveProviderSettingsOnEnter = (event) => {
    if (event.key !== "Enter" || typeof onSaveProviderSettings !== "function") {
      return;
    }
    event.preventDefault();
    onSaveProviderSettings();
  };
  const handleProviderModelDiscovery = async () => {
    if (isProviderModelSelectActive) {
      setProviderModelDiscovery("idle");
      setDetectedProviderModels([]);
      return;
    }
    if (typeof onDiscoverProviderModels !== "function") {
      return;
    }
    setProviderModelDiscovery("loading");
    try {
      const models = await onDiscoverProviderModels();
      setDetectedProviderModels(models);
      setProviderModelDiscovery("ready");
    } catch {
      setProviderModelDiscovery("idle");
    }
  };
  const providerOptions = [
    { id: "openai", label: "openai", group: "官方", description: "OpenAI 官方 API；大多数中转站也兼容" },
    { id: "anthropic", label: "anthropic", group: "官方", description: "Anthropic Claude 官方 API" },
    { id: "gemini", label: "gemini", group: "官方", description: "Google Gemini 官方 API" },
    { id: "deepseek", label: "deepseek", group: "官方", description: "DeepSeek 官方 API" },
    { id: "xai", label: "xai", group: "官方", description: "xAI Grok 官方 API" },
    { id: "mistral", label: "mistral", group: "官方", description: "Mistral AI 官方 API" },
    { id: "dashscope", label: "dashscope (Qwen)", group: "官方", description: "阿里云通义千问官方通道" },
    { id: "volcengine", label: "volcengine (字节)", group: "官方", description: "火山引擎豆包官方通道" },
    { id: "minimax", label: "minimax (MiniMax)", group: "官方", description: "MiniMax 官方 API" },
    { id: "azure", label: "azure", group: "平台", description: "Azure OpenAI，微软云托管通道" },
    { id: "vertex_ai", label: "vertex_ai", group: "平台", description: "Google Cloud Vertex AI，谷歌云托管通道" },
    { id: "bedrock", label: "bedrock", group: "平台", description: "AWS Bedrock，亚马逊云托管模型平台" },
    { id: "groq", label: "groq", group: "平台", description: "Groq 高速推理平台" },
    { id: "perplexity", label: "perplexity", group: "平台", description: "Perplexity AI 搜索增强平台，支持联网搜索" },
    { id: "openrouter", label: "openrouter", group: "平台", description: "OpenRouter 模型路由平台，支持数百个模型" },
    { id: "ollama", label: "ollama", group: "本地", description: "本地运行，Ollama 默认接口" },
    { id: "lm_studio", label: "lm_studio", group: "本地", description: "本地运行，LM Studio 内置服务器" },
  ];

  const tabs = [
    { id: "general", label: "常规与显示", icon: Settings2 },
    { id: "ai", label: "AI 总结能力", icon: Cpu },
    { id: "rag", label: "对话管理", icon: FileText },
    { id: "keys", label: "模型供应商", icon: Key },
    { id: "external-import", label: "外部导入", icon: Globe },
    { id: "network", label: "下载管理 ", icon: Download },
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
            className="w-full text-left px-3 py-2 rounded-lg text-[13px] font-semibold text-stone-600 hover:text-red-600 dark:hover:text-red-400 hover:bg-red-50 dark:hover:bg-red-950/30 transition-colors"
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
            className="inline-flex items-center justify-center w-9 h-9 rounded-full bg-stone-100 dark:bg-stone-800 text-stone-600 hover:bg-stone-200 dark:hover:bg-stone-700 transition-colors shadow-sm"
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
                  <p className="text-[13px] text-stone-600 dark:text-stone-400 mt-2">常规配置项</p>
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
                  description="在概况内容顶部优先展示 AI 归纳的核心要点。"
                >
                  <WorkspaceToggleSwitch
                    checked={ui.showTakeaways}
                    onChange={() => onChangeSetting("showTakeaways", !ui.showTakeaways)}
                  />
                </WorkspaceSettingRow>

                <WorkspaceSettingRow
                  title="显示模式"
                  description="设定界面主视区优先展示视频播放器或 AI 对话框。"
                >
                  <WorkspaceSegmentedControl
                    value={ui.layoutMode}
                    options={[
                      { id: "video_center", label: "视频居中" },
                      { id: "chat_center", label: "AI 聊天居中" },
                    ]}
                    onChange={(nextValue) => onChangeSetting("layoutMode", nextValue)}
                  />
                </WorkspaceSettingRow>
              </>
            )}

            {activeTab === "ai" && (
              <>
                <div className="mb-2">
                  <h3 className="text-2xl font-bold text-stone-900 dark:text-stone-100">AI 总结能力</h3>
                  <p className="text-[13px] text-stone-600 dark:text-stone-400 mt-2">控制总结流程</p>
                </div>

                <WorkspaceSettingRow
                  title="语音识别供应商"
                  description={
                    !fasterWhisperAvailable && currentAsrProvider === "faster_whisper"
                      ? `${unavailableReason} 请改用 whisper.cpp 或阿里云百炼。`
                      : currentAsrProvider === "aliyun_bailian"
                        ? "云端极速转写，无需依赖本地显卡或下载模型，开箱即用。"
                        : currentAsrProvider === "whisper_cpp"
                          ? "适用于 Mac (Metal)、AMD 显卡或纯 CPU 环境的本地引擎，跨平台兼容性好且资源占用低。"
                          : "基于 NVIDIA 显卡 (CUDA) 的高性能本地识别，数据完全保存在本机，速度与精度兼备（首次需下载模型）。"
                  }
                >
                  <WorkspaceSegmentedControl
                    value={currentAsrProvider}
                    options={[
                      {
                        id: "faster_whisper",
                        label: "本地 faster-whisper",
                        disabled: !fasterWhisperAvailable,
                        disabledReason: unavailableReason,
                      },
                      { id: "whisper_cpp", label: "本地 whisper.cpp" },
                      { id: "aliyun_bailian", label: "阿里云百炼" },
                    ]}
                    onChange={(nextValue) => onChangeSetting("asrProvider", nextValue)}
                  />
                </WorkspaceSettingRow>

                {currentAsrProvider !== "aliyun_bailian" && (
                  <>
                    {currentAsrProvider === "faster_whisper" && (
                      <WorkspaceSettingRow
                        title="转写模式"
                        description="平衡语音转写的解码速度与文本识别准确率。"
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
                    )}

                    <WorkspaceSettingRow
                      title="语音模型质量"
                      description="选择本地识别模型规格，模型越大识别精度越高。"
                    >
                      <div className="w-full flex flex-col gap-3">
                        {fasterWhisperModelsLoading && !fasterWhisperModels.length ? (
                          <div className="flex items-center gap-2 text-sm text-stone-600 dark:text-stone-400">
                            <LoaderCircle size={16} className="animate-spin" />
                            正在读取模型状态...
                          </div>
                        ) : (
                          fasterWhisperModels.map((model) => {
                            const needsConfirm = confirmDownloadModelId === model.id;
                            const isCurrent = ui.asrModelQuality === model.id;
                            const modelDownload = modelDownloadsById?.[model.id] ?? null;
                            const isCancelling =
                              modelDownload?.status === "cancelling" ||
                              (downloadingModelId === model.id && modelDownloadStatus === "cancelling");
                            const isDownloading =
                              modelDownload?.status === "running" ||
                              (downloadingModelId === model.id && modelDownloadStatus === "running");
                            const downloadFailed =
                              modelDownload?.status === "failed" ||
                              (modelDownloadErrorModelId === model.id && Boolean(modelDownloadError));
                            const downloadProgress =
                              typeof modelDownload?.progress === "number"
                                ? modelDownload.progress
                                : modelDownloadProgress;
                            const isReady = model.downloaded === true;
                            const statusText = model.downloaded
                              ? "已下载到本地"
                              : isCancelling
                                ? "正在取消下载..."
                                : downloadFailed
                                  ? "下载失败"
                                  : isCurrent
                                    ? "当前默认模型，需先下载"
                                    : "尚未下载";
                            return (
                              <div
                                key={model.id}
                                className={`rounded-2xl border p-4 transition-colors ${downloadFailed
                                  ? "border-red-200 bg-red-50/70 dark:border-red-900/60 dark:bg-red-950/20"
                                  : isCurrent
                                    ? "border-accent/30 bg-info-subtle dark:bg-info-subtle"
                                    : "border-stone-200 dark:border-stone-800"
                                  }`}
                              >
                                <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
                                  <div className="min-w-0">
                                    <div className="flex items-center gap-2">
                                      <strong className="min-w-0 break-words text-sm font-bold text-stone-900 dark:text-stone-100">{model.label}</strong>
                                      {model.recommended ? (
                                        <span className="rounded-full bg-accent/10 px-2 py-0.5 text-[11px] font-bold text-accent">
                                          推荐
                                        </span>
                                      ) : null}
                                    </div>
                                    <p className="mt-1 text-xs text-stone-600 dark:text-stone-400">
                                      {isDownloading
                                        ? `正在下载... ${typeof downloadProgress === "number" ? `${Math.round(downloadProgress)}%` : ""}`.trim()
                                        : isCancelling
                                          ? "正在取消下载..."
                                          : statusText}
                                    </p>
                                    {isDownloading || isCancelling ? (
                                      <div className="mt-3 w-full h-1.5 bg-stone-200/70 dark:bg-stone-800 rounded-full overflow-hidden">
                                        <div
                                          className={`h-full transition-[width] duration-200 ease-out ${isCancelling ? "bg-amber-500" : "bg-accent"}`}
                                          style={{ width: `${typeof downloadProgress === "number" ? downloadProgress : 8}%` }}
                                        />
                                      </div>
                                    ) : null}
                                    {downloadFailed ? (
                                      <p className="mt-3 rounded-xl border border-red-200 bg-white/70 px-3 py-2 text-xs font-semibold text-red-700 dark:border-red-900/60 dark:bg-red-950/30 dark:text-red-200">
                                        {MODEL_DOWNLOAD_FAILED_MESSAGE}
                                      </p>
                                    ) : null}
                                  </div>
                                  {isCancelling ? (
                                    <button
                                      type="button"
                                      disabled
                                      className="rounded-xl border border-stone-200 bg-white px-3 py-2 text-xs font-bold text-stone-500 disabled:cursor-wait disabled:opacity-70 dark:border-stone-700 dark:bg-stone-900 dark:text-stone-500"
                                    >
                                      取消中
                                    </button>
                                  ) : isDownloading ? (
                                    <button
                                      type="button"
                                      onClick={() => onCancelFasterWhisperModelDownload?.(model.id)}
                                      className="rounded-xl border border-red-200 bg-red-50 px-3 py-2 text-xs font-bold text-red-700 transition-colors hover:bg-red-100 dark:border-red-900/60 dark:bg-red-950/30 dark:text-red-200 dark:hover:bg-red-950/50"
                                    >
                                      取消下载
                                    </button>
                                  ) : isCurrent && isReady ? (
                                    <button
                                      type="button"
                                      disabled
                                      className="rounded-xl border border-stone-200 bg-white px-3 py-2 text-xs font-bold text-stone-600 dark:border-stone-700 dark:bg-stone-900 dark:text-stone-400"
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
                                        if (downloadFailed || needsConfirm) {
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
                                      {downloadFailed ? "重试下载" : needsConfirm ? "确认下载?" : (isCurrent ? "下载并使用" : "下载")}
                                    </button>
                                  )}
                                </div>
                              </div>
                            );
                          })
                        )}
                      </div>
                    </WorkspaceSettingRow>
                  </>
                )}

                {currentAsrProvider === "aliyun_bailian" && (
                  <WorkspaceSettingRow
                    title="阿里云百炼 ASR"
                    description="云端转写配置。API Key 只保存到本机 .env，不写入 settings.toml。"
                    contentClassName="2xl:flex-1"
                  >
                    <div className="w-full rounded-2xl border border-stone-200 bg-white p-4 dark:border-stone-800 dark:bg-stone-900">
                      <div className="grid gap-4">
                        <label className="grid gap-1.5">
                          <span className="text-xs font-bold text-stone-600 dark:text-stone-400">模型</span>
                          <WorkspaceSelect
                            value={asrCloudModel}
                            options={[
                              { id: "paraformer-v2", label: "paraformer-v2" },
                            ]}
                            onChange={(nextValue) => onChangeSetting("asrCloudModel", nextValue)}
                            className="w-full"
                          />
                        </label>
                        <label className="grid gap-1.5">
                          <span className="text-xs font-bold text-stone-600 dark:text-stone-400">API 地址</span>
                          <WorkspaceTextInput
                            value={asrBaseUrl}
                            onChange={(nextValue) => onChangeSetting("asrBaseUrl", nextValue)}
                            onBlur={() => onSaveAsrSettings?.()}
                            onKeyDown={(event) => {
                              if (event.key === "Enter") {
                                event.preventDefault();
                                onSaveAsrSettings?.();
                              }
                            }}
                            placeholder="https://dashscope.aliyuncs.com"
                            className="w-full"
                          />
                        </label>
                        <label className="grid gap-1.5">
                          <span className="text-xs font-bold text-stone-600 dark:text-stone-400">API Key</span>
                          <div className="flex flex-col gap-2 sm:flex-row">
                            <WorkspaceTextInput
                              value={asrApiKeyDisplayValue}
                              onChange={(nextValue) => onChangeSetting("asrApiKey", nextValue)}
                              placeholder={ui.hasAsrApiKey ? "已保存" : "填写 DASHSCOPE_API_KEY"}
                              className="w-full"
                              type={showAsrApiKeyValue ? "text" : "password"}
                            />
                            <button
                              type="button"
                              disabled={asrApiKeyRevealLoading || !asrApiKeyStatus}
                              onClick={async () => {
                                if (!showAsrApiKeyValue && !draftAsrApiKey && ui.hasAsrApiKey) {
                                  setAsrApiKeyRevealLoading(true);
                                  const revealed = await onRevealAsrApiKey?.();
                                  setAsrApiKeyRevealLoading(false);
                                  if (!revealed) {
                                    return;
                                  }
                                }
                                setShowAsrApiKeyValue((value) => !value);
                              }}
                              className="rounded-xl border border-stone-200 px-3 py-2 text-xs font-bold text-stone-700 transition-colors hover:bg-stone-50 disabled:cursor-not-allowed disabled:opacity-50 dark:border-stone-700 dark:text-stone-200 dark:hover:bg-stone-800"
                            >
                              {asrApiKeyRevealLoading ? "读取中" : showAsrApiKeyValue ? "隐藏" : "显示"}
                            </button>
                            <button
                              type="button"
                              onClick={() => onSaveAsrSettings?.()}
                              className="rounded-xl bg-accent px-3 py-2 text-xs font-bold text-white transition-colors hover:bg-accent/90"
                            >
                              保存
                            </button>
                          </div>
                        </label>
                        <div>
                          <button
                            type="button"
                            disabled={asrTest.status === "testing"}
                            onClick={async () => {
                              if (typeof onTestAsrConnection !== "function") {
                                return;
                              }
                              setAsrTest({ status: "testing", message: "正在测试 ASR 连接..." });
                              const result = await onTestAsrConnection();
                              setAsrTest({
                                status: result?.ok ? "success" : "failed",
                                message: result?.message ?? "ASR 连接测试失败",
                              });
                            }}
                            className="w-full rounded-xl bg-stone-900 px-4 py-2.5 text-xs font-bold text-white transition-colors hover:bg-black disabled:cursor-not-allowed disabled:opacity-50 dark:bg-white dark:text-stone-900 dark:hover:bg-stone-100"
                          >
                            {asrTest.status === "testing" ? "测试中..." : "测试 ASR 连接"}
                          </button>
                          {asrTest.message ? (
                            <div
                              className={`mt-3 flex items-start gap-2 rounded-xl border px-3 py-2 text-xs font-semibold ${asrTest.status === "success"
                                ? "border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-900/60 dark:bg-emerald-950/30 dark:text-emerald-300"
                                : asrTest.status === "failed"
                                  ? "border-red-200 bg-red-50 text-red-700 dark:border-red-900/60 dark:bg-red-950/30 dark:text-red-300"
                                  : "border-stone-200 bg-stone-50 text-stone-600 dark:border-stone-800 dark:bg-stone-900 dark:text-stone-300"
                                }`}
                            >
                              <span className="min-w-0 flex-1">{asrTest.message}</span>
                              <button
                                type="button"
                                onClick={() => setAsrTest({ status: "idle", message: "" })}
                                className="inline-flex h-5 w-5 shrink-0 items-center justify-center rounded-full opacity-70 transition-colors hover:bg-white/70 hover:opacity-100 dark:hover:bg-black/20"
                                title="关闭测试结果"
                                aria-label="关闭测试结果"
                              >
                                <X size={12} />
                              </button>
                            </div>
                          ) : null}
                        </div>
                      </div>
                    </div>
                  </WorkspaceSettingRow>
                )}

                <WorkspaceSettingRow
                  title="上下文大小"
                  description="控制模型单次可用的上下文预算。"
                >
                  <WorkspaceTextInput
                    value={String(ui.windowTokens)}
                    onChange={(nextValue) => onChangeSetting("windowTokens", Number.parseInt(nextValue, 10) || 1)}
                    placeholder="1000000"
                    className="w-full sm:w-[180px]"
                    type="number"
                  />
                </WorkspaceSettingRow>

                <WorkspaceSettingRow
                  title="视频并行处理数"
                  description="控制全局最多同时处理多少个视频。"
                >
                  <WorkspaceTextInput
                    value={String(ui.videoGenerationConcurrency)}
                    onChange={(nextValue) => onChangeSetting("videoGenerationConcurrency", Number.parseInt(nextValue, 10) || 1)}
                    placeholder="1"
                    className="w-full sm:w-[180px]"
                    type="number"
                  />
                </WorkspaceSettingRow>

                <WorkspaceSettingRow
                  title="生成章节截图"
                  description="为 AI 概括的每个章节截取视频画面并嵌入总结。关闭后不再生成或保留章节图片。"
                >
                  <WorkspaceToggleSwitch
                    checked={ui.chapterScreenshotsEnabled}
                    ariaLabel="生成章节截图"
                    onChange={() => onChangeSetting("chapterScreenshotsEnabled", !ui.chapterScreenshotsEnabled)}
                  />
                </WorkspaceSettingRow>

                <WorkspaceSettingRow
                  title="AI 视频内容增强(不建议开启)"
                  description="利用大模型理解上下文后纠正转写文本，让总结结果更加精确。关闭可提高处理速度但会降低准确率。"
                >
                  <WorkspaceToggleSwitch
                    checked={ui.transcriptEnhancementEnabled}
                    onChange={() => onChangeSetting("transcriptEnhancementEnabled", !ui.transcriptEnhancementEnabled)}
                  />
                </WorkspaceSettingRow>
              </>
            )}

            {activeTab === "rag" && (
              <>
                <div className="mb-2">
                  <h3 className="text-2xl font-bold text-stone-900 dark:text-stone-100">对话管理</h3>
                  <p className="text-[13px] text-stone-600 dark:text-stone-400 mt-2">控制对话流程以及功能</p>
                </div>

                <WorkspaceSettingRow
                  title="回复长度"
                  description="控制回答详略"
                >
                  <WorkspaceSegmentedControl
                    value={ui.answerDetailLevel}
                    options={[
                      { id: "short", label: "短" },
                      { id: "medium", label: "中" },
                      { id: "long", label: "长" },
                    ]}
                    onChange={(nextValue) => onChangeSetting("answerDetailLevel", nextValue)}
                  />
                </WorkspaceSettingRow>

                <WorkspaceSettingRow
                  title="用户提示词"
                  description="自定义修改对话输出偏好"
                  contentClassName="2xl:flex-1"
                >
                  <textarea
                    value={ui.talkCustomPrompt}
                    onChange={(event) => onChangeSetting("talkCustomPrompt", event.target.value)}
                    placeholder="如：回答时先给结论，再用表格对比关键概念。"
                    rows={5}
                    className="block w-full min-w-0 resize-y rounded-xl border border-stone-200 bg-white px-4 py-2.5 text-sm leading-6 text-stone-900 outline-none focus:border-accent dark:border-stone-700 dark:bg-stone-900 dark:text-stone-100"
                  />
                </WorkspaceSettingRow>

                <WorkspaceSettingRow
                  title="检索硬件引擎"
                  description="选择向量检索的硬件计算引擎（CPU / GPU / 自动）。"
                >
                  <WorkspaceSegmentedControl
                    value={ui.ragEmbeddingDevice}
                    options={[
                      { id: "cpu", label: "CPU" },
                      {
                        id: "gpu",
                        label: "GPU",
                        disabled: !gpuEmbeddingAvailable,
                        disabledReason: unavailableReason,
                      },
                      { id: "auto", label: "自动" },
                    ]}
                    onChange={(nextValue) => onChangeSetting("ragEmbeddingDevice", nextValue)}
                  />
                </WorkspaceSettingRow>

                <WorkspaceSettingRow
                  title="开启 RAG 重排序模型"
                  description={
                    rerankerNeedsDownload
                      ? "重排序模型尚未下载，下载前不能开启 reranking。"
                      : "开启后将对检索到的资料进行二次精细筛选，提高回答准确度（响应时间略增）。"
                  }
                >
                  <div className="flex flex-col items-end gap-2">
                    <WorkspaceToggleSwitch
                      checked={effectiveRerankEnabled}
                      disabled={rerankerNeedsDownload}
                      onChange={() => {
                        if (!rerankerNeedsDownload) {
                          onChangeSetting("ragRerankEnabled", !effectiveRerankEnabled);
                        }
                      }}
                    />
                    {rerankerNeedsDownload ? (
                      <button
                        type="button"
                        onClick={() => onDownloadRagModel("reranker")}
                        disabled={isRerankerDownloading}
                        className="inline-flex items-center gap-2 rounded-xl bg-stone-900 px-3 py-2 text-xs font-bold text-white transition-colors hover:bg-black disabled:cursor-not-allowed disabled:opacity-50 dark:bg-stone-100 dark:text-stone-900 dark:hover:bg-white"
                      >
                        <Download size={14} />
                        下载重排序模型
                      </button>
                    ) : null}
                  </div>
                </WorkspaceSettingRow>

                <WorkspaceSettingRow
                  title="RAG 证据数量"
                  description={
                    effectiveRerankEnabled
                      ? `参考资料的引用数量。将从初步检索到的 ${ui.ragMaxHits * 4} 条候选段落中，精选最相关的 ${ui.ragMaxHits} 条作为回答依据。`
                      : `参考资料的引用数量。当前直接从检索结果中选取 ${ui.ragMaxHits} 条作为回答依据。`
                  }
                >
                  <WorkspaceTextInput
                    value={String(ui.ragMaxHits)}
                    onChange={(nextValue) => onChangeSetting("ragMaxHits", Number.parseInt(nextValue, 10) || 1)}
                    placeholder="5"
                    className="w-full sm:w-[180px]"
                    type="number"
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
                  title="模型协议"
                  description="选择模型服务商对接协议（第三方中转接口通常选择 openai）。"
                >
                  <WorkspaceProviderSelect
                    value={ui.llmProvider}
                    options={providerOptions}
                    onChange={(nextValue) => onChangeSetting("llmProvider", nextValue)}
                    className="w-full sm:w-[280px]"
                  />
                </WorkspaceSettingRow>

                <WorkspaceSettingRow
                  title="API 根地址"
                  description="自定义服务商的 API 基础 URL（留空则默认使用官方地址）。"
                >
                  <div className="w-full sm:w-[340px]">
                    <WorkspaceTextInput
                      value={ui.openaiBaseUrl}
                      onChange={(nextValue) => onChangeSetting("openaiBaseUrl", nextValue)}
                      onBlur={onSaveProviderSettings}
                      onKeyDown={saveProviderSettingsOnEnter}
                      placeholder="默认指向官方地址"
                      className="w-full"
                    />
                  </div>
                </WorkspaceSettingRow>

                <WorkspaceSettingRow
                  title="模型名称"
                  description="可探测当前接口可用模型并选择，或切换回手动填写模型标识。"
                >
                  <div className="flex w-full flex-col gap-2 sm:w-[340px] sm:flex-row sm:items-center">
                    {isProviderModelSelectActive ? (
                      <WorkspaceProviderSelect
                        value={ui.openaiModel}
                        options={providerModelOptions}
                        onChange={(nextValue) => {
                          if (typeof onSelectProviderModel === "function") {
                            onSelectProviderModel(nextValue);
                            return;
                          }
                          onChangeSetting("openaiModel", nextValue);
                        }}
                        className="w-full min-w-0 flex-1"
                        hideGroupLabels
                        ariaLabel="模型名称"
                      />
                    ) : (
                      <WorkspaceTextInput
                        value={ui.openaiModel}
                        onChange={(nextValue) => onChangeSetting("openaiModel", nextValue)}
                        onBlur={onSaveProviderSettings}
                        onKeyDown={saveProviderSettingsOnEnter}
                        placeholder="gpt-5.4"
                        className="w-full min-w-0 flex-1"
                      />
                    )}
                    <button
                      type="button"
                      onClick={handleProviderModelDiscovery}
                      disabled={providerModelDiscovery === "loading" || typeof onDiscoverProviderModels !== "function"}
                      aria-label={isProviderModelSelectActive ? "改为手动填写模型" : "探测模型"}
                      title={isProviderModelSelectActive ? "改为手动填写模型" : "探测模型"}
                      className="inline-flex h-10 shrink-0 items-center justify-center gap-2 rounded-xl border border-stone-200 px-3 text-xs font-bold text-stone-700 transition-colors hover:bg-stone-50 disabled:cursor-not-allowed disabled:opacity-50 dark:border-stone-700 dark:text-stone-200 dark:hover:bg-stone-800"
                    >
                      {providerModelDiscovery === "loading" ? (
                        <LoaderCircle size={15} className="animate-spin" />
                      ) : isProviderModelSelectActive ? (
                        <Check size={16} aria-hidden="true" />
                      ) : (
                        "探测模型"
                      )}
                    </button>
                  </div>
                </WorkspaceSettingRow>

                <WorkspaceSettingRow
                  title="思考强度"
                  description="控制模型的思考深度"
                >
                  <WorkspaceSegmentedControl
                    value={ui.reasoningEffort}
                    options={[
                      { id: "none", label: "无" },
                      { id: "low", label: "低" },
                      { id: "medium", label: "中" },
                      { id: "high", label: "高" },
                    ]}
                    onChange={(nextValue) => onChangeSetting("reasoningEffort", nextValue)}
                  />
                </WorkspaceSettingRow>

                {!isOllamaProvider ? (
                  <WorkspaceSettingRow
                    title="API Key"
                    description="访问大语言模型服务所需的授权 API 密钥。"
                    contentClassName="2xl:w-full 2xl:flex-1 2xl:shrink"
                  >
                    <div className="w-full min-w-0 max-w-full rounded-2xl border border-stone-200 bg-white px-4 py-3 dark:border-stone-700 dark:bg-stone-900">
                      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                        <div className="min-w-0">
                          <p className={`text-sm font-semibold ${hasApiKey ? "text-success" : "text-stone-600 dark:text-stone-400"}`}>
                            {hasApiKey ? "已配置" : "未配置"}
                          </p>
                          {apiKeyStatus ? (
                            <p className="mt-1 max-w-full break-all text-xs text-stone-600 [overflow-wrap:anywhere] dark:text-stone-400">
                              当前状态：{apiKeyDisplayValue}
                            </p>
                          ) : null}
                        </div>
                        <button
                          type="button"
                          onClick={async () => {
                            if (showApiKeyValue) {
                              setShowApiKeyValue(false);
                              return;
                            }
                            if (!draftApiKey && typeof onRevealOpenaiApiKey === "function") {
                              setApiKeyRevealLoading(true);
                              const revealedKey = await onRevealOpenaiApiKey();
                              setApiKeyRevealLoading(false);
                              if (!revealedKey) {
                                return;
                              }
                            }
                            setShowApiKeyValue(true);
                          }}
                          disabled={!apiKeyStatus || apiKeyRevealLoading}
                          className="w-full rounded-xl border border-stone-200 px-3 py-2 text-xs font-bold text-stone-600 transition-colors hover:bg-stone-50 disabled:cursor-not-allowed disabled:opacity-50 dark:border-stone-700 dark:text-stone-300 dark:hover:bg-stone-800 sm:w-auto"
                        >
                          {apiKeyRevealLoading ? "读取中..." : showApiKeyValue ? "隐藏" : "显示"}
                        </button>
                      </div>
                      {showApiKeyValue ? (
                        <textarea
                          value={ui.openaiApiKey}
                          onChange={(event) => onChangeSetting("openaiApiKey", event.target.value)}
                          placeholder={hasApiKey ? "输入新 Key 以覆盖现有配置" : "sk-..."}
                          rows={3}
                          className="mt-3 block w-full min-w-0 max-w-full resize-none overflow-y-auto break-all rounded-xl border border-stone-200 bg-white px-4 py-2.5 font-mono text-sm leading-6 text-stone-900 outline-none [overflow-wrap:anywhere] focus:border-accent dark:border-stone-700 dark:bg-stone-950 dark:text-stone-100"
                        />
                      ) : (
                        <WorkspaceTextInput
                          type="password"
                          value={ui.openaiApiKey}
                          onChange={(nextValue) => onChangeSetting("openaiApiKey", nextValue)}
                          placeholder={hasApiKey ? "输入新 Key 以覆盖现有配置" : "sk-..."}
                          className="mt-3 w-full min-w-0 dark:bg-stone-950"
                        />
                      )}
                      <div className="mt-3 flex justify-end">
                        <button
                          type="button"
                          onClick={onSaveApiKey}
                          disabled={!ui.openaiApiKey.trim()}
                          className="w-full rounded-xl bg-stone-900 px-4 py-2 text-xs font-bold text-white transition-colors hover:bg-black disabled:cursor-not-allowed disabled:opacity-50 dark:bg-white dark:text-stone-900 dark:hover:bg-stone-100 sm:w-auto"
                        >
                          保存 Key
                        </button>
                      </div>
                    </div>
                  </WorkspaceSettingRow>
                ) : null}

                <WorkspaceSettingRow
                  title="连接测试"
                  description="发起一次模型请求"
                >
                  <div className="w-full sm:w-[340px]">
                    <button
                      type="button"
                      onClick={async () => {
                        if (typeof onTestProviderConnection !== "function") {
                          return;
                        }
                        setProviderTest({ status: "testing", message: "正在测试模型连接..." });
                        const result = await onTestProviderConnection();
                        setProviderTest({
                          status: result?.ok ? "success" : "failed",
                          message: result?.message ?? "模型连接测试失败",
                        });
                      }}
                      disabled={providerTest.status === "testing"}
                      className="w-full rounded-xl bg-accent px-4 py-2.5 text-xs font-bold text-white transition-colors hover:bg-accent/90 disabled:cursor-not-allowed disabled:opacity-50"
                    >
                      {providerTest.status === "testing" ? "测试中..." : "测试"}
                    </button>
                    {providerTest.message ? (
                      <div
                        className={`mt-3 flex items-start gap-2 rounded-xl border px-3 py-2 text-xs font-semibold ${providerTest.status === "success"
                          ? "border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-900/60 dark:bg-emerald-950/30 dark:text-emerald-300"
                          : providerTest.status === "failed"
                            ? "border-red-200 bg-red-50 text-red-700 dark:border-red-900/60 dark:bg-red-950/30 dark:text-red-300"
                            : "border-stone-200 bg-stone-50 text-stone-600 dark:border-stone-800 dark:bg-stone-900 dark:text-stone-300"
                          }`}
                      >
                        <span className="min-w-0 flex-1">{providerTest.message}</span>
                        <button
                          type="button"
                          onClick={() => setProviderTest({ status: "idle", message: "" })}
                          className="inline-flex h-5 w-5 shrink-0 items-center justify-center rounded-full opacity-70 transition-colors hover:bg-white/70 hover:opacity-100 dark:hover:bg-black/20"
                          title="关闭测试结果"
                          aria-label="关闭测试结果"
                        >
                          <X size={12} />
                        </button>
                      </div>
                    ) : null}
                  </div>
                </WorkspaceSettingRow>

                <WorkspaceSettingRow
                  title="联网搜索"
                  description="开启后，Agent 仅在本地内容缺失或你明确要求联网时才会使用联网搜索。需要当前模型或供应商支持联网搜索。"
                >
                  <WorkspaceToggleSwitch
                    checked={ui.webSearchEnabled}
                    onChange={() => onChangeSetting("webSearchEnabled", !ui.webSearchEnabled)}
                  />
                </WorkspaceSettingRow>

                <WorkspaceSettingRow
                  title="API 用量统计"
                  description="查看真实 token 用量、供应商与模型分布。"
                >
                  <button
                    type="button"
                    onClick={onOpenUsagePage}
                    className="px-4 py-2.5 rounded-xl text-sm font-bold bg-accent text-white shadow-sm hover:bg-accent-hover transition-colors"
                  >
                    打开用量统计
                  </button>
                </WorkspaceSettingRow>
              </>
            )}

            {activeTab === "network" && (
              <>
                <div className="mb-2">
                  <h3 className="text-2xl font-bold text-stone-900 dark:text-stone-100">下载管理</h3>
                  <p className="text-[13px] text-stone-600 dark:text-stone-400 mt-2">
                    管理内容下载
                  </p>
                </div>

                <WorkspaceSettingRow
                  title="HuggingFace 镜像地址"
                  description="模型下载镜像地址。留空后保存将使用 HuggingFace 官方源。"
                >
                  <WorkspaceTextInput
                    value={ui.hfEndpoint}
                    onChange={(nextValue) => onChangeSetting("hfEndpoint", nextValue)}
                    onBlur={onSaveProviderSettings}
                    onKeyDown={saveProviderSettingsOnEnter}
                    placeholder="https://huggingface.co"
                    className="w-full sm:w-[340px]"
                  />
                </WorkspaceSettingRow>

                <WorkspaceSettingRow
                  title="RAG 检索模型"
                  description="Series 对话需要embdding模型，reranking模型强化检索能力(可选)"
                >
                  <div className="w-full flex flex-col gap-3">
                    {ragModelsLoading && !ragModels.length ? (
                      <div className="flex items-center gap-2 text-sm text-stone-600 dark:text-stone-400">
                        <LoaderCircle size={16} className="animate-spin" />
                        正在读取 RAG 模型状态...
                      </div>
                    ) : (
                      ragModels.map((model) => {
                        const isCancelling = model.status === "cancelling";
                        const isDownloading = !isCancelling && (
                          model.status === "running" || downloadingRagModelKey === model.key
                        );
                        const downloadFailed = model.status === "failed" && Boolean(model.error);
                        const statusText = model.downloaded
                          ? "已下载到本地"
                          : isCancelling
                            ? "正在取消下载..."
                            : isDownloading
                            ? `正在下载 RAG 模型... ${typeof model.progress === "number" ? `${Math.round(model.progress)}%` : ""}`.trim()
                            : downloadFailed
                              ? "下载失败"
                              : "尚未下载";
                        return (
                          <div
                            key={model.key}
                            className={`rounded-2xl border p-4 transition-colors ${downloadFailed
                              ? "border-red-200 bg-red-50/70 dark:border-red-900/60 dark:bg-red-950/20"
                              : model.downloaded
                                ? "border-accent/30 bg-info-subtle dark:bg-info-subtle"
                                : "border-stone-200 dark:border-stone-800"
                              }`}
                          >
                            <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
                              <div className="min-w-0">
                                <strong className="break-words text-sm font-bold text-stone-900 dark:text-stone-100">{model.label}</strong>
                                <p className="mt-1 text-xs text-stone-600 dark:text-stone-400">{statusText}</p>
                                {isDownloading || isCancelling ? (
                                  <div className="mt-3 w-full h-1.5 bg-stone-200/70 dark:bg-stone-800 rounded-full overflow-hidden">
                                    <div
                                      className="h-full bg-accent transition-[width] duration-200 ease-out"
                                      style={{ width: `${typeof model.progress === "number" ? model.progress : 8}%` }}
                                    />
                                  </div>
                                ) : null}
                                {downloadFailed ? (
                                  <p className="mt-3 rounded-xl border border-red-200 bg-white/70 px-3 py-2 text-xs font-semibold text-red-700 dark:border-red-900/60 dark:bg-red-950/30 dark:text-red-200">
                                    {MODEL_DOWNLOAD_FAILED_MESSAGE}
                                  </p>
                                ) : null}
                              </div>
                              {isCancelling ? (
                                <button
                                  type="button"
                                  disabled
                                  className="rounded-xl border border-stone-200 bg-white px-3 py-2 text-xs font-bold text-stone-500 disabled:cursor-wait disabled:opacity-70 dark:border-stone-700 dark:bg-stone-900 dark:text-stone-500"
                                >
                                  取消中
                                </button>
                              ) : isDownloading ? (
                                <button
                                  type="button"
                                  onClick={() => onCancelRagModelDownload?.(model.key)}
                                  className="rounded-xl border border-red-200 bg-red-50 px-3 py-2 text-xs font-bold text-red-700 transition-colors hover:bg-red-100 dark:border-red-900/60 dark:bg-red-950/30 dark:text-red-200 dark:hover:bg-red-950/50"
                                >
                                  取消下载
                                </button>
                              ) : model.downloaded ? (
                                <button
                                  type="button"
                                  disabled
                                  className="rounded-xl border border-stone-200 bg-white px-3 py-2 text-xs font-bold text-stone-600 dark:border-stone-700 dark:bg-stone-900 dark:text-stone-400"
                                >
                                  使用中
                                </button>
                              ) : (
                                <button
                                  type="button"
                                  onClick={() => onDownloadRagModel(model.key)}
                                  disabled={isDownloading}
                                  className="inline-flex items-center gap-2 rounded-xl bg-stone-900 px-3 py-2 text-xs font-bold text-white transition-colors hover:bg-black disabled:cursor-not-allowed disabled:opacity-50 dark:bg-stone-100 dark:text-stone-900 dark:hover:bg-white"
                                >
                                  <Download size={14} />
                                  {downloadFailed ? "重试下载" : "下载"}
                                </button>
                              )}
                            </div>
                          </div>
                        );
                      })
                    )}
                  </div>
                </WorkspaceSettingRow>
              </>
            )}

            {activeTab === "external-import" && (
              <>
                <div className="mb-2">
                  <h3 className="text-2xl font-bold text-stone-900 dark:text-stone-100">外部API</h3>
                  <p className="text-[13px] text-stone-600 dark:text-stone-400 mt-2">
                    控制外部API的设置。
                  </p>
                </div>

                <WorkspaceSettingRow
                  title="超星请求间隔"
                  description="正常列举课程、章节、视频时的请求间隔，单位秒。越小获取越快。默认 0.2。"
                >
                  <WorkspaceTextInput
                    type="number"
                    value={String(ui.chaoxingRequestDelaySeconds)}
                    onChange={(nextValue) => onChangeSetting("chaoxingRequestDelaySeconds", Number(nextValue))}
                    placeholder="0.2"
                    className="w-full sm:w-[180px]"
                  />
                </WorkspaceSettingRow>

                <WorkspaceSettingRow
                  title="超星初始化获取间隔"
                  description="初始化登录后获取课程的间隔。越小获取越快。默认 0.3。"
                >
                  <WorkspaceTextInput
                    type="number"
                    value={String(ui.chaoxingInitCourseDelaySeconds)}
                    onChange={(nextValue) => onChangeSetting("chaoxingInitCourseDelaySeconds", Number(nextValue))}
                    placeholder="0.3"
                    className="w-full sm:w-[180px]"
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
              <p className="text-[13px] leading-relaxed text-stone-600 dark:text-stone-400 mb-6">
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
