import { motion, AnimatePresence } from "framer-motion";
import {
  BarElement,
  CategoryScale,
  Chart as ChartJS,
  LinearScale,
  Tooltip,
} from "chart.js";
import { Bar } from "react-chartjs-2";
import { popScaleVariant, blurVariant, staggerContainer, fadeUpVariant } from "../../../lib/animations";
import { X, LoaderCircle, BarChart3, Zap, MessageSquare, ArrowUpRight, ArrowDownRight, Clock, Server } from "lucide-react";

ChartJS.register(CategoryScale, LinearScale, BarElement, Tooltip);

export function WorkspaceUsagePage({
  usage,
  range,
  loading,
  error,
  onChangeRange,
  onClose,
}) {
  const ranges = [
    { id: "today", label: "今日" },
    { id: "7d", label: "7 天" },
    { id: "30d", label: "30 天" },
    { id: "all", label: "全部" },
  ];

  const categoryTotals = new Map((usage?.byCategory ?? []).map((item) => [item.category, item]));
  const generation = categoryTotals.get("generation");
  const chat = categoryTotals.get("chat");
  const total = usage?.total ?? { promptTokens: 0, completionTokens: 0, totalTokens: 0 };
  const providers = usage?.byProvider ?? [];
  const recent = usage?.recent ?? [];
  const timeline = usage?.timeline ?? [];
  const timelineGranularity = usage?.timelineGranularity ?? "day";
  const maxProviderTokens = providers.length ? Math.max(...providers.map((p) => p.totalTokens)) : 0;

  return (
    <motion.section
      variants={popScaleVariant}
      initial="initial"
      animate="animate"
      exit="exit"
      className="bg-white dark:bg-neutral-950 rounded-[2rem] shadow-2xl border border-stone-200 dark:border-white/10 w-full max-w-6xl h-[85vh] flex flex-col overflow-hidden pointer-events-auto"
      aria-label="API 用量统计"
    >
      {/* Header */}
      <div className="sticky top-0 bg-white/80 dark:bg-neutral-950/80 backdrop-blur-md z-30 px-10 py-6 flex items-center justify-between border-b border-stone-200/60 dark:border-white/5 shrink-0">
        <div className="flex items-center gap-4">
          <div className="flex items-center justify-center w-10 h-10 rounded-xl bg-accent/10 text-accent">
            <BarChart3 size={20} strokeWidth={2.2} />
          </div>
          <div>
            <p className="text-[10px] font-bold text-accent tracking-widest uppercase">Analytics</p>
            <h2 className="text-xl font-bold text-stone-900 dark:text-stone-100 tracking-tight">API 用量统计</h2>
          </div>
        </div>
        <button
          type="button"
          className="inline-flex items-center justify-center w-9 h-9 rounded-full bg-stone-100 dark:bg-stone-800 text-stone-500 hover:bg-stone-200 dark:hover:bg-stone-700 transition-colors shadow-sm"
          onClick={onClose}
          aria-label="关闭面板"
        >
          <X size={18} />
        </button>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto px-10 pb-16">
        <div className="max-w-5xl mx-auto">

          {/* Range Selector */}
          <div className="flex flex-wrap items-center gap-2 mt-8 mb-6">
            <span className="text-xs font-semibold text-stone-500 dark:text-stone-400 mr-1">统计范围</span>
            {ranges.map((item) => (
              <button
                key={item.id}
                type="button"
                onClick={() => onChangeRange?.(item.id)}
                className={`rounded-full px-3.5 py-1.5 text-xs font-bold transition-colors ${range === item.id
                  ? "bg-accent text-white shadow-sm"
                  : "bg-stone-100 text-stone-600 hover:bg-stone-200 dark:bg-stone-800 dark:text-stone-300 dark:hover:bg-stone-700"
                  }`}
              >
                {item.label}
              </button>
            ))}
          </div>

          {/* Loading / Error */}
          {loading && !usage ? (
            <div className="flex items-center justify-center gap-3 py-24 text-stone-500 dark:text-stone-400">
              <LoaderCircle size={20} className="animate-spin" />
              <span className="text-sm font-semibold">正在读取用量统计...</span>
            </div>
          ) : error ? (
            <div className="rounded-2xl border border-red-200 bg-red-50 px-5 py-4 text-sm font-semibold text-red-700 dark:border-red-900/60 dark:bg-red-950/30 dark:text-red-300">
              {error}
            </div>
          ) : (
            <motion.div
              variants={staggerContainer}
              initial="initial"
              animate="animate"
              className="flex flex-col gap-8"
            >
              {/* ── Hero Stats ── */}
              <motion.div variants={fadeUpVariant} className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
                <UsageStatCard
                  label="总 Token"
                  value={total.totalTokens}
                  icon={BarChart3}
                  accentClass="text-accent bg-accent/10"
                  large
                  loading={loading}
                />
                <UsageStatCard
                  label="生成消耗"
                  value={generation?.totalTokens ?? 0}
                  icon={Zap}
                  accentClass="text-indigo-500 bg-indigo-500/10 dark:text-indigo-400 dark:bg-indigo-400/10"
                  loading={loading}
                />
                <UsageStatCard
                  label="对话消耗"
                  value={chat?.totalTokens ?? 0}
                  icon={MessageSquare}
                  accentClass="text-emerald-500 bg-emerald-500/10 dark:text-emerald-400 dark:bg-emerald-400/10"
                  loading={loading}
                />
                <div className="rounded-2xl border border-stone-200 bg-white p-4 dark:border-stone-800 dark:bg-stone-900/70 flex flex-col gap-3">
                  <div className="flex items-center gap-2">
                    <div className="flex items-center justify-center w-7 h-7 rounded-lg text-amber-500 bg-amber-500/10 dark:text-amber-400 dark:bg-amber-400/10">
                      <ArrowUpRight size={14} strokeWidth={2.5} />
                    </div>
                    <span className="text-xs font-semibold text-stone-500 dark:text-stone-400">Prompt / Completion</span>
                  </div>
                  <div className="flex items-baseline gap-3">
                    <div className="min-w-0">
                      <p className={`text-lg font-black tabular-nums text-stone-900 dark:text-stone-100 ${loading ? "opacity-60" : ""}`}>
                        {formatTokenCount(total.promptTokens)}
                      </p>
                      <p className="text-[10px] font-semibold text-stone-400 dark:text-stone-500 uppercase tracking-wide">Prompt</p>
                    </div>
                    <span className="text-stone-300 dark:text-stone-700">/</span>
                    <div className="min-w-0">
                      <p className={`text-lg font-black tabular-nums text-stone-900 dark:text-stone-100 ${loading ? "opacity-60" : ""}`}>
                        {formatTokenCount(total.completionTokens)}
                      </p>
                      <p className="text-[10px] font-semibold text-stone-400 dark:text-stone-500 uppercase tracking-wide">Completion</p>
                    </div>
                  </div>
                </div>
              </motion.div>

              {/* ── Bar Chart — Token Trend by Timeline Buckets ── */}
              {timeline.length > 0 && (
                <motion.div variants={fadeUpVariant}>
                  <UsageBarChart
                    timeline={timeline}
                    granularity={timelineGranularity}
                    range={range}
                    loading={loading}
                  />
                </motion.div>
              )}

              {/* ── Providers & Models ── */}
              <motion.div variants={fadeUpVariant}>
                <h3 className="text-sm font-bold text-stone-900 dark:text-stone-100 mb-3 flex items-center gap-2">
                  <Server size={14} strokeWidth={2.5} className="text-stone-400" />
                  供应商与模型
                  <span className="text-[11px] font-semibold text-stone-400 dark:text-stone-500">({providers.length})</span>
                </h3>
                {providers.length ? (
                  <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
                    {providers.map((item) => (
                      <div
                        key={`${item.provider}|${item.baseUrl}|${item.model}`}
                        className={`rounded-2xl border border-stone-200 bg-stone-50 px-4 py-3 transition-opacity dark:border-stone-800 dark:bg-stone-950/60 ${loading ? "opacity-60" : ""}`}
                      >
                        <div className="flex items-start justify-between gap-3 mb-2">
                          <div className="min-w-0">
                            <p className="truncate text-sm font-bold text-stone-800 dark:text-stone-200">
                              {item.provider} · {item.model}
                            </p>
                            <p className="mt-0.5 truncate text-[11px] text-stone-500 dark:text-stone-500">
                              {item.baseUrl || "默认接口"}
                            </p>
                          </div>
                          <span className="shrink-0 text-sm font-black tabular-nums text-stone-900 dark:text-stone-100">
                            {formatTokenCount(item.totalTokens)}
                          </span>
                        </div>
                        {/* Progress bar */}
                        {maxProviderTokens > 0 && (
                          <div className="h-1.5 w-full rounded-full bg-stone-200 dark:bg-stone-800 overflow-hidden">
                            <div
                              className="h-full rounded-full bg-accent transition-all duration-500 ease-out"
                              style={{ width: `${Math.max(2, (item.totalTokens / maxProviderTokens) * 100)}%` }}
                            />
                          </div>
                        )}
                        <div className="flex items-center gap-4 mt-2 text-[11px] text-stone-500 dark:text-stone-400">
                          <span className="flex items-center gap-1">
                            <ArrowUpRight size={10} strokeWidth={2.5} />
                            Prompt {formatTokenCount(item.promptTokens)}
                          </span>
                          <span className="flex items-center gap-1">
                            <ArrowDownRight size={10} strokeWidth={2.5} />
                            Completion {formatTokenCount(item.completionTokens)}
                          </span>
                        </div>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="rounded-2xl border border-dashed border-stone-200 px-4 py-6 text-center text-sm text-stone-500 dark:border-stone-800 dark:text-stone-400">
                    暂无真实 token 用量记录。
                  </div>
                )}
              </motion.div>

              {/* ── Recent Records Table ── */}
              <motion.div variants={fadeUpVariant}>
                <h3 className="text-sm font-bold text-stone-900 dark:text-stone-100 mb-3 flex items-center gap-2">
                  <Clock size={14} strokeWidth={2.5} className="text-stone-400" />
                  最近调用记录
                  <span className="text-[11px] font-semibold text-stone-400 dark:text-stone-500">({recent.length})</span>
                </h3>
                {recent.length ? (
                  <div className={`overflow-hidden rounded-2xl border border-stone-200 transition-opacity dark:border-stone-800 ${loading ? "opacity-60" : ""}`}>
                    <div className="overflow-x-auto">
                      <table className="w-full text-left">
                        <thead>
                          <tr className="border-b border-stone-200 dark:border-stone-800 bg-stone-50 dark:bg-stone-900/50">
                            <th className="px-4 py-2.5 text-[11px] font-bold text-stone-500 dark:text-stone-400 uppercase tracking-wider">时间</th>
                            <th className="px-4 py-2.5 text-[11px] font-bold text-stone-500 dark:text-stone-400 uppercase tracking-wider">类别</th>
                            <th className="px-4 py-2.5 text-[11px] font-bold text-stone-500 dark:text-stone-400 uppercase tracking-wider">供应商 · 模型</th>
                            <th className="px-4 py-2.5 text-[11px] font-bold text-stone-500 dark:text-stone-400 uppercase tracking-wider text-right">Prompt</th>
                            <th className="px-4 py-2.5 text-[11px] font-bold text-stone-500 dark:text-stone-400 uppercase tracking-wider text-right">Completion</th>
                            <th className="px-4 py-2.5 text-[11px] font-bold text-stone-500 dark:text-stone-400 uppercase tracking-wider text-right">Total</th>
                          </tr>
                        </thead>
                        <tbody>
                          {recent.map((item, index) => (
                            <tr
                              key={`${item.createdAt}-${index}`}
                              className="border-b border-stone-100 last:border-b-0 dark:border-stone-800/60 hover:bg-stone-50/50 dark:hover:bg-stone-900/30 transition-colors"
                            >
                              <td className="px-4 py-2.5 text-xs text-stone-600 dark:text-stone-400 whitespace-nowrap tabular-nums">
                                {formatUsageTime(item.createdAt)}
                              </td>
                              <td className="px-4 py-2.5">
                                <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-bold ${
                                  item.category === "chat"
                                    ? "bg-emerald-50 text-emerald-600 dark:bg-emerald-950/40 dark:text-emerald-400"
                                    : "bg-indigo-50 text-indigo-600 dark:bg-indigo-950/40 dark:text-indigo-400"
                                }`}>
                                  {item.category === "chat" ? "对话" : "生成"}
                                </span>
                              </td>
                              <td className="px-4 py-2.5 text-xs font-semibold text-stone-800 dark:text-stone-200 max-w-[200px] truncate">
                                {item.provider} · {item.model}
                              </td>
                              <td className="px-4 py-2.5 text-xs tabular-nums text-stone-600 dark:text-stone-400 text-right">
                                {formatTokenCount(item.promptTokens)}
                              </td>
                              <td className="px-4 py-2.5 text-xs tabular-nums text-stone-600 dark:text-stone-400 text-right">
                                {formatTokenCount(item.completionTokens)}
                              </td>
                              <td className="px-4 py-2.5 text-xs font-bold tabular-nums text-stone-900 dark:text-stone-100 text-right">
                                {formatTokenCount(item.totalTokens)}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                ) : (
                  <div className="rounded-2xl border border-dashed border-stone-200 px-4 py-6 text-center text-sm text-stone-500 dark:border-stone-800 dark:text-stone-400">
                    暂无最近记录。
                  </div>
                )}
              </motion.div>
            </motion.div>
          )}
        </div>
      </div>
    </motion.section>
  );
}


/* ── Sub-components ── */

function UsageStatCard({ label, value, icon: Icon, accentClass, large = false, loading = false }) {
  return (
    <div className={`rounded-2xl border border-stone-200 bg-white p-4 dark:border-stone-800 dark:bg-stone-900/70 flex flex-col gap-2 ${large ? "sm:col-span-2 lg:col-span-1" : ""}`}>
      <div className="flex items-center gap-2">
        <div className={`flex items-center justify-center w-7 h-7 rounded-lg ${accentClass}`}>
          <Icon size={14} strokeWidth={2.5} />
        </div>
        <span className="text-xs font-semibold text-stone-500 dark:text-stone-400">{label}</span>
      </div>
      <p className={`text-2xl font-black tabular-nums text-stone-900 dark:text-stone-100 transition-opacity ${loading ? "opacity-60" : ""}`}>
        {formatTokenCount(value)}
      </p>
    </div>
  );
}

function UsageBarChart({ timeline, granularity, range, loading = false }) {
  const chartRows = buildUsageTrendRows(timeline, granularity, range);
  const chartData = {
    labels: chartRows.map((item) => item.label),
    datasets: [
      {
        label: "生成",
        data: chartRows.map((item) => item.generationTokens),
        backgroundColor: createChartGradient("#6366f1", "#a5b4fc"),
        borderRadius: 10,
        borderSkipped: false,
        barThickness: chartRows.length <= 4 ? 34 : "flex",
        maxBarThickness: 34,
      },
      {
        label: "对话",
        data: chartRows.map((item) => item.chatTokens),
        backgroundColor: createChartGradient("#10b981", "#6ee7b7"),
        borderRadius: 10,
        borderSkipped: false,
        barThickness: chartRows.length <= 4 ? 34 : "flex",
        maxBarThickness: 34,
      },
    ],
  };
  const chartOptions = {
    responsive: true,
    maintainAspectRatio: false,
    animation: {
      duration: 260,
    },
    interaction: {
      mode: "index",
      intersect: false,
    },
    plugins: {
      legend: {
        display: false,
      },
      tooltip: {
        displayColors: false,
        padding: 12,
        backgroundColor: "rgba(28, 25, 23, 0.94)",
        titleColor: "#fafaf9",
        bodyColor: "#e7e5e4",
        cornerRadius: 14,
        callbacks: {
          title(items) {
            const row = chartRows[items[0]?.dataIndex ?? 0];
            return row ? `${row.label} · ${formatTokenCount(row.totalTokens)} tokens` : "";
          },
          label(item) {
            const row = chartRows[item.dataIndex];
            if (!row) {
              return "";
            }
            const value = typeof item.raw === "number" ? item.raw : 0;
            return `${item.dataset.label} ${formatTokenCount(value)} tokens`;
          },
        },
      },
    },
    scales: {
      x: {
        stacked: true,
        grid: {
          display: false,
        },
        ticks: {
          color: "#78716c",
          font: {
            size: 11,
            weight: 700,
          },
          maxRotation: 0,
          autoSkip: false,
          callback(value, index) {
            return chartRows[index]?.showAxisTick ? chartRows[index].label : "";
          },
        },
        border: {
          display: false,
        },
      },
      y: {
        beginAtZero: true,
        grid: {
          color: "rgba(168, 162, 158, 0.22)",
          drawTicks: false,
        },
        ticks: {
          color: "#a8a29e",
          padding: 10,
          font: {
            size: 11,
            weight: 700,
          },
          callback: formatCompactTokenCount,
        },
        border: {
          display: false,
        },
      },
    },
  };

  return (
    <div className="overflow-hidden rounded-3xl border border-stone-200 bg-gradient-to-br from-white via-stone-50/80 to-white p-5 shadow-sm dark:border-stone-800 dark:from-stone-950 dark:via-stone-900/70 dark:to-neutral-950">
      <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h4 className="text-sm font-bold text-stone-900 dark:text-stone-100">Token 用量趋势</h4>
          <p className="mt-1 text-xs font-semibold text-stone-500 dark:text-stone-400">
            按时间聚合真实 token 消耗，悬停查看明细。
          </p>
        </div>
        <div className="flex items-center gap-3 text-[11px] font-bold text-stone-500 dark:text-stone-400">
          <span className="flex items-center gap-1.5">
            <span className="inline-block h-2.5 w-2.5 rounded-full bg-indigo-500 shadow-[0_0_0_3px_rgba(99,102,241,0.12)]" />
            生成
          </span>
          <span className="flex items-center gap-1.5">
            <span className="inline-block h-2.5 w-2.5 rounded-full bg-emerald-500 shadow-[0_0_0_3px_rgba(16,185,129,0.12)]" />
            对话
          </span>
        </div>
      </div>

      <div className={`h-52 transition-opacity ${loading ? "opacity-60" : ""}`}>
        <Bar data={chartData} options={chartOptions} />
      </div>
    </div>
  );
}

export function buildUsageTrendRows(timeline, granularity = "day", range = "7d") {
  const buckets = Array.isArray(timeline) ? timeline : [];
  return buckets.map((bucket, index) => ({
    label: formatUsageBucketLabel(bucket.startedAt, granularity),
    generationTokens: toFiniteTokenValue(bucket.generationTokens),
    chatTokens: toFiniteTokenValue(bucket.chatTokens),
    totalTokens: toFiniteTokenValue(bucket.totalTokens),
    showAxisTick: shouldShowUsageAxisTick(index, buckets.length, granularity, range),
  }));
}

function shouldShowUsageAxisTick(index, total, granularity, range) {
  if (total <= 12) {
    return true;
  }
  if (index === 0 || index === total - 1) {
    return true;
  }
  if (granularity === "hour") {
    return index % 6 === 0;
  }
  if (range === "30d" && granularity === "day") {
    return index % 7 === 0;
  }
  if (granularity === "week" || granularity === "month") {
    return true;
  }
  return index % 7 === 0;
}

function formatUsageBucketLabel(value, granularity) {
  if (!value) {
    return "";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  if (granularity === "hour") {
    return date.toLocaleTimeString("zh-CN", {
      hour: "2-digit",
      minute: "2-digit",
    });
  }
  if (granularity === "month") {
    return date.toLocaleDateString("zh-CN", {
      year: "numeric",
      month: "2-digit",
    });
  }
  return date.toLocaleDateString("zh-CN", {
    month: "numeric",
    day: "numeric",
  });
}

function toFiniteTokenValue(value) {
  return typeof value === "number" && Number.isFinite(value) ? value : 0;
}

function createChartGradient(startColor, endColor) {
  return (context) => {
    const { chart } = context;
    const { ctx, chartArea } = chart;
    if (!chartArea || typeof CanvasGradient === "undefined") {
      return startColor;
    }
    const gradient = ctx.createLinearGradient(0, chartArea.top, 0, chartArea.bottom);
    gradient.addColorStop(0, startColor);
    gradient.addColorStop(1, endColor);
    return gradient;
  };
}


/* ── Utilities ── */

function formatTokenCount(value) {
  const number = typeof value === "number" && Number.isFinite(value) ? value : 0;
  return new Intl.NumberFormat("zh-CN").format(number);
}

function formatCompactTokenCount(value) {
  const number = typeof value === "number" && Number.isFinite(value) ? value : 0;
  return new Intl.NumberFormat("zh-CN", {
    notation: "compact",
    maximumFractionDigits: 1,
  }).format(number);
}

function formatUsageTime(value) {
  if (!value) {
    return "未知时间";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return date.toLocaleString("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}
