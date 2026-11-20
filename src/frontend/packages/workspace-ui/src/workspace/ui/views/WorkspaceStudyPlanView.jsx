import { useCallback, useEffect, useRef, useState } from "react";
import { CalendarDays, Check, ChevronRight, Clock, PlayCircle, RefreshCw } from "lucide-react";

import { useWorkspaceRuntime } from "../../../runtime/WorkspaceProvider";
import { WorkspaceDialog } from "../shared/WorkspaceDialog";
import { WorkspaceGenerationStatus } from "../shared/WorkspaceGenerationStatus";
import { WorkspaceStateBlock } from "../shared/WorkspaceStateBlock";

const DAILY_MINUTE_OPTIONS = [20, 30, 45, 60, 90];
const DEFAULT_DAILY_MINUTES = 45;

export function formatPlanTime(seconds) {
  const total = Math.max(0, Math.floor(Number(seconds) || 0));
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const secs = String(total % 60).padStart(2, "0");
  return hours ? `${hours}:${String(minutes).padStart(2, "0")}:${secs}` : `${minutes}:${secs}`;
}

export function formatTotalMinutes(minutes) {
  const value = Math.max(0, Math.round(Number(minutes) || 0));
  if (value < 60) return `${value} 分钟`;
  const rest = value % 60;
  return rest ? `${Math.floor(value / 60)} 小时 ${rest} 分` : `${Math.floor(value / 60)} 小时`;
}

function localIsoDate(date) {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
}

function shortDate(value) {
  const [, month, day] = String(value).split("-").map(Number);
  return month && day ? `${month}月${day}日` : String(value);
}

/**
 * 每一天的日程：已学完的显示完成日期；第一个没学完的是“今天”，其后的日期从今天依次顺延。
 * 漏学几天不会出现“落后”，打开看到的始终是一份可以接着学的计划。
 */
export function scheduleSessions(sessions, progress, today = new Date()) {
  let offset = 0;
  return sessions.map((session) => {
    const completedOn = progress?.[String(session.index)] ?? null;
    if (completedOn) return { ...session, completedOn, isToday: false, dateLabel: `已学完 · ${shortDate(completedOn)}` };
    const date = new Date(today.getFullYear(), today.getMonth(), today.getDate() + offset);
    const entry = { ...session, completedOn: null, isToday: offset === 0, dateLabel: offset === 0 ? "今天" : shortDate(localIsoDate(date)) };
    offset += 1;
    return entry;
  });
}

/**
 * 学习计划：一个视频或一门课程按每天的学习时长分好的课。
 * 面板自己读取计划、提交生成任务并跟踪进度；生成动作走宿主的 action，
 * 这样云端可以在提交前插入计费确认。
 */
