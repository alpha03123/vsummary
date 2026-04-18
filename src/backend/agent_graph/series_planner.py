from __future__ import annotations

from pydantic import BaseModel, Field

from backend.agent.memory.context import AgentContext
from backend.agent.ports import ChatGateway
from backend.agent.schemas.messages import AgentChatMessage
from backend.agent_graph.models import ExecutionDepth, SelectionMode
from backend.video_summary.library.ports import VideoWorkspace


class PlannerSubplanOutput(BaseModel):
    target_video_ids: list[str] = Field(default_factory=list)
    depth: ExecutionDepth
    query: str
    needs_probe: bool = False


class PlannerSelectedVideoOutput(BaseModel):
    video_id: str
    reason_for_selection: str = ""
    needs_probe: bool = False


class SeriesPlannerOutput(BaseModel):
    selected_videos: list[PlannerSelectedVideoOutput] = Field(default_factory=list)
    selection_mode: SelectionMode = SelectionMode.FRESH
    subplans: list[PlannerSubplanOutput] = Field(default_factory=list)
    reason: str = ""


class LegacyStyleSeriesPlanner:
    def __init__(self, *, workspace: VideoWorkspace, gateway: ChatGateway) -> None:
        self._workspace = workspace
        self._gateway = gateway

    def create_plan(
        self,
        *,
        user_message: str,
        series_id: str,
        series_title: str = "",
        history_messages: list[dict[str, object]] | None = None,
        previous_selected_videos: list[dict[str, object]] | None = None,
        debug_trace: dict[str, object] | None = None,
    ) -> dict[str, object]:
        series = next((item for item in self._workspace.list_series() if item.id == series_id), None)
        if series is None:
            raise RuntimeError(f"series '{series_id}' not found")

        fallback_candidate_ids = [video.id for video in series.videos]
        catalog_lines: list[str] = []
        for video in series.videos:
            summary = self._workspace.get_video_summary(series.id, video.id)
            if summary is None:
                catalog_lines.append(
                    f"- video_id={video.id}; title={video.title}; processed={video.processed}; summary=(none)"
                )
                continue
            raw_summary = summary.summary if isinstance(summary.summary, dict) else {}
            catalog_lines.append(
                _render_catalog_line(
                    video_id=video.id,
                    title=video.title,
                    processed=video.processed,
                    raw_summary=raw_summary,
                )
            )

        history_lines = [
            f"{str(item.get('role', '')).strip()}: {str(item.get('content', '')).strip()}"
            for item in (history_messages or [])
            if isinstance(item, dict) and str(item.get("content", "")).strip()
        ][-6:]
        previous_selection_lines = [
            f"- video_id={str(item.get('video_id', '')).strip()}; reason_for_selection={str(item.get('reason_for_selection', '')).strip()}"
            for item in (previous_selected_videos or [])
            if isinstance(item, dict) and str(item.get("video_id", "")).strip()
        ]

        planner_messages = _build_planner_messages(
            user_message=user_message,
            context=AgentContext(
                session_id=f"series|{series_id}|series-home",
                scope_type="series",
                series_id=series_id,
                series_title=series_title or series.title,
            ),
            catalog_lines=catalog_lines,
            history_lines=history_lines,
            previous_selection_lines=previous_selection_lines,
        )
        plan = self._create_contract_valid_plan(
            planner_messages=planner_messages,
            all_video_ids=fallback_candidate_ids,
            previous_selected_video_ids=[
                str(item.get("video_id", "")).strip()
                for item in (previous_selected_videos or [])
                if isinstance(item, dict) and str(item.get("video_id", "")).strip()
            ],
            debug_trace=debug_trace,
        )
        planner_supplied_subplans = bool(plan.subplans)
        selected_videos = _resolve_selected_videos(
            selected_videos=plan.selected_videos,
            selection_mode=plan.selection_mode,
            all_video_ids=fallback_candidate_ids,
            previous_selected_videos=previous_selected_videos or [],
        )
        candidate_ids = [item["video_id"] for item in selected_videos]
        if not candidate_ids and plan.selection_mode == SelectionMode.FRESH and not selected_videos and not planner_supplied_subplans:
            candidate_ids = fallback_candidate_ids

        subplans: list[dict[str, object]] = []
        for subplan in plan.subplans:
            target_ids = [video_id for video_id in subplan.target_video_ids if video_id in fallback_candidate_ids]
            if subplan.depth == ExecutionDepth.SERIES_META:
                target_ids = []
            elif not target_ids and subplan.depth != ExecutionDepth.SERIES_META:
                if candidate_ids:
                    target_ids = candidate_ids
                elif plan.selection_mode == SelectionMode.FRESH and not selected_videos and not planner_supplied_subplans:
                    target_ids = fallback_candidate_ids
            elif candidate_ids and subplan.depth != ExecutionDepth.SERIES_META:
                narrowed_ids = [video_id for video_id in target_ids if video_id in candidate_ids]
                target_ids = narrowed_ids or candidate_ids
            subplans.append(
                {
                    "target_video_ids": target_ids,
                    "depth": subplan.depth.value,
                    "query": subplan.query.strip() or user_message,
                    "needs_probe": subplan.needs_probe,
                }
            )
        if not subplans:
            subplans.append(
                {
                    "target_video_ids": candidate_ids,
                    "depth": ExecutionDepth.SUMMARY.value,
                    "query": user_message,
                    "needs_probe": False,
                }
            )

        result = {
            "goal": "series_content",
            "target_source": "all",
            "context_need": "chunk",
            "reason": plan.reason.strip(),
            "action_name": "",
            "action_args": {},
            "candidate_video_ids": candidate_ids,
            "selected_videos": selected_videos,
            "selection_mode": plan.selection_mode.value,
            "subplans": subplans,
        }
        if debug_trace is not None:
            debug_trace["legacy_series_planner"] = {
                "final_plan": result,
            }
        return result

    def _create_contract_valid_plan(
        self,
        *,
        planner_messages: list[AgentChatMessage],
        all_video_ids: list[str],
        previous_selected_video_ids: list[str],
        debug_trace: dict[str, object] | None = None,
        retries: int = 1,
    ) -> SeriesPlannerOutput:
        contract_error: str | None = None
        attempts: list[dict[str, object]] = []
        for attempt_index in range(retries + 1):
            messages = _build_contract_retry_messages(
                base_messages=planner_messages,
                contract_error=contract_error,
                all_video_ids=all_video_ids,
            )
            plan = self._gateway.create_structured_completion(
                messages,
                response_model=SeriesPlannerOutput,
            )
            contract_error = _validate_planner_contract(
                plan=plan,
                all_video_ids=all_video_ids,
                previous_selected_video_ids=previous_selected_video_ids,
            )
            attempts.append(
                {
                    "attempt_index": attempt_index,
                    "contract_error": contract_error,
                    "messages": [message.model_dump(mode="json") for message in messages],
                    "structured_output": plan.model_dump(mode="json"),
                }
            )
            if debug_trace is not None:
                debug_trace["legacy_series_planner_attempts"] = attempts
            if contract_error is None:
                return plan
            if attempt_index == retries:
                raise RuntimeError(f"legacy-style series planner returned invalid contract: {contract_error}")
        raise RuntimeError("legacy-style series planner returned invalid contract")


