from __future__ import annotations

from collections.abc import Callable
from typing import Any, Literal

import dspy

from backend.agent_graph.query.models import CompareSplitDecision, DecomposeDecision, SeriesQueryDecision


class DecomposeUserTask(dspy.Signature):
    user_message: str = dspy.InputField(
        desc="用户原始请求。你要把它拆成一个或多个简单任务。"
    )
    scope_type: str = dspy.InputField(
        desc="当前上下文范围。video 只能围绕当前视频；series 才能跨视频。"
    )
    series_id: str = dspy.InputField(desc="当前 series 标识。")
    video_id: str = dspy.InputField(desc="当前 video 标识，series 场景可为空。")
    tasks: list[dict[str, object]] = dspy.OutputField(
        desc=(
            "输出 tasks 数组。每个 task 只能包含 task_id、instruction、depends_on、kind_hint 四个字段。"
            "task_id 用 task-1/task-2...；instruction 用中文简洁描述单步任务；"
            "depends_on 只表示真实数据依赖，不表示自然语言顺序；"
            "kind_hint 只能是 understand/locate/compare/meta_state/action 之一。"
            "简单目标输出 1 个 task，复合目标拆分为多个 task，并保持依赖关系。"
        )
    )
    reason: str = dspy.OutputField(desc="简短说明拆分原因。")


class ClassifySeriesQuery(dspy.Signature):
    user_message: str = dspy.InputField(
        desc="用户当前这一条任务/请求文本。你要判断它属于理解、定位、比较、状态查询还是动作请求。"
    )
    scope_type: Literal["video", "series"] = dspy.InputField(
        desc="当前上下文范围。video 只能围绕当前视频；series 才能跨视频/跨章节。"
    )
    series_id: str = dspy.InputField(desc="当前 series 标识。")
    video_id: str = dspy.InputField(desc="当前 video 标识；若 scope 是 series 则可能为空。")
    history_summary: str = dspy.InputField(
        desc="当前会话的压缩历史摘要；如果为空，说明没有可复用的历史。"
    )
    history_selected_videos: list[dict[str, object]] = dspy.InputField(
        desc=(
            "上一轮已经筛出的 selected_videos。"
            "如果当前问题明显是在承接上一轮视频集，应优先输出 selection_mode=carry_forward，"
            "并沿用这些 video_id，而不是重新从全集中胡乱猜。"
        )
    )
    goal: Literal["understand", "locate", "compare", "meta_state", "action"] = dspy.OutputField(
        desc=(
            "任务类型。只能输出 understand/locate/compare/meta_state/action 之一。"
            "understand=概括理解；locate=找位置或原话；compare=比较多个对象；"
            "meta_state=问资源状态；action=明确要求打开/生成/保存/跳转。"
        )
    )
    target_source: Literal["summary", "transcript", "all"] = dspy.OutputField(
        desc=(
            "证据来源。只能输出 summary/transcript/all 之一。"
            "understand 通常选 summary；locate 通常选 transcript；compare 通常选 all；"
            "meta_state 和 action 默认用 all。"
        )
    )
    context_need: Literal["chunk", "continuous"] = dspy.OutputField(
        desc="上下文粒度。只能输出 chunk 或 continuous。默认 chunk；明确要求前后文或原话细节时用 continuous。"
    )
    reason: str = dspy.OutputField(desc="简短说明分类原因。")
    action_name: str = dspy.OutputField(
        desc=(
            "如果 goal=action，则从 open_overview/open_mindmap/open_notes/open_video/"
            "save_note/video_seek/generate_overview/generate_mindmap 中选一个；否则输出空字符串。"
        )
    )
    action_args: dict[str, object] = dspy.OutputField(desc="动作参数；非 action 时输出空对象 {}。")
    candidate_video_ids: list[str] = dspy.OutputField(
        desc="如果已经能确定目标视频集，输出 video_id 数组；否则可留空。"
    )
    selected_videos: list[dict[str, object]] = dspy.OutputField(
        desc=(
            "如果已经能确定目标视频集，输出 selected_videos。"
            "每项包含 video_id、reason_for_selection、needs_probe。"
        )
    )
    selection_mode: Literal["fresh", "carry_forward"] = dspy.OutputField(
        desc="如果当前问题是在承接上一轮已选视频集，输出 carry_forward；否则 fresh。"
    )
    subplans: list[dict[str, object]] = dspy.OutputField(
        desc=(
            "可选。若你已经能明确执行结构，输出 subplans。"
            "每项包含 target_video_ids、depth、query、needs_probe。"
            "depth 只能是 series_meta/summary/video_graph。"
        )
    )


class SplitCompareQuery(dspy.Signature):
    user_message: str = dspy.InputField(
        desc="一个比较类任务文本。你要提取出需要分别检索的对象或概念。"
    )
    queries: list[str] = dspy.OutputField(
        desc=(
            "只输出对象/概念本身，不要输出完整问题，不要输出用途句、关系句、搜索词扩写、官方文档提示。"
            "例如输入“Jmanus 和 AgentScope 的定位有什么不同”时，应输出 [\"Jmanus\", \"AgentScope\"]。"
            "如果有三个并列对象，就输出三个对象。"
        )
    )
    reason: str = dspy.OutputField(desc="简短说明拆分原因。")


class SynthesizeSeriesAnswer(dspy.Signature):
    user_message: str = dspy.InputField()
    retrieval_results: list[dict[str, object]] = dspy.InputField()
    meta_state: dict[str, object] = dspy.InputField()
    answer: str = dspy.OutputField()


class UpdateConversationMemory(dspy.Signature):
    history_summary: str = dspy.InputField()
    user_message: str = dspy.InputField()
    assistant_message: str = dspy.InputField()
    task_outputs: list[dict[str, object]] = dspy.InputField()
    history_summary_update: str = dspy.OutputField()