export function WorkspaceStudyPlanView({ scope, seriesId, videoId, available, seriesVideos = [], onGenerate, onOpenSegment, onOpenSeriesPlan }) {
  const { api } = useWorkspaceRuntime();
  const [plan, setPlan] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [progress, setProgress] = useState(null);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [savingIndex, setSavingIndex] = useState(null);
  // 默认只展开“今天”那一课；这里记的是用户手动切换过展开状态的课。
  const [toggledSessions, setToggledSessions] = useState(() => new Set());
  const unsubscribeRef = useRef(null);

  // 视频页读的也是课程计划，只显示包含这个视频的那几天。
  const planUrl = `/api/series/${encodeURIComponent(seriesId)}/study-plan`;

  const loadPlan = useCallback(async () => {
    const payload = await api.fetchJson(planUrl, undefined, { notFoundValue: null });
    setPlan(payload ?? null);
  }, [api, planUrl]);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    setPlan(null);
    api.fetchJson(planUrl, undefined, { notFoundValue: null })
      .then((payload) => { if (!cancelled) setPlan(payload ?? null); })
      .catch((reason) => { if (!cancelled) setError(reason instanceof Error ? reason.message : "学习计划读取失败"); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [api, planUrl]);

  useEffect(() => () => unsubscribeRef.current?.(), []);

  async function generate(dailyMinutes) {
    setDialogOpen(false);
    setError(null);
    let submitted;
    try {
      submitted = await onGenerate?.(dailyMinutes);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "学习计划生成失败");
      return;
    }
    if (!submitted?.jobId) {
      return; // 宿主取消了（例如云端确认框里点了取消）。
    }
    setProgress({ status: "queued", startedAt: Date.now() / 1000 });
    unsubscribeRef.current?.();
    unsubscribeRef.current = api.subscribeDurableJobProgress(submitted.jobId, async (snapshot) => {
      setProgress(snapshot);
      if (snapshot.status === "completed") {
        unsubscribeRef.current?.();
        try {
          await loadPlan();
        } catch (reason) {
          setError(reason instanceof Error ? reason.message : "学习计划读取失败");
        }
        setProgress(null);
      } else if (snapshot.status === "failed" || snapshot.status === "cancelled") {
        unsubscribeRef.current?.();
        setProgress(null);
        setError(snapshot.error || snapshot.detail || "学习计划生成失败");
      }
    });
  }

  async function toggleDone(session) {
    setSavingIndex(session.index);
    setError(null);
    try {
      const updated = await api.fetchJson(`${planUrl}/progress`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ plan_id: plan.id ?? null, index: session.index, completed_on: session.completedOn ? null : localIsoDate(new Date()) }),
      });
      setPlan(updated);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "进度保存失败");
    } finally {
      setSavingIndex(null);
    }
  }

  const hasProgress = Object.keys(plan?.progress ?? {}).length > 0;
  const dialog = (
    <DailyMinutesDialog
      open={dialogOpen}
      initialMinutes={plan?.daily_minutes ?? DEFAULT_DAILY_MINUTES}
      warning={hasProgress ? "重新安排将清空当前进度。" : null}
      onCancel={() => setDialogOpen(false)}
      onConfirm={generate}
    />
  );

  if (progress) {
    return (
      <WorkspaceStateBlock title="正在安排学习计划">
        <WorkspaceGenerationStatus snapshot={progress} label="正在按章节分课" />
      </WorkspaceStateBlock>
    );
  }

  if (loading) {
    return <WorkspaceStateBlock title="载入学习计划" loading />;
  }

  if (!plan && scope === "video") {
    return (
      <WorkspaceStateBlock title="课程还没有学习计划">
        <OpenSeriesPlanButton onClick={onOpenSeriesPlan} label="制定课程计划" />
      </WorkspaceStateBlock>
    );
  }

  if (!plan) {
    if (!available) {
      return scope === "series"
        ? <WorkspaceStateBlock title="需要先生成 AI 概括" description="课程中暂无已生成 AI 概括的视频。" />
        : <WorkspaceStateBlock title="需要先生成 AI 概括" />;
    }
    return (
      <WorkspaceStateBlock
        title="还没有学习计划"
        description={scope === "series" ? "为这门课程制定每日学习计划。" : "为这个视频制定每日学习计划。"}
      >
        {error ? <p className="mb-3 text-sm text-danger">{error}</p> : null}
        <button
          type="button"
          onClick={() => setDialogOpen(true)}
          className="inline-flex items-center gap-2 rounded-2xl bg-inverse px-5 py-3 text-sm font-semibold text-on-accent transition hover:bg-accent"
        >
          <CalendarDays size={16} strokeWidth={2.2} />
          制定学习计划
        </button>
        {dialog}
      </WorkspaceStateBlock>
    );
  }

  const allSessions = scheduleSessions(Array.isArray(plan.sessions) ? plan.sessions : [], plan.progress);
  if (scope === "video") {
    const videoSessions = allSessions.filter((session) => (session.segments ?? []).some((segment) => segment.video_id === videoId));
    if (!videoSessions.length) {
      return (
        <WorkspaceStateBlock title="此视频未纳入课程计划" description="重新安排课程计划后纳入。">
          <OpenSeriesPlanButton onClick={onOpenSeriesPlan} label="查看课程计划" />
        </WorkspaceStateBlock>
      );
    }
    return (
      <div className="flex flex-col gap-5">
        <section className="flex flex-wrap items-center justify-between gap-4">
          <p className="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-subtle">
            <span className="font-semibold text-body">{formatDayRange(videoSessions)}</span>
            <span className="text-faint">·</span>
            <span>课程共 {allSessions.length} 天</span>
            <span className="text-faint">·</span>
            <span>每天约 {plan.daily_minutes} 分钟</span>
          </p>
          <OpenSeriesPlanButton onClick={onOpenSeriesPlan} label="查看课程计划" subtle />
        </section>
        {error ? <p className="text-sm text-danger">{error}</p> : null}
        <SessionList sessions={videoSessions} scope="series" expandAll savingIndex={savingIndex} onToggleDone={toggleDone} onOpenSegment={onOpenSegment} />
      </div>
    );
  }
  const sessions = allSessions;
  const currentPosition = sessions.findIndex((session) => !session.completedOn);
  const plannedVideoIds = new Set(sessions.flatMap((session) => (session.segments ?? []).map((segment) => segment.video_id)));
  const missingCount = scope === "series"
    ? seriesVideos.filter((video) => !plannedVideoIds.has(video.id) && !video.processed).length
    : 0;
  const toggleExpanded = (index) => setToggledSessions((current) => {
    const next = new Set(current);
    if (next.has(index)) next.delete(index);
    else next.add(index);
    return next;
  });

  return (
    <div className="flex flex-col gap-5">
      <section className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-[min(100%,18rem)] flex-1">
          <p className="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-subtle">
            <span className="font-semibold text-body">{currentPosition < 0 ? "已全部学完" : `第 ${currentPosition + 1} 天`}</span>
            <span className="text-faint">·</span>
            <span>共 {sessions.length} 天</span>
            <span className="text-faint">·</span>
            <span>每天约 {plan.daily_minutes} 分钟</span>
            <span className="text-faint">·</span>
            <span>{plan.video_minutes ? `视频共 ${formatTotalMinutes(plan.video_minutes)}` : `合计约 ${formatTotalMinutes(plan.total_minutes)}`}</span>
          </p>
          {plan.overview ? <p className="mt-2 text-sm leading-relaxed text-body">{plan.overview}</p> : null}
        </div>
        <button
          type="button"
          onClick={() => setDialogOpen(true)}
          className="inline-flex items-center gap-2 rounded-xl border border-line bg-surface px-3 py-2 text-xs font-semibold text-subtle transition-colors hover:border-accent/30 hover:bg-accent/8 hover:text-accent"
        >
          <RefreshCw size={14} strokeWidth={2.2} />
          重新安排
        </button>
      </section>

      {missingCount > 0 ? (
        <p className="rounded-2xl border border-warning-border bg-warning-subtle px-4 py-3 text-sm text-warning">
          {missingCount} 个视频尚未生成 AI 概括，未纳入计划。
        </p>
      ) : null}

      {error ? <p className="text-sm text-danger">{error}</p> : null}

      {plan.prerequisites?.length ? (
        <section className="rounded-3xl border border-line-soft bg-soft/60 px-5 py-4">
          <h3 className="text-sm font-bold text-strong">前置知识</h3>
          <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-body">
            {plan.prerequisites.map((item) => <li key={item}>{item}</li>)}
          </ul>
        </section>
      ) : null}

      <SessionList sessions={sessions} scope={scope} toggledSessions={toggledSessions} onToggleExpanded={toggleExpanded} savingIndex={savingIndex} onToggleDone={toggleDone} onOpenSegment={onOpenSegment} />
      {dialog}
    </div>
  );
}