def _build_planner_messages(
    *,
    user_message: str,
    context: AgentContext,
    catalog_lines: list[str],
    history_lines: list[str],
    previous_selection_lines: list[str],
) -> list[AgentChatMessage]:
    history_block = "\n".join(history_lines) if history_lines else "(none)"
    catalog_block = "\n".join(catalog_lines) if catalog_lines else "(empty)"
    previous_selection_block = "\n".join(previous_selection_lines) if previous_selection_lines else "(none)"
    return [
        AgentChatMessage(
            role="system",
            content=(
                "你是 series 查询计划器。"
                "不要分类自然语言意图，不要输出 compare/action/meta_state 之类标签。"
                "你的职责是：基于当前 series 目录与上下文，做正向选择，只输出真正需要继续阅读或比较的视频。"
                "不要只看字面关键词是否重合，要根据 summary 描述的实际作用判断。"
                "即使视频标题或摘要里没有复现用户原词，只要它明显属于完成后续任务所需的前置准备、核心比较对象或必要证据，也可以纳入。"
                "只输出 selected_videos，不要为未选中的视频写 exclude reason。"
                "selected_videos 只能包含最终要纳入回答主体的视频；"
                "如果某个视频只是用来说明“为什么不算”或作为对照示例，它不能出现在 selected_videos 中。"
                "如果用户是在筛选“真正属于某一类的视频”，你必须按视频整体主题来判断，而不是按视频里顺带出现的一小段内容来判断。"
                "如果一节视频主体是在做框架介绍、能力说明、产品亮点或概念讲解，即使中间顺带出现启动、初始化、配置之类步骤，也不要把它放进 selected_videos。"
                "只有当视频整体主题本身就是前置准备、安装、初始化、环境搭建、账号/密钥配置这类内容时，才应纳入 selected_videos。"
                "如果当前问题明显是在承接上一轮已经选出的结果集，就把 selection_mode 设为 carry_forward。"
                "carry_forward 时，selected_videos 可以为空，表示继续沿用上一轮选择集。"
                "fresh 时，selected_videos 表示本轮重新从全集中选出的视频，且顺序必须与 series 原顺序一致。"
                "子计划的 depth 只能是 series_meta、summary、video_graph、video_workflow。"
                "series_meta 只用于系列级元信息；summary 用于跨视频浅层聚合；"
                "video_graph 用于需要深入单视频内部的细粒度定位、原话或单点事实核对。"
                "video_workflow 用于需要还原单视频里的连续执行流程、案例链、角色分工、产物路径。"
                "如果当前问题可以完全靠系列元数据回答，就用 series_meta。"
                "如果需要跨视频概括、筛选、比较或归纳，优先用 summary。"
                "如果问题明显要求细粒度时间点、单点原话或单个事实定位，用 video_graph。"
                "如果问题要求按视频顺序还原一个演示案例、执行过程、Agent 协作流程或最终产物落点，用 video_workflow。"
            ),
        ),
        AgentChatMessage(
            role="user",
            content=(
                f"当前 scope: {context.scope_type}\n"
                f"series_id: {context.series_id or ''}\n"
                f"series_title: {context.series_title or ''}\n\n"
                f"最近对话:\n{history_block}\n\n"
                f"上一轮已选视频:\n{previous_selection_block}\n\n"
                f"系列目录:\n{catalog_block}\n\n"
                f"当前用户问题:\n{user_message}"
            ),
        ),
    ]


