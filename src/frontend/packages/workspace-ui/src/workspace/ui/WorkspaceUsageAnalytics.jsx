import { motion } from "framer-motion";
import {
  BarElement,
  CategoryScale,
  Chart as ChartJS,
  LinearScale,
  Tooltip,
} from "chart.js";
import { Bar } from "react-chartjs-2";
import { staggerContainer, fadeUpVariant } from "../../lib/animations";
import { LoaderCircle, BarChart3, Zap, MessageSquare, ArrowUpRight, ArrowDownRight, Clock, Server } from "lucide-react";

ChartJS.register(CategoryScale, LinearScale, BarElement, Tooltip);

export function WorkspaceUsageAnalytics({
  usage,
  range,
  loading,
  error,
  onChangeRange,
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
    <div className="max-w-5xl mx-auto">

          {/* Range Selector */}
          <div className="flex flex-wrap items-center gap-2 mt-8 mb-6">
            <span className="text-xs font-semibold text-subtle mr-1">统计范围</span>
            {ranges.map((item) => (
              <button
                key={item.id}
                type="button"
                onClick={() => onChangeRange?.(item.id)}
                className={`rounded-full px-3.5 py-1.5 text-xs font-bold transition-colors ${range === item.id
                  ? "bg-accent text-on-accent shadow-sm"
                  : "bg-soft text-subtle hover:bg-softer"
                  }`}
              >
                {item.label}
              </button>
            ))}
          </div>

          {/* Loading / Error */}
          {loading && !usage ? (
            <div className="flex items-center justify-center gap-3 py-24 text-subtle">
              <LoaderCircle size={20} className="animate-spin" />
              <span className="text-sm font-semibold">正在读取用量统计...</span>
            </div>
          ) : error ? (
            <div className="rounded-2xl border border-danger-border bg-danger-subtle px-5 py-4 text-sm font-semibold text-danger">
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
                  accentClass="text-accent bg-accent/10"
                  loading={loading}
                />
                <UsageStatCard
                  label="对话消耗"
                  value={chat?.totalTokens ?? 0}
                  icon={MessageSquare}
                  accentClass="text-success-muted bg-success/10"
                  loading={loading}
                />
                <div className="rounded-2xl border border-line bg-surface p-4 flex flex-col gap-3">
                  <div className="flex items-center gap-2">
                    <div className="flex items-center justify-center w-7 h-7 rounded-lg text-warning-muted bg-warning/10">
                      <ArrowUpRight size={14} strokeWidth={2.5} />
                    </div>
                    <span className="text-xs font-semibold text-subtle">Prompt / Completion</span>
                  </div>
                  <div className="flex items-baseline gap-3">
                    <div className="min-w-0">
                      <p className={`text-lg font-black tabular-nums text-strong ${loading ? "opacity-60" : ""}`}>
                        {formatTokenCount(total.promptTokens)}
                      </p>
                      <p className="text-xs font-semibold text-faint uppercase tracking-wide">输入</p>
                    </div>
                    <span className="text-faint">/</span>
                    <div className="min-w-0">
                      <p className={`text-lg font-black tabular-nums text-strong ${loading ? "opacity-60" : ""}`}>
                        {formatTokenCount(total.completionTokens)}
                      </p>
                      <p className="text-xs font-semibold text-faint uppercase tracking-wide">输出</p>
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
                <h3 className="text-sm font-bold text-strong mb-3 flex items-center gap-2">
                  <Server size={14} strokeWidth={2.5} className="text-faint" />
                  供应商与模型
                  <span className="text-xs font-semibold text-faint">({providers.length})</span>
                </h3>
                {providers.length ? (
                  <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
                    {providers.map((item) => (
                      <div
                        key={`${item.provider}|${item.baseUrl}|${item.model}`}
                        className={`rounded-2xl border border-line bg-muted px-4 py-3 transition-opacity ${loading ? "opacity-60" : ""}`}
                      >
                        <div className="flex items-start justify-between gap-3 mb-2">
                          <div className="min-w-0">
                            <p className="truncate text-sm font-bold text-body">
                              {item.provider} · {item.model}
                            </p>
                            <p className="mt-0.5 truncate text-xs text-subtle">
                              {item.baseUrl || "默认接口"}
                            </p>
                          </div>
                          <span className="shrink-0 text-sm font-black tabular-nums text-strong">
                            {formatTokenCount(item.totalTokens)}
                          </span>
                        </div>
                        {/* Progress bar */}
                        {maxProviderTokens > 0 && (
                          <div className="h-1.5 w-full rounded-full bg-softer overflow-hidden">
                            <div
                              className="h-full rounded-full bg-accent transition-all duration-500 ease-out"
                              style={{ width: `${Math.max(2, (item.totalTokens / maxProviderTokens) * 100)}%` }}
                            />
                          </div>
                        )}
                        <div className="flex items-center gap-4 mt-2 text-xs text-subtle">
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
                  <div className="rounded-2xl border border-dashed border-line px-4 py-6 text-center text-sm text-subtle">
                    暂无真实 token 用量记录。
                  </div>
                )}
              </motion.div>

              {/* ── Recent Records Table ── */}
              <motion.div variants={fadeUpVariant}>
                <h3 className="text-sm font-bold text-strong mb-3 flex items-center gap-2">
                  <Clock size={14} strokeWidth={2.5} className="text-faint" />
                  最近调用记录
                  <span className="text-xs font-semibold text-faint">({recent.length})</span>
                </h3>
                {recent.length ? (
                  <div className={`overflow-hidden rounded-2xl border border-line transition-opacity ${loading ? "opacity-60" : ""}`}>
                    <div className="overflow-x-auto">
                      <table className="w-full text-left">
                        <thead>
                          <tr className="border-b border-line bg-muted">
                            <th className="px-4 py-2.5 text-xs font-bold text-subtle uppercase tracking-wider">时间</th>
                            <th className="px-4 py-2.5 text-xs font-bold text-subtle uppercase tracking-wider">类别</th>
                            <th className="px-4 py-2.5 text-xs font-bold text-subtle uppercase tracking-wider">供应商 · 模型</th>
                            <th className="px-4 py-2.5 text-xs font-bold text-subtle uppercase tracking-wider text-right">输入</th>
                            <th className="px-4 py-2.5 text-xs font-bold text-subtle uppercase tracking-wider text-right">输出</th>
                            <th className="px-4 py-2.5 text-xs font-bold text-subtle uppercase tracking-wider text-right">合计</th>
                          </tr>
                        </thead>
                        <tbody>
                          {recent.map((item, index) => (
                            <tr
                              key={`${item.createdAt}-${index}`}
                              className="border-b border-line-soft last:border-b-0 hover:bg-muted/50 transition-colors"
                            >
                              <td className="px-4 py-2.5 text-xs text-subtle whitespace-nowrap tabular-nums">
                                {formatUsageTime(item.createdAt)}
                              </td>
                              <td className="px-4 py-2.5">
                                <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-bold ${
                                  item.category === "chat"
                                    ? "bg-success-subtle text-success"
                                    : "bg-accent/10 text-accent"
                                }`}>
                                  {item.category === "chat" ? "对话" : "生成"}
                                </span>
                              </td>
                              <td className="px-4 py-2.5 text-xs font-semibold text-body max-w-[200px] truncate">
                                {item.provider} · {item.model}
                              </td>
                              <td className="px-4 py-2.5 text-xs tabular-nums text-subtle text-right">
                                {formatTokenCount(item.promptTokens)}
                              </td>
                              <td className="px-4 py-2.5 text-xs tabular-nums text-subtle text-right">
                                {formatTokenCount(item.completionTokens)}
                              </td>
                              <td className="px-4 py-2.5 text-xs font-bold tabular-nums text-strong text-right">
                                {formatTokenCount(item.totalTokens)}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                ) : (
                  <div className="rounded-2xl border border-dashed border-line px-4 py-6 text-center text-sm text-subtle">
                    暂无最近记录。
                  </div>
                )}
              </motion.div>
            </motion.div>
          )}

    </div>
  );
}

/* ── Sub-components ── */

function UsageStatCard({ label, value, icon: Icon, accentClass, large = false, loading = false }) {
  return (
    <div className={`rounded-2xl border border-line bg-surface p-4 flex flex-col gap-2 ${large ? "sm:col-span-2 lg:col-span-1" : ""}`}>
      <div className="flex items-center gap-2">
        <div className={`flex items-center justify-center w-7 h-7 rounded-lg ${accentClass}`}>
          <Icon size={14} strokeWidth={2.5} />
        </div>
        <span className="text-xs font-semibold text-subtle">{label}</span>
      </div>
      <p className={`text-2xl font-black tabular-nums text-strong transition-opacity ${loading ? "opacity-60" : ""}`}>
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
        backgroundColor: createChartGradient("--workspace-accent-color"),
        borderRadius: 10,
        borderSkipped: false,
        barThickness: chartRows.length <= 4 ? 34 : "flex",
        maxBarThickness: 34,
      },
      {
        label: "对话",
        data: chartRows.map((item) => item.chatTokens),
        backgroundColor: createChartGradient("--color-success-muted"),
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
        backgroundColor: () => themeColor("--inverse", 0.94),
        titleColor: () => themeColor("--on-inverse"),
        bodyColor: () => themeColor("--on-inverse", 0.85),
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
          color: () => themeColor("--faint"),
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
          color: () => themeColor("--line"),
          drawTicks: false,
        },
        ticks: {
          color: () => themeColor("--ghost"),
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
    <div className="overflow-hidden rounded-3xl border border-line bg-gradient-to-br from-surface via-muted/80 to-surface p-5 shadow-sm">
      <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h4 className="text-sm font-bold text-strong">Token 用量趋势</h4>
          <p className="mt-1 text-xs font-semibold text-subtle">
            按时间聚合真实 token 消耗，悬停查看明细。
          </p>
        </div>
        <div className="flex items-center gap-3 text-xs font-bold text-subtle">
          <span className="flex items-center gap-1.5">
            <span className="inline-block h-2.5 w-2.5 rounded-full bg-accent ring-[3px] ring-accent/15" />
            生成
          </span>
          <span className="flex items-center gap-1.5">
            <span className="inline-block h-2.5 w-2.5 rounded-full bg-success ring-[3px] ring-success/15" />
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

// Canvas cannot resolve var(), so chart colours read the theme variable ("99 102 241") when
// Chart.js draws; scriptable options make them follow the light/dark switch.
function themeColor(variable, alpha = 1) {
  const channels = getComputedStyle(document.documentElement).getPropertyValue(variable).trim();
  return `rgb(${channels} / ${alpha})`;
}

function createChartGradient(colorVariable) {
  return (context) => {
    const { chart } = context;
    const { ctx, chartArea } = chart;
    if (!chartArea || typeof CanvasGradient === "undefined") {
      return themeColor(colorVariable);
    }
    const gradient = ctx.createLinearGradient(0, chartArea.top, 0, chartArea.bottom);
    gradient.addColorStop(0, themeColor(colorVariable));
    gradient.addColorStop(1, themeColor(colorVariable, 0.45));
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