function formatDayRange(sessions) {
  const first = sessions[0].index;
  const last = sessions[sessions.length - 1].index;
  return first === last ? `课程第 ${first} 天` : `课程第 ${first}–${last} 天`;
}

function OpenSeriesPlanButton({ onClick, label, subtle = false }) {
  if (!onClick) return null;
  return (
    <button
      type="button"
      onClick={onClick}
      className={subtle
        ? "inline-flex items-center gap-1.5 rounded-xl border border-line bg-surface px-3 py-2 text-xs font-semibold text-subtle transition-colors hover:border-accent/30 hover:bg-accent/8 hover:text-accent"
        : "inline-flex items-center gap-2 rounded-2xl bg-inverse px-5 py-3 text-sm font-semibold text-on-inverse transition hover:bg-accent hover:text-on-accent"}
    >
      <CalendarDays size={subtle ? 14 : 16} strokeWidth={2.2} />
      {label}
    </button>
  );
}

/** 每一课一张卡片；默认只展开“今天”那一课（expandAll 时全部展开）。 */
function SessionList({ sessions, scope, toggledSessions = null, onToggleExpanded = null, expandAll = false, savingIndex, onToggleDone, onOpenSegment }) {
  const isExpanded = (session) => expandAll || Boolean(session.isToday) !== Boolean(toggledSessions?.has(session.index));
  return (
    <ol className="flex flex-col gap-3">
      {sessions.map((session) => {
        const expanded = isExpanded(session);
        return (
          <li
            key={session.index}
            className={`rounded-4xl border ${expanded ? "workspace-elevated-panel p-5 @[480px]:p-6" : "border-line-soft bg-surface px-5 py-4"} ${session.isToday && expanded ? "border-accent/50" : ""} ${session.completedOn ? "opacity-70" : ""}`}
          >
            <header className="flex items-center justify-between gap-4">
              <button
                type="button"
                onClick={() => onToggleExpanded?.(session.index)}
                disabled={!onToggleExpanded}
                aria-expanded={expanded}
                className="group flex min-w-0 flex-1 items-start gap-2 text-left disabled:cursor-default"
              >
                {onToggleExpanded ? <ChevronRight size={16} strokeWidth={2.2} className={`mt-0.5 shrink-0 text-faint transition-transform group-hover:text-body ${expanded ? "rotate-90" : ""}`} /> : null}
                <span className="min-w-0">
                  <span className={`block text-xs font-semibold ${session.isToday ? "text-accent" : "text-subtle"}`}>
                    {session.dateLabel} · 第 {session.index} 天
                  </span>
                  <span className="mt-1 block text-base font-bold text-strong">{session.title}</span>
                </span>
              </button>
              <div className="flex shrink-0 items-center gap-3">
                <span className="inline-flex items-center gap-1 text-xs font-medium text-subtle">
                  <Clock size={13} strokeWidth={2.2} />
                  约 {session.study_minutes} 分钟
                </span>
                <button
                  type="button"
                  disabled={savingIndex === session.index}
                  onClick={() => onToggleDone(session)}
                  aria-pressed={Boolean(session.completedOn)}
                  className={`inline-flex items-center gap-1.5 rounded-xl border px-3 py-1.5 text-xs font-semibold transition-colors disabled:opacity-50 ${session.completedOn ? "border-success-border bg-success-subtle text-success" : "border-line bg-surface text-body hover:border-accent/30 hover:text-accent"}`}
                >
                  <Check size={14} strokeWidth={2.4} />
                  {session.completedOn ? "已学完" : "学完了"}
                </button>
              </div>
            </header>
            {expanded ? <SessionBody session={session} scope={scope} indent={Boolean(onToggleExpanded)} onOpenSegment={onOpenSegment} /> : null}
          </li>
        );
      })}
    </ol>
  );
}