class TaskDecomposerProgram:
    def __init__(self, predictor: Callable[..., Any] | None = None) -> None:
        self._predictor = predictor or dspy.ChainOfThought(DecomposeUserTask)

    def run(self, *, user_message: str, scope_type: str, series_id: str, video_id: str = "") -> DecomposeDecision:
        raw = self._predictor(
            user_message=user_message,
            scope_type=scope_type,
            series_id=series_id,
            video_id=video_id,
        )
        return normalize_decompose_prediction(raw)


class SeriesQueryClassifierProgram:
    def __init__(self, predictor: Callable[..., Any] | None = None) -> None:
        self._predictor = predictor or dspy.Predict(ClassifySeriesQuery)

    def run(
        self,
        *,
        user_message: str,
        scope_type: str,
        series_id: str,
        video_id: str = "",
        history_summary: str = "",
        history_selected_videos: list[dict[str, object]] | None = None,
    ) -> SeriesQueryDecision:
        raw = self._predictor(
            user_message=user_message,
            scope_type=scope_type,
            series_id=series_id,
            video_id=video_id,
            history_summary=history_summary,
            history_selected_videos=history_selected_videos or [],
        )
        return normalize_classifier_prediction(raw)


class CompareSplitProgram:
    def __init__(self, predictor: Callable[..., Any] | None = None) -> None:
        self._predictor = predictor or dspy.ChainOfThought(SplitCompareQuery)

    def run(self, *, user_message: str) -> CompareSplitDecision:
        raw = self._predictor(user_message=user_message)
        return normalize_split_compare_prediction(raw)


class AnswerSynthesisProgram:
    def __init__(self, predictor: Callable[..., Any] | None = None) -> None:
        self._predictor = predictor or dspy.ChainOfThought(SynthesizeSeriesAnswer)

    def run(
        self,
        *,
        user_message: str,
        retrieval_results: list[dict[str, object]],
        meta_state: dict[str, object] | None = None,
    ) -> str:
        raw = self._predictor(
            user_message=user_message,
            retrieval_results=retrieval_results,
            meta_state=meta_state or {},
        )
        payload = _coerce_prediction(raw)
        answer = payload.get("answer", "")
        if not isinstance(answer, str) or not answer.strip():
            raise ValueError("DSPy answer synthesis 缺少 answer。")
        return answer.strip()


class MemoryUpdateProgram:
    def __init__(self, predictor: Callable[..., Any] | None = None) -> None:
        self._predictor = predictor or dspy.ChainOfThought(UpdateConversationMemory)

    def run(
        self,
        *,
        history_summary: str,
        user_message: str,
        assistant_message: str,
        task_outputs: list[dict[str, object]],
    ) -> str:
        raw = self._predictor(
            history_summary=history_summary,
            user_message=user_message,
            assistant_message=assistant_message,
            task_outputs=task_outputs,
        )
        payload = _coerce_prediction(raw)
        result = payload.get("history_summary_update", "")
        if not isinstance(result, str):
            raise ValueError("DSPy memory update 缺少 history_summary_update。")
        return result.strip()


def _coerce_prediction(value: Any) -> dict[str, object]:
    if isinstance(value, dict):
        return dict(value)
    if hasattr(value, "items"):
        return dict(value.items())
    if hasattr(value, "__dict__"):
        return {
            key: item
            for key, item in vars(value).items()
            if not key.startswith("_")
        }
    raise TypeError("无法将 DSPy 输出转换为结构化字典。")


def normalize_decompose_prediction(value: Any) -> DecomposeDecision:
    payload = _coerce_prediction(value)
    tasks = payload.get("tasks")
    if not isinstance(tasks, list) or not tasks:
        raise ValueError("DSPy decompose 缺少 tasks。")
    normalized_tasks: list[dict[str, object]] = []
    for index, task in enumerate(tasks, start=1):
        if not isinstance(task, dict):
            continue
        normalized_tasks.append(
            {
                "task_id": str(task.get("task_id") or f"task-{index}").strip(),
                "instruction": str(task.get("instruction") or task.get("user_query") or "").strip(),
                "depends_on": task.get("depends_on") if isinstance(task.get("depends_on"), list) else [],
                "kind_hint": str(task.get("kind_hint") or task.get("task_type") or "").strip(),
            }
        )
    payload["tasks"] = normalized_tasks
    return DecomposeDecision.model_validate(payload)


def normalize_classifier_prediction(value: Any) -> SeriesQueryDecision:
    payload = _coerce_prediction(value)
    if not payload.get("goal"):
        raise ValueError("DSPy classify 缺少 goal。")
    if not payload.get("target_source"):
        raise ValueError("DSPy classify 缺少 target_source。")
    if not payload.get("context_need"):
        raise ValueError("DSPy classify 缺少 context_need。")
    if payload.get("action_args") is None:
        payload["action_args"] = {}
    if payload.get("candidate_video_ids") is None:
        payload["candidate_video_ids"] = []
    if payload.get("selected_videos") is None:
        payload["selected_videos"] = []
    if payload.get("selection_mode") is None:
        payload["selection_mode"] = "fresh"
    if payload.get("subplans") is None:
        payload["subplans"] = []
    return SeriesQueryDecision.model_validate(payload)


def normalize_split_compare_prediction(value: Any) -> CompareSplitDecision:
    payload = _coerce_prediction(value)
    queries = payload.get("queries")
    if not isinstance(queries, list) or not queries:
        raise ValueError("DSPy split_compare 缺少 queries。")
    normalized_queries = [
        str(item).strip()
        for item in queries
        if isinstance(item, str) and str(item).strip()
    ]
    payload["queries"] = normalized_queries
    return CompareSplitDecision.model_validate(payload)
