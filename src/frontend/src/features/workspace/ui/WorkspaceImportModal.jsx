import { useEffect, useMemo, useRef, useState } from "react";
import { X, Loader2, CheckCircle2, AlertCircle, FolderUp, Film, Search } from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";

export function WorkspaceImportModal({
  mode = "series",
  targetSeriesId = null,
  targetSeriesTitle = "",
  onClose,
  onResolveSeries,
  onResolveVideo,
  onInitBilibiliCookie,
  onLoadChaoxingStatus,
  onInitChaoxing,
  onCancelChaoxingInit,
  onCancelChaoxingImport,
  onLoadChaoxingCourses,
  onImportChaoxingCourse,
  onImportLocalSeries,
  onImportSeriesVideos,
  onImportLocalPlaygroundVideos,
}) {
  const [sourceType, setSourceType] = useState("local");
  const [externalProvider, setExternalProvider] = useState("bilibili");
  const [url, setUrl] = useState("");
  const [seriesTitle, setSeriesTitle] = useState("");
  const [files, setFiles] = useState([]);
  const [status, setStatus] = useState("idle");
  const [errorMsg, setErrorMsg] = useState("");
  const [preview, setPreview] = useState(null);
  const [chaoxingStatus, setChaoxingStatus] = useState(null);
  const [chaoxingCourses, setChaoxingCourses] = useState([]);
  const [chaoxingCourseSearch, setChaoxingCourseSearch] = useState("");
  const [selectedChaoxingCourseKey, setSelectedChaoxingCourseKey] = useState("");
  const [chaoxingLoading, setChaoxingLoading] = useState(false);
  const [bilibiliCookieLoading, setBilibiliCookieLoading] = useState(false);
  const [bilibiliCookieConfigured, setBilibiliCookieConfigured] = useState(false);
  const [chaoxingImportProgress, setChaoxingImportProgress] = useState(null);
  const loadChaoxingStatusRef = useRef(onLoadChaoxingStatus);
  const loadChaoxingCoursesRef = useRef(onLoadChaoxingCourses);
  const cancelChaoxingInitRef = useRef(onCancelChaoxingInit);
  const cancelChaoxingImportRef = useRef(onCancelChaoxingImport);
  const chaoxingImportTaskRef = useRef(null);
  const initAbortControllerRef = useRef(null);
  const initInFlightRef = useRef(false);
  const mountedRef = useRef(true);

  const isSeriesCreation = mode === "series";
  const isSeriesVideo = mode === "series-video";
  const title = isSeriesCreation
    ? "添加系列"
    : isSeriesVideo
      ? `添加视频到 ${targetSeriesTitle || "当前系列"}`
      : "添加 Playground 媒体";
  const subtitle = sourceType === "external" ? "外部来源" : (isSeriesCreation ? "本地导入" : "媒体导入");
  const actionLabel = "导入";
  const chaoxingEnabledForMode = isSeriesCreation;
  const normalizedChaoxingCourseSearch = chaoxingCourseSearch.trim().toLowerCase();
  const filteredChaoxingCourses = useMemo(() => {
    if (!normalizedChaoxingCourseSearch) {
      return chaoxingCourses;
    }
    return chaoxingCourses.filter((course) => {
      const haystacks = [course.title, course.teacher, course.openTime]
        .filter((value) => typeof value === "string")
        .map((value) => value.toLowerCase());
      return haystacks.some((value) => value.includes(normalizedChaoxingCourseSearch));
    });
  }, [chaoxingCourses, normalizedChaoxingCourseSearch]);
  const selectedFileSummary = useMemo(() => {
    if (!files.length) {
      return "未选择文件";
    }
    if (files.length === 1) {
      return files[0].name;
    }
    return `已选择 ${files.length} 个文件`;
  }, [files]);

  useEffect(() => {
    loadChaoxingStatusRef.current = onLoadChaoxingStatus;
    loadChaoxingCoursesRef.current = onLoadChaoxingCourses;
    cancelChaoxingInitRef.current = onCancelChaoxingInit;
    cancelChaoxingImportRef.current = onCancelChaoxingImport;
  }, [onLoadChaoxingStatus, onLoadChaoxingCourses, onCancelChaoxingInit, onCancelChaoxingImport]);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      requestChaoxingInitCancel();
      requestChaoxingImportCancel();
    };
  }, []);

  useEffect(() => {
    if (sourceType !== "external" || externalProvider !== "chaoxing") {
      requestChaoxingInitCancel();
    }
  }, [sourceType, externalProvider]);

  useEffect(() => {
    if (sourceType !== "external" || externalProvider !== "chaoxing" || !chaoxingEnabledForMode) {
      return;
    }
    const loadStatus = loadChaoxingStatusRef.current;
    const loadCourses = loadChaoxingCoursesRef.current;
    if (!loadStatus) {
      return;
    }
    let cancelled = false;
    setChaoxingLoading(true);
    loadStatus()
      .then(async (nextStatus) => {
        if (cancelled) {
          return;
        }
        setChaoxingStatus(nextStatus);
        if (nextStatus.initialized && loadCourses) {
          const courses = await loadCourses();
          if (!cancelled) {
            setChaoxingCourses(courses);
            setSelectedChaoxingCourseKey((current) => current || courses[0]?.courseKey || "");
          }
        }
      })
      .catch((error) => {
        if (!cancelled) {
          setErrorMsg(error instanceof Error ? error.message : "读取超星状态失败");
          setStatus("error");
        }
      })
      .finally(() => {
        if (!cancelled) {
          setChaoxingLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [sourceType, externalProvider, chaoxingEnabledForMode]);

  async function handleInitChaoxing() {
    if (!onInitChaoxing || !onLoadChaoxingCourses) {
      return;
    }
    const controller = new AbortController();
    initAbortControllerRef.current = controller;
    initInFlightRef.current = true;
    setStatus("loading");
    setErrorMsg("");
    setChaoxingLoading(true);
    try {
      const nextStatus = await onInitChaoxing({ signal: controller.signal });
      if (!mountedRef.current) {
        return;
      }
      setChaoxingStatus(nextStatus);
      const courses = nextStatus.initialized ? await onLoadChaoxingCourses() : [];
      if (!mountedRef.current) {
        return;
      }
      setChaoxingCourses(courses);
      setSelectedChaoxingCourseKey(courses[0]?.courseKey || "");
      setStatus("idle");
    } catch (error) {
      if (error instanceof DOMException && error.name === "AbortError") {
        return;
      }
      if (!mountedRef.current) {
        return;
      }
      setStatus("error");
      setErrorMsg(toChaoxingInitErrorMessage(error));
    } finally {
      if (initAbortControllerRef.current === controller) {
        initAbortControllerRef.current = null;
        initInFlightRef.current = false;
      }
      if (mountedRef.current) {
        setChaoxingLoading(false);
      }
    }
  }

  async function handleInitBilibiliCookie() {
    if (!onInitBilibiliCookie) {
      return;
    }
    setStatus("loading");
    setErrorMsg("");
    setBilibiliCookieLoading(true);
    try {
      const result = await onInitBilibiliCookie();
      if (!mountedRef.current) {
        return;
      }
      setBilibiliCookieConfigured(result.configured === true);
      setStatus("idle");
    } catch (error) {
      if (!mountedRef.current) {
        return;
      }
      setStatus("error");
      setErrorMsg(error instanceof Error ? error.message : "获取 Bilibili Cookie 失败");
    } finally {
      if (mountedRef.current) {
        setBilibiliCookieLoading(false);
      }
    }
  }

  function requestChaoxingInitCancel() {
    initAbortControllerRef.current?.abort();
    if (initInFlightRef.current) {
      cancelChaoxingInitRef.current?.();
    }
  }

  function requestChaoxingImportCancel() {
    const taskId = chaoxingImportTaskRef.current?.taskId;
    if (taskId) {
      cancelChaoxingImportRef.current?.(taskId);
      chaoxingImportTaskRef.current = null;
    }
  }

  function handleClose() {
    requestChaoxingInitCancel();
    requestChaoxingImportCancel();
    onClose();
  }

  async function handleSubmit() {
    setStatus("loading");
    setErrorMsg("");
    setPreview(null);
    setChaoxingImportProgress(null);

    try {
      let result;
      if (sourceType === "external") {
        if (externalProvider === "chaoxing") {
          if (!selectedChaoxingCourseKey || !onImportChaoxingCourse) {
            setStatus("idle");
            return;
          }
          result = await onImportChaoxingCourse(selectedChaoxingCourseKey, setChaoxingImportProgress, {
            onTaskStarted: (task) => {
              chaoxingImportTaskRef.current = task;
            },
          });
          chaoxingImportTaskRef.current = null;
        } else {
          const trimmed = url.trim();
          if (!trimmed) {
            setStatus("idle");
            return;
          }
          result = isSeriesCreation
            ? await onResolveSeries(trimmed)
            : await onResolveVideo(trimmed, isSeriesVideo ? targetSeriesId : null);
        }
      } else {
        if (!files.length) {
          setStatus("idle");
          return;
        }
        result = isSeriesCreation
          ? await onImportLocalSeries(seriesTitle.trim(), files)
          : isSeriesVideo
            ? await onImportSeriesVideos(targetSeriesId, files)
            : await onImportLocalPlaygroundVideos(files);
      }
      setPreview({
        title: isSeriesCreation ? result.title : (isSeriesVideo ? (targetSeriesTitle || "当前系列") : result.title ?? "Playground"),
        videoCount: Array.isArray(result) ? result.length : result.videos?.length ?? (sourceType === "external" ? 1 : files.length),
      });
      setStatus("success");
    } catch (error) {
      chaoxingImportTaskRef.current = null;
      setStatus("error");
      setErrorMsg(error instanceof Error ? error.message : "导入失败，请检查输入内容");
    }
  }

  const submitDisabled = status === "loading" || (
    sourceType === "external"
      ? (externalProvider === "chaoxing" ? !selectedChaoxingCourseKey || !chaoxingStatus?.initialized : !url.trim())
      : (isSeriesCreation ? !seriesTitle.trim() || !files.length : !files.length)
  );

  return (
    <AnimatePresence>
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4 backdrop-blur-sm"
        onClick={(event) => {
          if (event.target === event.currentTarget) {
            handleClose();
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
              <div className="flex h-9 w-9 items-center justify-center rounded-xl border border-accent/20 bg-accent/10 text-accent">
                <FolderUp size={18} />
              </div>
              <div>
                <p className="mb-0.5 text-[10px] font-bold uppercase tracking-widest text-stone-500 dark:text-zinc-500">{subtitle}</p>
                <h2 className="text-base font-bold leading-tight text-stone-900 dark:text-stone-100">{title}</h2>
              </div>
            </div>
            <button
              type="button"
              onClick={handleClose}
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
                className={`cursor-pointer rounded-2xl border px-4 py-3 text-left text-sm font-bold transition-colors ${
                  sourceType === "local"
                    ? "border-accent bg-accent/10 text-accent"
                    : "border-stone-200 bg-white text-stone-600 dark:border-stone-700 dark:bg-neutral-900 dark:text-zinc-300"
                }`}
              >
                本地媒体
                <p className="mt-1 text-xs font-medium opacity-70">复制文件到 videos 目录。</p>
              </button>
              <button
                type="button"
                onClick={() => setSourceType("external")}
                className={`cursor-pointer rounded-2xl border px-4 py-3 text-left text-sm font-bold transition-colors ${
                  sourceType === "external"
                    ? "border-accent bg-accent/10 text-accent"
                    : "border-stone-200 bg-white text-stone-600 dark:border-stone-700 dark:bg-neutral-900 dark:text-zinc-300"
                }`}
              >
                外部来源
                <p className="mt-1 text-xs font-medium opacity-70">外部API下载</p>
              </button>
            </div>

            {sourceType === "external" ? (
              <div className="space-y-4">
                <div>
                  <p className="mb-2 text-xs font-bold tracking-wide text-stone-600 dark:text-zinc-400">渠道</p>
                  <div className="inline-flex rounded-2xl border border-stone-200 bg-stone-100 p-1 dark:border-stone-700 dark:bg-neutral-900">
                  <button
                    type="button"
                    onClick={() => setExternalProvider("bilibili")}
                    className={`cursor-pointer rounded-xl px-3.5 py-2 text-xs font-bold transition-colors ${
                      externalProvider === "bilibili"
                        ? "bg-white text-accent shadow-sm dark:bg-neutral-800"
                        : "text-stone-500 hover:text-stone-800 dark:text-zinc-400 dark:hover:text-zinc-100"
                    }`}
                  >
                    Bilibili
                  </button>
                  <button
                    type="button"
                    onClick={() => setExternalProvider("chaoxing")}
                    className={`cursor-pointer rounded-xl px-3.5 py-2 text-xs font-bold transition-colors ${
                      externalProvider === "chaoxing"
                        ? "bg-white text-accent shadow-sm dark:bg-neutral-800"
                        : "text-stone-500 hover:text-stone-800 dark:text-zinc-400 dark:hover:text-zinc-100"
                    }`}
                  >
                    ChaoXing
                  </button>
                  </div>
                </div>
                {externalProvider === "bilibili" ? (
                <>
                <label className="mb-2 block text-xs font-bold tracking-wide text-stone-600 dark:text-zinc-400">
                  {isSeriesCreation ? "Bilibili 系列 / 多 P URL" : "Bilibili 视频 URL"}
                </label>
                <input
                  type="url"
                  value={url}
                  onChange={(event) => setUrl(event.target.value)}
                  placeholder={isSeriesCreation ? "https://www.bilibili.com/video/BV... 或合集链接" : "https://www.bilibili.com/video/BV..."}
                  disabled={status === "loading"}
                  className="w-full rounded-2xl border border-stone-200 bg-white px-4 py-2.5 text-sm font-medium text-stone-900 transition-all placeholder:text-stone-400 focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent/10 disabled:opacity-60 dark:border-stone-700 dark:bg-neutral-900 dark:text-stone-100 dark:placeholder:text-zinc-500"
                  autoFocus
                />
                <p className="mt-2 text-[11px] text-stone-400 dark:text-zinc-500">
                  遇到风控时请先获取 Cookie，再重新解析。
                </p>
                <div className="mt-3 flex flex-wrap items-center gap-3">
                  <button
                    type="button"
                    onClick={handleInitBilibiliCookie}
                    disabled={bilibiliCookieLoading || status === "loading"}
                    className="inline-flex cursor-pointer items-center gap-2 rounded-2xl border border-accent/30 bg-accent/10 px-4 py-2 text-xs font-bold text-accent transition-colors hover:bg-accent/15 disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    {bilibiliCookieLoading ? <Loader2 size={14} className="animate-spin" /> : null}
                    {bilibiliCookieLoading ? "等待登录..." : "获取 Bilibili Cookie"}
                  </button>
                  {bilibiliCookieConfigured ? (
                    <span className="inline-flex items-center gap-1 text-xs font-semibold text-emerald-600 dark:text-emerald-400">
                      <CheckCircle2 size={14} />
                      Cookie 已写入
                    </span>
                  ) : null}
                </div>
                </>
                ) : (
                  <div className="rounded-2xl border border-stone-200 bg-stone-50 p-4 dark:border-stone-700 dark:bg-neutral-900">
                    {!chaoxingEnabledForMode ? (
                      <p className="text-sm font-semibold text-stone-700 dark:text-stone-200">
                        超星按课程导入为系列，请从“添加系列”入口使用。
                      </p>
                    ) : status === "error" && errorMsg ? (
                      <div className="flex items-center gap-2 text-sm font-semibold text-danger">
                        <AlertCircle size={16} />
                        {errorMsg}
                      </div>
                    ) : chaoxingLoading ? (
                      <div className="flex items-center gap-2 text-sm font-semibold text-stone-600 dark:text-zinc-300">
                        <Loader2 size={16} className="animate-spin" />
                        等待登录...
                      </div>
                    ) : !chaoxingStatus?.initialized ? (
                      <div className="flex flex-col gap-3">
                        <div>
                          <p className="text-sm font-bold text-stone-900 dark:text-stone-100">需要初始化超星登录</p>
                          <p className="mt-1 text-xs text-stone-500 dark:text-zinc-400">
                            点击后会打开浏览器，请在浏览器中完成学习通登录。
                          </p>
                        </div>
                        <button
                          type="button"
                          onClick={handleInitChaoxing}
                          disabled={status === "loading"}
                          className="inline-flex w-fit cursor-pointer items-center gap-2 rounded-2xl bg-accent px-4 py-2 text-xs font-bold text-white hover:bg-accent/90 disabled:cursor-not-allowed disabled:opacity-50"
                        >
                          {status === "loading" ? <Loader2 size={14} className="animate-spin" /> : null}
                          开始登陆
                        </button>
                      </div>
                    ) : (
                      <div>
                        <div className="mb-3 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                          <p className="text-xs font-bold tracking-wide text-stone-600 dark:text-zinc-400">选择要导入的课程</p>
                          <button
                            type="button"
                            onClick={handleInitChaoxing}
                            disabled={status === "loading"}
                            className="inline-flex w-fit cursor-pointer items-center gap-2 rounded-2xl bg-red-600 px-4 py-2 text-xs font-bold text-white transition-colors hover:bg-red-700 disabled:cursor-not-allowed disabled:opacity-50"
                          >
                            {status === "loading" ? <Loader2 size={14} className="animate-spin" /> : null}
                            重新登录初始化
                          </button>
                        </div>
                        <div className="relative mb-3">
                          <Search size={14} className="pointer-events-none absolute left-4 top-1/2 -translate-y-1/2 text-stone-400 dark:text-zinc-500" />
                          <input
                            type="text"
                            value={chaoxingCourseSearch}
                            onChange={(event) => setChaoxingCourseSearch(event.target.value)}
                            placeholder="搜索课程或教师"
                            className="w-full rounded-2xl border border-stone-200 bg-white px-10 py-2.5 pr-10 text-sm font-medium text-stone-800 outline-none transition-colors placeholder:text-stone-400 focus:border-accent/50 focus:ring-2 focus:ring-accent/10 dark:border-stone-700 dark:bg-neutral-950 dark:text-stone-100 dark:placeholder:text-zinc-500"
                          />
                          {chaoxingCourseSearch ? (
                            <button
                              type="button"
                              onClick={() => setChaoxingCourseSearch("")}
                              className="absolute right-3 top-1/2 inline-flex h-7 w-7 -translate-y-1/2 items-center justify-center rounded-full text-stone-400 transition-colors hover:bg-stone-100 hover:text-stone-700 dark:text-stone-500 dark:hover:bg-stone-800 dark:hover:text-stone-200"
                              aria-label="清空课程搜索"
                              title="清空课程搜索"
                            >
                              <X size={14} />
                            </button>
                          ) : null}
                        </div>
                        <div className="max-h-56 space-y-2 overflow-auto pr-1">
                          {filteredChaoxingCourses.length ? filteredChaoxingCourses.map((course) => (
                            <button
                              key={course.courseKey}
                              type="button"
                              onClick={() => setSelectedChaoxingCourseKey(course.courseKey)}
                              className={`w-full cursor-pointer rounded-2xl border px-4 py-3 text-left transition-colors ${
                                selectedChaoxingCourseKey === course.courseKey
                                  ? "border-accent bg-accent/10"
                                  : "border-stone-200 bg-white dark:border-stone-700 dark:bg-neutral-950"
                              }`}
                            >
                              <p className="text-sm font-bold text-stone-900 dark:text-stone-100">{course.title}</p>
                              <p className="mt-1 text-xs text-stone-500 dark:text-zinc-400">
                                {[course.teacher, course.openTime].filter(Boolean).join(" · ") || "超星课程"}
                              </p>
                            </button>
                          )) : (
                            <p className="rounded-2xl border border-dashed border-stone-200 px-4 py-6 text-center text-sm font-semibold text-stone-600 dark:border-stone-700 dark:text-zinc-300">
                              {chaoxingCourses.length ? "没有匹配的课程。" : "没有读取到可导入课程。"}
                            </p>
                          )}
                        </div>
                      </div>
                    )}
                  </div>
                )}
              </div>
            ) : isSeriesCreation ? (
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
                  className="w-full rounded-2xl border border-stone-200 bg-white px-4 py-2.5 text-sm font-medium text-stone-900 transition-all placeholder:text-stone-400 focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent/10 disabled:opacity-60 dark:border-stone-700 dark:bg-neutral-900 dark:text-stone-100 dark:placeholder:text-zinc-500"
                  autoFocus
                />
              </div>
            ) : null}

            {sourceType === "local" ? (
            <div>
              <label className="mb-2 block text-xs font-bold tracking-wide text-stone-600 dark:text-zinc-400">
                选择媒体文件
              </label>
              <label className="flex cursor-pointer flex-col gap-2 rounded-2xl border border-dashed border-stone-300 bg-stone-50 px-4 py-4 transition hover:border-accent hover:bg-accent/5 dark:border-stone-700 dark:bg-neutral-900">
                <div className="flex items-center gap-2 text-sm font-semibold text-stone-700 dark:text-stone-200">
                  <Film size={16} />
                  {selectedFileSummary}
                </div>
                <p className="text-xs text-stone-500 dark:text-zinc-400">
                  支持多选，导入时会复制到项目媒体目录。
                </p>
                <input
                  type="file"
                  accept="video/*,audio/*,.mp4,.mov,.mkv,.avi,.webm,.m4v,.mp3,.wav,.m4a,.aac,.flac,.ogg,.opus,.wma"
                  multiple
                  disabled={status === "loading"}
                  onChange={(event) => setFiles(Array.from(event.target.files ?? []))}
                  className="hidden"
                />
              </label>
            </div>
            ) : null}

            {status === "success" && preview ? (
              <motion.div
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                className="flex items-center gap-4 rounded-2xl border border-success bg-success-subtle p-4"
              >
                <CheckCircle2 size={20} className="shrink-0 text-success" />
                <div className="min-w-0">
                  <p className="truncate text-sm font-bold text-stone-900 dark:text-stone-100">{preview.title}</p>
                  <p className="mt-0.5 text-xs text-success">
                    共 {preview.videoCount} 个视频 · 已导入
                  </p>
                </div>
              </motion.div>
            ) : null}

            {status === "loading" && sourceType === "external" && externalProvider === "chaoxing" ? (
              <motion.div
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                className="rounded-2xl border border-accent/20 bg-accent/5 p-4"
              >
                <div className="mb-2 flex items-center justify-between gap-3">
                  <p className="min-w-0 truncate text-xs font-bold text-stone-700 dark:text-stone-200">
                    {chaoxingImportProgress?.detail || "正在导入超星课程..."}
                  </p>
                  <p className="shrink-0 text-xs font-bold text-accent">
                    {typeof chaoxingImportProgress?.progress === "number"
                      ? `${Math.round(chaoxingImportProgress.progress)}%`
                      : "处理中"}
                  </p>
                </div>
                <div className="h-2 overflow-hidden rounded-full bg-stone-200 dark:bg-neutral-800">
                  <div
                    className="h-full rounded-full bg-accent transition-all duration-300"
                    style={{ width: `${Math.max(4, Math.min(100, chaoxingImportProgress?.progress ?? 8))}%` }}
                  />
                </div>
              </motion.div>
            ) : null}

            {status === "error" ? (
              <motion.div
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                className="flex items-start gap-3 rounded-2xl border border-danger bg-danger-subtle p-4"
              >
                <AlertCircle size={18} className="mt-0.5 shrink-0 text-red-500" />
                <p className="min-w-0 flex-1 text-sm font-medium text-danger">{errorMsg}</p>
                <button
                  type="button"
                  onClick={() => {
                    setStatus("idle");
                    setErrorMsg("");
                  }}
                  className="inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-red-500 transition-colors hover:bg-red-100 hover:text-red-700 dark:hover:bg-red-950/50 dark:hover:text-red-100"
                  title="关闭错误提示"
                  aria-label="关闭错误提示"
                >
                  <X size={15} />
                </button>
              </motion.div>
            ) : null}
          </div>

          <div className="flex justify-end gap-3 px-6 pb-6">
            <button
              type="button"
              onClick={handleClose}
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
              className="inline-flex items-center gap-2 rounded-2xl bg-accent px-5 py-2.5 text-sm font-bold text-white shadow-sm transition-colors hover:bg-accent/90 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {status === "loading" ? <Loader2 size={16} className="animate-spin" /> : null}
              {sourceType === "external" ? (externalProvider === "chaoxing" ? "导入课程" : "解析") : actionLabel}
            </button>
          </div>
        </motion.div>
      </motion.div>
    </AnimatePresence>
  );
}

function toChaoxingInitErrorMessage(error) {
  const message = error instanceof Error ? error.message : "超星初始化失败";
  if (message.includes("超星初始化已中断")) {
    return "超星初始化已中断";
  }
  return message;
}
