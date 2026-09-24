import { useEffect, useState } from "react";
import { Check, FolderOpen, HardDriveDownload, LoaderCircle, RefreshCw } from "lucide-react";

const TERMINAL_STATUSES = new Set(["completed", "failed", "cancelled", "interrupted"]);

function formatBytes(bytes) {
  if (!Number.isFinite(bytes)) return "—";
  if (bytes < 1024) return `${bytes} B`;
  const unit = bytes < 1024 ** 2 ? "KB" : bytes < 1024 ** 3 ? "MB" : "GB";
  const divisor = unit === "KB" ? 1024 : unit === "MB" ? 1024 ** 2 : 1024 ** 3;
  return `${(bytes / divisor).toFixed(1)} ${unit}`;
}

function messageOf(error) {
  return error instanceof Error ? error.message : "迁移操作失败";
}

const MODE_LABELS = { copy: "复制", hardlink: "硬链接", external_reference: "外部路径引用" };
const DATA_LABELS = { models: "本地模型", bilibili: "Bilibili 浏览器状态", youtube: "YouTube 浏览器状态", douyin: "抖音浏览器状态", chaoxing: "超星状态" };
const STATUS_LABELS = { ready: "准备就绪", running: "迁移中", completed: "已完成", failed: "失败", cancelled: "已暂停", interrupted: "已中断" };