/** 连续属于同一个视频的片段合成一组，视频名只出现一次。 */
export function groupSegmentsByVideo(segments) {
  const groups = [];
  for (const segment of segments ?? []) {
    const last = groups[groups.length - 1];
    if (last && last.videoId === segment.video_id) last.segments.push(segment);
    else groups.push({ videoId: segment.video_id, videoTitle: segment.video_title, segments: [segment] });
  }
  return groups;
}

function SectionTitle({ children, minutes }) {
  return (
    <h4 className="text-xs font-bold text-subtle">
      {children}
      {minutes ? <span className="ml-1.5 font-medium text-faint">约 {minutes} 分钟</span> : null}
    </h4>
  );
}

function SessionBody({ session, scope, indent = true, onOpenSegment }) {
  const groups = groupSegmentsByVideo(session.segments);
  return (
    <div className={`mt-3 ${indent ? "pl-6" : ""}`}>
      {session.goal ? <p className="text-sm leading-relaxed text-body">{session.goal}</p> : null}

      <div className="mt-4">
        <SectionTitle minutes={session.watch_minutes}>要看的内容</SectionTitle>
        <div className="mt-1.5 flex flex-col gap-2">
          {groups.map((group, groupIndex) => {
            const first = group.segments[0];
            const last = group.segments[group.segments.length - 1];
            return (
              <div key={`${group.videoId}-${groupIndex}`}>
                {scope === "series" ? (
                  <button
                    type="button"
                    onClick={() => onOpenSegment?.(first)}
                    className="group flex w-full items-center gap-2 rounded-xl px-2 py-1.5 text-left text-sm transition-colors hover:bg-accent/8"
                  >
                    <PlayCircle size={16} strokeWidth={2.2} className="shrink-0 text-faint group-hover:text-accent" />
                    <span className="min-w-0 flex-1 truncate font-semibold text-strong">{group.videoTitle}</span>
                    <span className="shrink-0 font-mono text-xs text-subtle">
                      {formatPlanTime(first.start_seconds)}–{formatPlanTime(last.end_seconds)}
                    </span>
                  </button>
                ) : null}
                <ul className={scope === "series" ? "ml-4 border-l border-line-soft pl-2" : ""}>
                  {group.segments.map((segment, index) => (
                    <li key={`${segment.start_seconds}-${index}`}>
                      <button
                        type="button"
                        onClick={() => onOpenSegment?.(segment)}
                        className="group flex w-full items-start gap-2 rounded-lg px-2 py-1 text-left text-sm transition-colors hover:bg-accent/8"
                      >
                        {scope === "series"
                          ? <span className="mt-2 h-1 w-1 shrink-0 rounded-full bg-current text-ghost group-hover:text-accent" />
                          : <PlayCircle size={16} strokeWidth={2.2} className="mt-0.5 shrink-0 text-faint group-hover:text-accent" />}
                        <span className="min-w-0 flex-1 text-body group-hover:text-strong">{segment.chapter_title}</span>
                        <span className="shrink-0 font-mono text-xs text-faint">{formatPlanTime(segment.start_seconds)}</span>
                      </button>
                    </li>
                  ))}
                </ul>
              </div>
            );
          })}
        </div>
      </div>

      {session.focus?.length ? (
        <div className="mt-4">
          <SectionTitle>重点</SectionTitle>
          <ul className="mt-1.5 list-disc space-y-1 pl-5 text-sm leading-relaxed text-body">
            {session.focus.map((item) => <li key={item}>{item}</li>)}
          </ul>
        </div>
      ) : null}
      {session.practice?.length ? (
        <div className="mt-4">
          <SectionTitle minutes={session.practice_minutes}>练习</SectionTitle>
          <ul className="mt-1.5 list-disc space-y-1 pl-5 text-sm leading-relaxed text-body">
            {session.practice.map((item) => <li key={item}>{item}</li>)}
          </ul>
        </div>
      ) : null}
    </div>
  );
}

