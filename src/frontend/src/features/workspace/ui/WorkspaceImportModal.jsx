import { useMemo, useState } from "react";
import { X, Link2, Loader2, CheckCircle2, AlertCircle, FolderUp, Film } from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";

export function WorkspaceImportModal({
  mode = "series",
  targetSeriesId = null,
  targetSeriesTitle = "",
  onClose,
  onResolveSeries,
  onResolveVideo,
  onImportLocalSeries,
  onImportSeriesVideos,
  onImportLocalPlaygroundVideos,
}) {
  const [sourceType, setSourceType] = useState("local");
  const [url, setUrl] = useState("");
  const [seriesTitle, setSeriesTitle] = useState("");
  const [files, setFiles] = useState([]);
  const [status, setStatus] = useState("idle");
  const [errorMsg, setErrorMsg] = useState("");
  const [preview, setPreview] = useState(null);

  const isSeriesCreation = mode === "series";
  const isSeriesVideo = mode === "series-video";
  const isPlayground = mode === "playground";
  const title = isSeriesCreation
    ? "添加系列"
    : isSeriesVideo
      ? `添加视频到 ${targetSeriesTitle || "当前系列"}`
      : "添加 Playground 视频";
  const subtitle = isSeriesCreation ? "系列来源" : "视频来源";
  const placeholder = isSeriesCreation
    ? "https://space.bilibili.com/.../collectiondetail?sid=..."
    : "https://www.bilibili.com/video/BVxxx";
  const localButtonText = isSeriesCreation
    ? "导入本地系列"
    : isSeriesVideo
      ? "导入本地视频"
      : "导入 Playground 视频";
  const externalButtonText = isSeriesCreation
    ? "添加外链系列"
    : isSeriesVideo
      ? "添加外链视频"
      : "添加外链视频";
  const actionLabel = sourceType === "local" ? "导入" : "解析";
  const selectedFileSummary = useMemo(() => {
    if (!files.length) {
      return "未选择文件";
    }
    if (files.length === 1) {
      return files[0].name;
    }
    return `已选择 ${files.length} 个文件`;
  }, [files]);

  async function handleSubmit() {
    setStatus("loading");
    setErrorMsg("");
    setPreview(null);

    try {
      if (sourceType === "local") {
        if (!files.length) {
          setStatus("idle");
          return;
        }
        const result = isSeriesCreation
          ? await onImportLocalSeries(seriesTitle.trim(), files)
          : isSeriesVideo
            ? await onImportSeriesVideos(targetSeriesId, files)
            : await onImportLocalPlaygroundVideos(files);
        setPreview({
          title: isSeriesCreation ? result.title : (isSeriesVideo ? (targetSeriesTitle || "当前系列") : "Playground"),
          videoCount: Array.isArray(result) ? result.length : result.videos?.length ?? files.length,
        });
        setStatus("success");
        return;
      }

      const trimmed = url.trim();
      if (!trimmed) {
        setStatus("idle");
        return;
      }
      const result = isSeriesCreation
        ? await onResolveSeries(trimmed)
        : await onResolveVideo(trimmed, isSeriesVideo ? targetSeriesId : null);
      setPreview({
        title: isSeriesCreation ? result.title : (isSeriesVideo ? (targetSeriesTitle || "当前系列") : result.title),
        videoCount: Array.isArray(result) ? result.length : result.videos?.length ?? 1,
      });
      setStatus("success");
    } catch (error) {
      setStatus("error");
      setErrorMsg(error instanceof Error ? error.message : "导入失败，请检查输入内容");
    }
  }

  function handleKeyDown(event) {
    if (event.key === "Enter" && sourceType === "external") {
      handleSubmit();
    }
  }

  const localDisabled = isSeriesCreation ? !seriesTitle.trim() || !files.length : !files.length;
  const externalDisabled = !url.trim();
  const submitDisabled = status === "loading" || (sourceType === "local" ? localDisabled : externalDisabled);

  return (
    <AnimatePresence>
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4 backdrop-blur-sm"
        onClick={(event) => {
          if (event.target === event.currentTarget) {
            onClose();
          }
        }}
      >
        <motion.div
          initial={{ opacity: 0, scale: 0.95, y: 16 }}
          animate={{ opacity: 1, scale: 1, y: 0 }}
          exit={{ opacity: 0, scale: 0.95, y: 16 }}
          transition={{ type: "spring", stiffness: 380, damping: 28 }}
          className="workspace-panel w-full max-w-xl overflow-hidden rounded-[2rem] border shadow-2xl"
        >
          <div className="flex items-center justify-between border-b border-stone-200/80 p-6 dark:border-stone-800">
            <div className="flex items-center gap-3">
              <div className="flex h-9 w-9 items-center justify-center rounded-xl border border-indigo-200 bg-indigo-100 text-indigo-600 dark:border-indigo-500/30 dark:bg-indigo-500/15 dark:text-indigo-400">
                {sourceType === "local" ? <FolderUp size={18} /> : <Link2 size={18} />}
              </div>
              <div>
                <p className="mb-0.5 text-[10px] font-bold uppercase tracking-widest text-stone-500 dark:text-zinc-500">{subtitle}</p>
                <h2 className="text-base font-bold leading-tight text-stone-900 dark:text-stone-100">{title}</h2>
              </div>
            </div>
            <button
              type="button"
              onClick={onClose}
              className="flex h-8 w-8 items-center justify-center rounded-full text-stone-400 transition-colors hover:bg-stone-100 hover:text-stone-600 dark:hover:bg-neutral-800 dark:hover:text-stone-200"
            >
              <X size={18} />
            </button>
          </div>

          <div className="flex flex-col gap-5 p-6">
            <div className="grid grid-cols-2 gap-3">
              <button
                type="button"
                onClick={() => setSourceType("local")}
                className={`rounded-2xl border px-4 py-3 text-left transition ${
                  sourceType === "local"
                    ? "border-indigo-300 bg-indigo-50 text-indigo-700 dark:border-indigo-700 dark:bg-indigo-950/30 dark:text-indigo-300"
                    : "border-stone-200 bg-white text-stone-600 dark:border-stone-700 dark:bg-neutral-900 dark:text-zinc-300"
                }`}
              >
                <div className="flex items-center gap-2 text-sm font-bold">
                  <FolderUp size={16} />
                  {localButtonText}
                </div>
                <p className="mt-1 text-xs font-medium opacity-80">选择本地视频文件，复制进项目目录。</p>
              </button>
              <button
                type="button"
                onClick={() => setSourceType("external")}
                className={`rounded-2xl border px-4 py-3 text-left transition ${
                  sourceType === "external"
                    ? "border-indigo-300 bg-indigo-50 text-indigo-700 dark:border-indigo-700 dark:bg-indigo-950/30 dark:text-indigo-300"
                    : "border-stone-200 bg-white text-stone-600 dark:border-stone-700 dark:bg-neutral-900 dark:text-zinc-300"
                }`}
              >
                <div className="flex items-center gap-2 text-sm font-bold">
                  <Link2 size={16} />
                  {externalButtonText}
                </div>
                <p className="mt-1 text-xs font-medium opacity-80">通过 Bilibili 链接解析系列或单视频。</p>
              </button>
            </div>

            {sourceType === "local" ? (
              <div className="flex flex-col gap-4">
                {isSeriesCreation ? (
                  <div>
                    <label className="mb-2 block text-xs font-bold tracking-wide text-stone-600 dark:text-zinc-400">
                      系列名称
                    </label>
                    <input
                      type="text"
                      value={seriesTitle}
                      onChange={(event) => setSeriesTitle(event.target.value)}
                      placeholder="例如：Agent Frameworks"
                      disabled={status === "loading"}
                      className="w-full rounded-2xl border border-stone-200 bg-white px-4 py-2.5 text-sm font-medium text-stone-900 transition-all placeholder:text-stone-400 focus:border-indigo-400 focus:outline-none focus:ring-2 focus:ring-indigo-400/50 disabled:opacity-60 dark:border-stone-700 dark:bg-neutral-900 dark:text-stone-100 dark:placeholder:text-zinc-500 dark:focus:border-indigo-500"
                      autoFocus
                    />
                  </div>
                ) : null}

                <div>
                  <label className="mb-2 block text-xs font-bold tracking-wide text-stone-600 dark:text-zinc-400">
                    选择视频文件
                  </label>
                  <label className="flex cursor-pointer flex-col gap-2 rounded-2xl border border-dashed border-stone-300 bg-stone-50 px-4 py-4 transition hover:border-indigo-300 hover:bg-indigo-50/50 dark:border-stone-700 dark:bg-neutral-900 dark:hover:border-indigo-700 dark:hover:bg-indigo-950/20">
                    <div className="flex items-center gap-2 text-sm font-semibold text-stone-700 dark:text-stone-200">
                      <Film size={16} />
                      {selectedFileSummary}
                    </div>
                    <p className="text-xs text-stone-500 dark:text-zinc-400">
                      支持多选，导入时会复制到项目的 videos 目录。
                    </p>
                    <input
                      type="file"
                      accept="video/*,.mp4,.mov,.mkv,.avi,.webm,.m4v"
                      multiple
                      disabled={status === "loading"}
                      onChange={(event) => setFiles(Array.from(event.target.files ?? []))}
                      className="hidden"
                    />
                  </label>
                </div>
              </div>
            ) : (
              <div>
                <label className="mb-2 block text-xs font-bold tracking-wide text-stone-600 dark:text-zinc-400">
                  {isSeriesCreation ? "合集 / 多P视频 URL" : "Bilibili 视频 URL"}
                </label>
                <div className="flex gap-2">
                  <input
                    type="url"
                    value={url}
                    onChange={(event) => setUrl(event.target.value)}
                    onKeyDown={handleKeyDown}
                    placeholder={placeholder}
                    disabled={status === "loading"}
                    className="flex-1 rounded-2xl border border-stone-200 bg-white px-4 py-2.5 text-sm font-medium text-stone-900 transition-all placeholder:text-stone-400 focus:border-indigo-400 focus:outline-none focus:ring-2 focus:ring-indigo-400/50 disabled:opacity-60 dark:border-stone-700 dark:bg-neutral-900 dark:text-stone-100 dark:placeholder:text-zinc-500 dark:focus:border-indigo-500"
                    autoFocus
                  />
                </div>
                <p className="mt-2 text-[11px] text-stone-400 dark:text-zinc-500">
                  {isSeriesCreation ? "支持：合集 (collectiondetail) · 系列 (seriesdetail) · 多P视频" : "支持：单个 BV 号视频"}
                </p>
              </div>
            )}

            {status === "success" && preview ? (
              <motion.div
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                className="flex items-center gap-4 rounded-2xl border border-emerald-200 bg-emerald-50 p-4 dark:border-emerald-700/40 dark:bg-emerald-950/25"
              >
                <CheckCircle2 size={20} className="shrink-0 text-emerald-500" />
                <div className="min-w-0">
                  <p className="truncate text-sm font-bold text-emerald-900 dark:text-emerald-200">{preview.title}</p>
                  <p className="mt-0.5 text-xs text-emerald-700/70 dark:text-emerald-400/70">
                    共 {preview.videoCount} 个视频 · 已导入
                  </p>
                </div>
              </motion.div>
            ) : null}

            {status === "error" ? (
              <motion.div
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                className="flex items-start gap-3 rounded-2xl border border-red-200 bg-red-50 p-4 dark:border-red-700/40 dark:bg-red-950/25"
              >
                <AlertCircle size={18} className="mt-0.5 shrink-0 text-red-500" />
                <p className="text-sm font-medium text-red-700 dark:text-red-300">{errorMsg}</p>
              </motion.div>
            ) : null}
          </div>

          <div className="flex justify-end gap-3 px-6 pb-6">
            <button
              type="button"
              onClick={onClose}
              className={status === "success"
                ? "rounded-2xl bg-stone-900 px-5 py-2.5 text-sm font-bold text-white shadow-sm transition-opacity hover:opacity-90 dark:bg-white dark:text-stone-900"
                : "rounded-2xl bg-stone-100 px-5 py-2.5 text-sm font-semibold text-stone-600 transition-colors hover:bg-stone-200 dark:bg-neutral-800 dark:text-zinc-300 dark:hover:bg-neutral-700"}
            >
              {status === "success" ? "完成" : "取消"}
            </button>
            <button
              type="button"
              onClick={handleSubmit}
              disabled={submitDisabled}
              className="inline-flex items-center gap-2 rounded-2xl bg-indigo-500 px-5 py-2.5 text-sm font-bold text-white shadow-sm transition-colors hover:bg-indigo-600 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {status === "loading" ? <Loader2 size={16} className="animate-spin" /> : null}
              {actionLabel}
            </button>
          </div>
        </motion.div>
      </motion.div>
    </AnimatePresence>
  );
}