export function WorkspaceLegacyMigrationPanel({ onSelectSource, onInspect, onCreateRun, onStartRun, onLoadRun, onLoadLatestRun, onCancelRun }) {
  const [path, setPath] = useState("");
  const [preview, setPreview] = useState(null);
  const [run, setRun] = useState(null);
  const [includeData, setIncludeData] = useState([]);
  const [convertHardlinks, setConvertHardlinks] = useState(false);
  const [confirmedCleanup, setConfirmedCleanup] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    void onLoadLatestRun().then((latest) => {
      if (active && latest) {
        setRun(latest);
        setPath(latest.source_root);
        setPreview(latest.manifest);
        setIncludeData(latest.include_data);
      }
    }).catch((caught) => { if (active) setError(messageOf(caught)); });
    return () => { active = false; };
  }, [onLoadLatestRun]);

  useEffect(() => {
    if (!run?.id || run.status !== "running") return undefined;
    let active = true;
    const poll = async () => {
      try {
        const next = await onLoadRun(run.id);
        if (active) setRun(next);
      } catch (caught) {
        if (active) setError(messageOf(caught));
      }
    };
    const timer = window.setInterval(() => void poll(), 800);
    return () => { active = false; window.clearInterval(timer); };
  }, [run?.id, run?.status, onLoadRun]);

  async function inspect(selectedPath, convert = convertHardlinks) {
    setBusy(true);
    setError("");
    try {
      const result = await onInspect(selectedPath, convert);
      setPath(selectedPath);
      setPreview(result);
      setRun(null);
      setConfirmedCleanup(false);
      setIncludeData(result.data?.filter((item) => item.category === "copyable").map((item) => item.name) ?? []);
    } catch (caught) {
      setError(messageOf(caught));
    } finally {
      setBusy(false);
    }
  }

  async function selectSource() {
    setBusy(true);
    setError("");
    try {
      const selection = await onSelectSource();
      if (selection.path) await inspect(selection.path);
    } catch (caught) {
      setError(messageOf(caught));
    } finally {
      setBusy(false);
    }
  }

  async function start() {
    setBusy(true);
    setError("");
    try {
      const created = run?.id ? run : await onCreateRun(path, includeData, convertHardlinks);
      const started = await onStartRun(created.id);
      setRun(started);
    } catch (caught) {
      setError(messageOf(caught));
    } finally {
      setBusy(false);
    }
  }

  async function cancel() {
    if (!run?.id) return;
    try {
      setRun(await onCancelRun(run.id));
    } catch (caught) {
      setError(messageOf(caught));
    }
  }

  const blockedByHardlinks = preview?.warnings?.some((warning) => warning.includes("跨卷"));
  const showHardlinkConversion = blockedByHardlinks || preview?.series?.some((series) => series.mode === "hardlink" && series.effective_mode !== "hardlink");
  const copyable = preview?.data?.filter((item) => item.category === "copyable") ?? [];

  return (
    <section data-testid="legacy-migration-panel" className="mt-7 rounded-2xl border border-stone-200 bg-white p-5 dark:border-stone-700 dark:bg-neutral-900">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h4 className="text-lg font-bold text-stone-900 dark:text-stone-100">旧版数据迁移</h4>
          <p className="mt-1 text-sm text-stone-600 dark:text-stone-400">选择旧版 VSummary 目录，检查 data、workspace 和 videos 后再开始迁移。</p>
        </div>
        <button type="button" onClick={() => void selectSource()} disabled={busy || run?.status === "running"} className="inline-flex items-center gap-2 rounded-lg border border-stone-300 px-4 py-2 text-sm font-semibold text-stone-700 hover:border-accent/50 disabled:opacity-50 dark:border-stone-600 dark:text-stone-200">
          <FolderOpen size={17} /> 选择旧版目录
        </button>
      </div>
      {path && <p className="mt-4 break-all rounded-lg bg-stone-50 px-3 py-2 text-xs text-stone-600 dark:bg-stone-800 dark:text-stone-300">来源：{path}</p>}
      {preview?.candidates?.length > 0 && (
        <div className="mt-4 space-y-2"><p className="text-sm font-semibold">找到多个旧版目录，请选择：</p>{preview.candidates.map((candidate) => <button key={candidate} type="button" onClick={() => void inspect(candidate)} className="block w-full break-all rounded-lg border border-stone-200 px-3 py-2 text-left text-sm hover:border-accent dark:border-stone-700">{candidate}</button>)}</div>
      )}
      {preview?.series && (
        <div className="mt-5 space-y-4">
          <div className="grid gap-3 text-sm sm:grid-cols-3">
            <div className="rounded-xl bg-stone-50 p-3 dark:bg-stone-800"><span className="text-stone-500">系列</span><strong className="ml-2">{preview.series.length}</strong></div>
            <div className="rounded-xl bg-stone-50 p-3 dark:bg-stone-800"><span className="text-stone-500">视频/引用</span><strong className="ml-2">{preview.total_videos}</strong></div>
            <div className="rounded-xl bg-stone-50 p-3 dark:bg-stone-800"><span className="text-stone-500">预计复制</span><strong className="ml-2">{formatBytes(preview.copy_bytes)}</strong></div>
          </div>
          <div className="rounded-xl border border-stone-200 dark:border-stone-700">
            {preview.series.map((series) => <div key={series.name} className="flex flex-wrap items-center justify-between gap-2 border-b border-stone-100 px-3 py-2 text-sm last:border-0 dark:border-stone-800"><span className="font-medium">{series.name}</span><span className="text-stone-500">{MODE_LABELS[series.mode]} · {series.media.length + series.external.length} 个视频{series.effective_mode !== series.mode ? " · 将转换为复制" : ""}</span></div>)}
          </div>
          {copyable.length > 0 && <div><p className="text-sm font-semibold">同时迁入 data 中的文件</p><div className="mt-2 grid gap-2 sm:grid-cols-2">{copyable.map((item) => <label key={item.name} className="flex items-center gap-2 text-sm"><input type="checkbox" checked={includeData.includes(item.name)} onChange={(event) => setIncludeData((current) => event.target.checked ? [...current, item.name] : current.filter((name) => name !== item.name))} /><span>{DATA_LABELS[item.name] ?? item.name} · {formatBytes(item.bytes)}</span></label>)}</div></div>}
          {preview.data?.some((item) => item.category !== "copyable") && <p className="text-xs text-stone-500">Agent 会话和用量记录导入 SQL；临时缓存及未识别目录会列在迁移报告中，不会直接复制。</p>}
          {preview.warnings?.length > 0 && <div className="rounded-xl border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900 dark:border-amber-800 dark:bg-amber-950/30 dark:text-amber-200">{preview.warnings.map((warning) => <p key={warning}>{warning}</p>)}</div>}
          {showHardlinkConversion && <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={convertHardlinks} onChange={(event) => { setConvertHardlinks(event.target.checked); void inspect(path, event.target.checked); }} />明确将跨卷硬链接转换为复制</label>}
          <p className="text-xs text-stone-500">目标盘剩余：{formatBytes(preview.target_free_bytes)}。复制模式需容纳目标 Blob；迁移会在每个视频核验后清理对应的旧 videos 文件。</p>
          <label className="flex items-start gap-2 rounded-xl border border-stone-200 p-3 text-sm dark:border-stone-700"><input type="checkbox" checked={confirmedCleanup} onChange={(event) => setConfirmedCleanup(event.target.checked)} /><span>我了解：已核验的旧 videos 文件会逐个直接删除，不经过回收站；旧版目录之后不能直接完整回退。外部路径引用的原文件不会删除。</span></label>
          <button type="button" onClick={() => void start()} disabled={!confirmedCleanup || busy || blockedByHardlinks || run?.status === "running" || run?.status === "completed"} className="inline-flex items-center gap-2 rounded-lg bg-accent px-4 py-2 text-sm font-bold text-white disabled:opacity-50"><HardDriveDownload size={17} />{run?.status === "running" ? "正在迁移" : run?.status === "completed" ? "迁移完成" : run && TERMINAL_STATUSES.has(run.status) ? "继续迁移" : "开始迁移"}</button>
        </div>
      )}
      {run && <div data-testid="legacy-migration-status" className="mt-5 rounded-xl border border-stone-200 p-4 dark:border-stone-700"><div className="flex items-center gap-2 font-semibold">{run.status === "running" ? <LoaderCircle size={16} className="animate-spin" /> : run.status === "completed" ? <Check size={16} className="text-success" /> : <RefreshCw size={16} />}迁移状态：{STATUS_LABELS[run.status] ?? run.status}</div><p className="mt-2 text-sm text-stone-600 dark:text-stone-300">已核验 {run.verified_videos}/{run.total_videos}，已清理旧视频 {run.removed_videos}</p>{run.error && <p className="mt-2 text-sm text-red-600">{run.error}</p>}{run.status === "running" && <button type="button" onClick={() => void cancel()} className="mt-3 text-sm text-stone-600 underline">在当前视频完成后暂停</button>}{run.status === "completed" && <button type="button" onClick={() => window.location.reload()} className="mt-3 text-sm font-semibold text-accent underline">刷新视频库</button>}</div>}
      {error && <p role="alert" className="mt-4 text-sm text-red-600">{error}</p>}
    </section>
  );
}