def _build_contract_retry_messages(
    *,
    base_messages: list[AgentChatMessage],
    contract_error: str | None,
    all_video_ids: list[str],
) -> list[AgentChatMessage]:
    if not contract_error:
        return list(base_messages)
    return [
        *base_messages,
        AgentChatMessage(
            role="user",
            content=(
                "上一轮结构化输出违反业务约束，请直接修正 JSON，不要解释。\n"
                f"错误：{contract_error}\n"
                f"必须覆盖的 video_id：{', '.join(all_video_ids)}\n"
                "要求：selected_videos 只能包含目录中的 video_id；fresh 模式下需要明确给出选中的视频；carry_forward 只能在上一轮已有选择集时使用。"
            ),
        ),
    ]


def _render_catalog_line(
    *,
    video_id: str,
    title: str,
    processed: bool,
    raw_summary: dict[str, object],
) -> str:
    summary_parts = [
        str(raw_summary.get("one_sentence_summary", "")).strip(),
        str(raw_summary.get("core_problem", "")).strip(),
    ]
    summary_text = "；".join(part for part in summary_parts if part) or "(none)"
    key_takeaways = [
        takeaway.strip()
        for takeaway in raw_summary.get("key_takeaways", [])
        if isinstance(takeaway, str) and takeaway.strip()
    ]
    chapter_titles = [
        str(chapter.get("title", "")).strip()
        for chapter in raw_summary.get("chapters", [])
        if isinstance(chapter, dict) and str(chapter.get("title", "")).strip()
    ]
    extra_parts: list[str] = []
    if key_takeaways:
        extra_parts.append(f"key_takeaways={' | '.join(key_takeaways)}")
    if chapter_titles:
        extra_parts.append(f"chapters={' | '.join(chapter_titles)}")
    extras = f"; {'; '.join(extra_parts)}" if extra_parts else ""
    return f"- video_id={video_id}; title={title}; processed={processed}; summary={summary_text}{extras}"


def _validate_planner_contract(
    *,
    plan: SeriesPlannerOutput,
    all_video_ids: list[str],
    previous_selected_video_ids: list[str],
) -> str | None:
    selected_video_ids = [item.video_id for item in plan.selected_videos]
    duplicates = sorted({video_id for video_id in selected_video_ids if selected_video_ids.count(video_id) > 1})
    if duplicates:
        return f"selected_videos 存在重复 video_id: {', '.join(duplicates)}"
    unexpected = [video_id for video_id in selected_video_ids if video_id not in all_video_ids]
    if unexpected:
        return f"selected_videos 包含未知 video_id: {', '.join(unexpected)}"
    if plan.selection_mode == SelectionMode.CARRY_FORWARD and not previous_selected_video_ids:
        return "selection_mode=carry_forward 但上一轮没有可复用的选择集。"
    return None


def _resolve_selected_videos(
    *,
    selected_videos: list[PlannerSelectedVideoOutput],
    selection_mode: SelectionMode,
    all_video_ids: list[str],
    previous_selected_videos: list[dict[str, object]],
) -> list[dict[str, object]]:
    if selection_mode == SelectionMode.CARRY_FORWARD and previous_selected_videos:
        selected_ids = {item.video_id for item in selected_videos if item.video_id in all_video_ids}
        if selected_ids:
            return [
                {
                    "video_id": item.video_id,
                    "reason_for_selection": item.reason_for_selection.strip(),
                    "needs_probe": item.needs_probe,
                }
                for item in selected_videos
                if item.video_id in all_video_ids
            ]
        return [
            {
                "video_id": str(item.get("video_id", "")).strip(),
                "reason_for_selection": str(item.get("reason_for_selection", "")).strip(),
                "needs_probe": False,
            }
            for item in previous_selected_videos
            if str(item.get("video_id", "")).strip() in all_video_ids
        ]

    normalized_selected_videos: list[dict[str, object]] = []
    seen_video_ids: set[str] = set()
    for item in selected_videos:
        if item.video_id not in all_video_ids or item.video_id in seen_video_ids:
            continue
        seen_video_ids.add(item.video_id)
        normalized_selected_videos.append(
            {
                "video_id": item.video_id,
                "reason_for_selection": item.reason_for_selection.strip(),
                "needs_probe": item.needs_probe,
            }
        )
    return normalized_selected_videos