function DailyMinutesDialog({ open, initialMinutes, warning, onCancel, onConfirm }) {
  const [minutes, setMinutes] = useState(initialMinutes);
  useEffect(() => {
    if (open) setMinutes(initialMinutes);
  }, [open, initialMinutes]);

  return (
    <WorkspaceDialog
      open={open}
      title="每天学习多久？"
      description="学习内容将按此时长分配到每天。"
      icon={<CalendarDays size={19} />}
      onClose={onCancel}
      onSubmit={() => onConfirm(minutes)}
      footer={(
        <>
          <button type="button" onClick={onCancel} className="rounded-xl bg-soft px-4 py-2.5 text-sm font-semibold text-subtle">取消</button>
          <button type="submit" className="rounded-xl bg-accent px-4 py-2.5 text-sm font-bold text-on-accent">生成计划</button>
        </>
      )}
    >
      <div role="radiogroup" aria-label="每天学习时长" className="grid grid-cols-5 gap-2">
        {DAILY_MINUTE_OPTIONS.map((option) => {
          const selected = option === minutes;
          return (
            <button
              key={option}
              type="button"
              role="radio"
              aria-checked={selected}
              onClick={() => setMinutes(option)}
              className={`rounded-xl border px-2 py-2.5 text-sm font-semibold transition-colors ${selected ? "border-accent bg-accent/10 text-accent" : "border-line bg-surface text-body hover:border-accent/30"}`}
            >
              {option}
              <span className="ml-0.5 text-xs font-medium">分钟</span>
            </button>
          );
        })}
      </div>
      {warning ? <p className="mt-3 text-xs text-warning">{warning}</p> : null}
    </WorkspaceDialog>
  );
}
