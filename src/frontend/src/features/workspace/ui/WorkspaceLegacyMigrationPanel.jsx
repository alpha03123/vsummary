import { useEffect, useState } from "react";
import { Check, FolderOpen, HardDriveDownload, LoaderCircle, RefreshCw } from "lucide-react";
import { WorkspaceMultiSelect, WorkspaceSettingRow, WorkspaceToggleSwitch } from "./shared/WorkspaceSettingsControls";

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
    <section data-testid="legacy-migration-panel" className="space-y-4 pt-6">
      <div className="mb-2">
        <h4 className="text-2xl font-bold text-stone-900 dark:text-stone-100">旧版数据迁移</h4>
        <p className="mt-2 text-[13px] text-stone-600 dark:text-stone-400">选择旧版 VSummary 目录，检查 data、workspace 和 videos 后再开始迁移。</p>
      </div>
      <WorkspaceSettingRow title="旧版目录" description={path ? `来源：${path}` : ""}>
        <button type="button" onClick={() => void selectSource()} disabled={busy || run?.status === "running"} className="inline-flex items-center gap-2 rounded-lg border border-stone-300 bg-white px-4 py-2.5 text-sm font-bold text-stone-700 transition-colors hover:border-accent/50 hover:text-accent disabled:cursor-not-allowed disabled:opacity-50 dark:border-stone-700 dark:bg-neutral-900 dark:text-stone-200">
          <FolderOpen size={16} /> 选择旧版目录
        </button>
      </WorkspaceSettingRow>
      {preview?.candidates?.length > 0 && (
        <WorkspaceSettingRow title="找到多个旧版目录，请选择：" description="">
          <div className="w-full space-y-2">{preview.candidates.map((candidate) => <button key={candidate} type="button" onClick={() => void inspect(candidate)} className="block w-full break-all rounded-xl border border-stone-200 bg-white px-3.5 py-2.5 text-left text-sm text-stone-700 transition-colors hover:border-accent/50 dark:border-stone-700 dark:bg-neutral-900 dark:text-stone-200">{candidate}</button>)}</div>
        </WorkspaceSettingRow>
      )}
      {preview?.series && (
        <>
          <WorkspaceSettingRow title={`系列 ${preview.series.length}`} description={`视频/引用 ${preview.total_videos} · 预计复制 ${formatBytes(preview.copy_bytes)}`} contentClassName="2xl:max-w-[390px]">
            <div className="w-full divide-y divide-stone-200/80 rounded-xl border border-stone-200 bg-white px-3.5 dark:divide-stone-700 dark:border-stone-700 dark:bg-neutral-900">
              {preview.series.map((series) => <div key={series.name} className="flex flex-wrap items-center justify-between gap-x-3 gap-y-1 py-2.5 text-sm"><span className="font-medium text-stone-800 dark:text-stone-200">{series.name}</span><span className="text-xs text-stone-500 dark:text-stone-400">{MODE_LABELS[series.mode]} · {series.media.length + series.external.length} 个视频{series.effective_mode !== series.mode ? " · 将转换为复制" : ""}</span></div>)}
            </div>
          </WorkspaceSettingRow>
          {copyable.length > 0 && <WorkspaceSettingRow title="同时迁入 data 中的文件" description={preview.data?.some((item) => item.category !== "copyable") ? "Agent 会话和用量记录导入 SQL；临时缓存及未识别目录会列在迁移报告中，不会直接复制。" : ""} contentClassName="2xl:max-w-[390px]"><WorkspaceMultiSelect values={includeData} options={copyable.map((item) => ({ id: item.name, label: `${DATA_LABELS[item.name] ?? item.name} · ${formatBytes(item.bytes)}` }))} onChange={setIncludeData} /></WorkspaceSettingRow>}
          {preview.warnings?.length > 0 && <WorkspaceSettingRow title="迁移提醒" description=""><div className="w-full rounded-xl border border-amber-200 bg-amber-50 px-3.5 py-2.5 text-sm text-amber-900 dark:border-amber-800 dark:bg-amber-950/30 dark:text-amber-200">{preview.warnings.map((warning) => <p key={warning}>{warning}</p>)}</div></WorkspaceSettingRow>}
          {showHardlinkConversion && <WorkspaceSettingRow title="明确将跨卷硬链接转换为复制" description=""><WorkspaceToggleSwitch checked={convertHardlinks} onChange={() => { setConvertHardlinks(!convertHardlinks); void inspect(path, !convertHardlinks); }} ariaLabel="明确将跨卷硬链接转换为复制" /></WorkspaceSettingRow>}
          <WorkspaceSettingRow title="迁移清理" description="我了解：已核验的旧 videos 文件会逐个直接删除，不经过回收站；旧版目录之后不能直接完整回退。外部路径引用的原文件不会删除。"><WorkspaceToggleSwitch checked={confirmedCleanup} onChange={() => setConfirmedCleanup((value) => !value)} ariaLabel="我了解：逐视频清理旧 videos 文件" /></WorkspaceSettingRow>
          <WorkspaceSettingRow title="开始迁移" description={`目标盘剩余：${formatBytes(preview.target_free_bytes)}。复制模式需容纳目标 Blob；迁移会在每个视频核验后清理对应的旧 videos 文件。`}>
            <button type="button" onClick={() => void start()} disabled={!confirmedCleanup || busy || blockedByHardlinks || run?.status === "running" || run?.status === "completed"} className="inline-flex items-center gap-2 rounded-lg bg-accent px-4 py-2.5 text-sm font-bold text-white transition-colors hover:bg-accent/90 disabled:cursor-not-allowed disabled:opacity-50"><HardDriveDownload size={16} />{run?.status === "running" ? "正在迁移" : run?.status === "completed" ? "迁移完成" : run && TERMINAL_STATUSES.has(run.status) ? "继续迁移" : "开始迁移"}</button>
          </WorkspaceSettingRow>
        </>
      )}
      {run && <div data-testid="legacy-migration-status"><WorkspaceSettingRow title={`迁移状态：${STATUS_LABELS[run.status] ?? run.status}`} description={`已核验 ${run.verified_videos}/${run.total_videos}，已清理旧视频 ${run.removed_videos}`}><div className="flex flex-wrap items-center justify-end gap-3 text-sm font-semibold text-stone-700 dark:text-stone-200">{run.status === "running" ? <LoaderCircle size={16} className="animate-spin text-accent" /> : run.status === "completed" ? <Check size={16} className="text-success" /> : <RefreshCw size={16} />}{run.error && <span className="text-red-600">{run.error}</span>}{run.status === "running" && <button type="button" onClick={() => void cancel()} className="text-stone-600 underline dark:text-stone-300">在当前视频完成后暂停</button>}{run.status === "completed" && <button type="button" onClick={() => window.location.reload()} className="text-accent underline">刷新视频库</button>}</div></WorkspaceSettingRow></div>}
      {error && <p role="alert" className="text-sm text-red-600">{error}</p>}
    </section>
  );
}
