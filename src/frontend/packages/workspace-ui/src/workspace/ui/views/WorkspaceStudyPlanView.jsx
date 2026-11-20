import { useCallback, useEffect, useRef, useState } from "react";
import { CalendarDays, Clock, PlayCircle, RefreshCw } from "lucide-react";

import { useWorkspaceRuntime } from "../../WorkspaceRuntime";
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

/**
 * 学习计划：一个视频或整个合集按每天的学习时长分好的课。
 * 面板自己读取计划、提交生成任务并跟踪进度；生成动作走宿主的 action，
 * 这样云端可以在提交前插入计费确认。
 */
export function WorkspaceStudyPlanView({ scope, seriesId, videoId, available, onGenerate, onOpenSegment }) {
  const { api } = useWorkspaceRuntime();
  const [plan, setPlan] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [progress, setProgress] = useState(null);
  const [dialogOpen, setDialogOpen] = useState(false);
  const unsubscribeRef = useRef(null);

  const planUrl = scope === "series"
    ? `/api/series/${encodeURIComponent(seriesId)}/study-plan`
    : `/api/videos/${encodeURIComponent(seriesId)}/${encodeURIComponent(videoId ?? "")}/study-plan`;

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

  const dialog = (
    <DailyMinutesDialog
      open={dialogOpen}
      initialMinutes={plan?.daily_minutes ?? DEFAULT_DAILY_MINUTES}
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

  if (!plan) {
    if (!available) {
      return (
        <WorkspaceStateBlock
          title="需要先生成 AI 概括"
          description={scope === "series" ? "学习计划按各视频的章节来排，合集里至少要有一个视频生成了 AI 概括。" : "学习计划按 AI 概括里的章节来排，请先生成 AI 概括。"}
        />
      );
    }
    return (
      <WorkspaceStateBlock
        title="还没有学习计划"
        description={scope === "series" ? "按每天能学的时间，把整个合集分成一节节课，每节有目标和练习。" : "按每天能学的时间，把这个视频分成一节节课，每节有目标和练习。"}
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

  const sessions = Array.isArray(plan.sessions) ? plan.sessions : [];
  return (
    <div className="flex flex-col gap-5">
      <section className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-[min(100%,18rem)] flex-1">
          <p className="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-subtle">
            <span>每天约 {plan.daily_minutes} 分钟</span>
            <span className="text-faint">·</span>
            <span>共 {sessions.length} 天</span>
            <span className="text-faint">·</span>
            <span>合计约 {plan.total_minutes} 分钟</span>
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

      {error ? <p className="text-sm text-danger">{error}</p> : null}

      {plan.prerequisites?.length ? (
        <section className="rounded-3xl border border-line-soft bg-soft/60 px-5 py-4">
          <h3 className="text-sm font-bold text-strong">开始前最好已经会</h3>
          <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-body">
            {plan.prerequisites.map((item) => <li key={item}>{item}</li>)}
          </ul>
        </section>
      ) : null}

      <ol className="flex flex-col gap-4">
        {sessions.map((session) => (
          <li key={session.index} className="workspace-elevated-panel rounded-4xl border p-5 @[480px]:p-6">
            <header className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
              <h3 className="text-base font-bold text-strong">
                <span className="mr-2 text-subtle">第 {session.index} 天</span>
                {session.title}
              </h3>
              <span className="inline-flex items-center gap-1 text-xs font-medium text-subtle">
                <Clock size={13} strokeWidth={2.2} />
                约 {session.study_minutes} 分钟
              </span>
            </header>
            {session.goal ? <p className="mt-2 text-sm leading-relaxed text-body">{session.goal}</p> : null}

            <ul className="mt-4 flex flex-col gap-1.5">
              {(session.segments ?? []).map((segment, index) => (
                <li key={`${segment.video_id}-${segment.start_seconds}-${index}`}>
                  <button
                    type="button"
                    onClick={() => onOpenSegment?.(segment)}
                    className="group flex w-full items-start gap-2 rounded-xl px-2 py-1.5 text-left text-sm transition-colors hover:bg-accent/8"
                  >
                    <PlayCircle size={16} strokeWidth={2.2} className="mt-0.5 shrink-0 text-faint group-hover:text-accent" />
                    <span className="min-w-0 flex-1 text-body">
                      {scope === "series" ? <span className="text-subtle">{segment.video_title} · </span> : null}
                      {segment.chapter_title}
                    </span>
                    <span className="shrink-0 font-mono text-xs text-subtle">
                      {formatPlanTime(segment.start_seconds)}–{formatPlanTime(segment.end_seconds)}
                    </span>
                  </button>
                </li>
              ))}
            </ul>

            {session.focus?.length ? (
              <div className="mt-4">
                <h4 className="text-xs font-bold text-subtle">重点</h4>
                <ul className="mt-1.5 list-disc space-y-1 pl-5 text-sm leading-relaxed text-body">
                  {session.focus.map((item) => <li key={item}>{item}</li>)}
                </ul>
              </div>
            ) : null}
            {session.practice?.length ? (
              <div className="mt-4">
                <h4 className="text-xs font-bold text-subtle">练习</h4>
                <ul className="mt-1.5 list-disc space-y-1 pl-5 text-sm leading-relaxed text-body">
                  {session.practice.map((item) => <li key={item}>{item}</li>)}
                </ul>
              </div>
            ) : null}
          </li>
        ))}
      </ol>
      {dialog}
    </div>
  );
}

function DailyMinutesDialog({ open, initialMinutes, onCancel, onConfirm }) {
  const [minutes, setMinutes] = useState(initialMinutes);
  useEffect(() => {
    if (open) setMinutes(initialMinutes);
  }, [open, initialMinutes]);

  return (
    <WorkspaceDialog
      open={open}
      title="每天能学多久？"
      description="按这个时长把内容分成一节节课。时长按视频长度的 1.3 倍估算，留出暂停和记笔记的时间。"
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
    </WorkspaceDialog>
  );
}
