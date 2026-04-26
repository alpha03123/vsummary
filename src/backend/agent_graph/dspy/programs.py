from __future__ import annotations

from collections.abc import Callable
from typing import Any, Literal

import dspy

from backend.agent.memory.context import AgentContext
from backend.agent.tools import list_model_visible_tool_definitions_for_context
from backend.agent_graph.query.models import CompareSplitDecision, StructuredQueryPlan


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
    available_actions: str = dspy.InputField(
        desc="当前上下文里真正可用的动作列表，包含动作名和用途说明。只能从这里选择 action_name。"
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
            "如果 goal=action，则只能从 available_actions 里列出的动作名中选择一个，且必须原样输出动作名；"
            "如果当前上下文没有合适动作，或 goal 不是 action，则输出空字符串。"
        )
    )
    action_args: dict[str, object] = dspy.OutputField(desc="动作参数；非 action 时输出空对象 {}。")
    candidate_video_ids: list[str] = dspy.OutputField(
        desc="如果已经能确定目标视频集，输出 video_id 数组；否则可留空。"
    )
    selected_videos: list[dict[str, object]] = dspy.OutputField(
        desc=(
            "如果已经能确定目标视频集，输出 selected_videos。"
            "每项包含 video_id、reason_for_selection。"
        )
    )
    selection_mode: Literal["fresh", "carry_forward"] = dspy.OutputField(
        desc="如果当前问题是在承接上一轮已选视频集，输出 carry_forward；否则 fresh。"
    )
    subplans: list[dict[str, object]] = dspy.OutputField(
        desc=(
            "可选。若你已经能明确执行结构，输出 subplans。"
            "每项包含 target_video_ids、depth、query。"
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


class SynthesizeNoteContent(dspy.Signature):
    user_message: str = dspy.InputField(
        desc="用户让系统保存/记录的内容请求。目标是生成可直接保存的 Markdown 笔记正文，而不是聊天回复。"
    )
    retrieval_results: list[dict[str, object]] = dspy.InputField(
        desc="当前请求相关的检索证据。只基于这些证据整理笔记，不要编造。"
    )
    meta_state: dict[str, object] = dspy.InputField()
    markdown: str = dspy.OutputField(
        desc=(
            "输出将被直接保存的 Markdown 笔记正文，不是聊天回复。"
            "第一行必须直接进入标题或主题，不允许任何开场白、过渡语、总结性客套语。"
            "禁止出现“当然”“可以帮你”“下面整理成”“如果你愿意”“我还可以”“这节视频讲了”等表达。"
            "不要使用“你”“我”“我们”这类对话指代。"
            "要求简洁、可编辑、可复习；保留关键结论、步骤、配置、参数、端口、路径等硬信息。"
        )
    )


class SynthesizeActionAfterContentReply(dspy.Signature):
    user_message: str = dspy.InputField(
        desc="用户原始请求。"
    )
    action_name: str = dspy.InputField(
        desc="刚刚执行的动作名，例如 save_note。"
    )
    generated_content: str = dspy.InputField(
        desc="已生成并保存用的正文内容。"
    )
    reply: str = dspy.OutputField(
        desc=(
            "输出 1 到 2 句自然、简短的回复，说明动作已完成，并可轻量提及已记录内容的主题。"
            "不要输出 Markdown，不要复述整篇笔记，不要使用客服腔和邀请继续提问的话术。"
        )
    )


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
    ) -> StructuredQueryPlan:
        context = AgentContext(
            session_id=f"{scope_type}|{series_id or 'unknown'}|classifier",
            scope_type=scope_type,
            series_id=series_id or None,
            video_id=video_id or None,
        )
        available_actions = _render_available_actions_for_classifier(context)
        raw = self._predictor(
            user_message=user_message,
            scope_type=scope_type,
            series_id=series_id,
            video_id=video_id,
            history_summary=history_summary,
            history_selected_videos=history_selected_videos or [],
            available_actions=available_actions,
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


class NoteSynthesisProgram:
    def __init__(self, predictor: Callable[..., Any] | None = None) -> None:
        self._predictor = predictor or dspy.ChainOfThought(SynthesizeNoteContent)

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
        markdown = payload.get("markdown", "")
        if not isinstance(markdown, str) or not markdown.strip():
            raise ValueError("DSPy note synthesis 缺少 markdown。")
        return markdown.strip()


class ActionAfterContentReplyProgram:
    def __init__(self, predictor: Callable[..., Any] | None = None) -> None:
        self._predictor = predictor or dspy.ChainOfThought(SynthesizeActionAfterContentReply)

    def run(
        self,
        *,
        user_message: str,
        action_name: str,
        generated_content: str,
    ) -> str:
        raw = self._predictor(
            user_message=user_message,
            action_name=action_name,
            generated_content=generated_content,
        )
        payload = _coerce_prediction(raw)
        reply = payload.get("reply", "")
        if not isinstance(reply, str) or not reply.strip():
            raise ValueError("DSPy action-after-content reply 缺少 reply。")
        return reply.strip()


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


def normalize_classifier_prediction(value: Any) -> StructuredQueryPlan:
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
    return StructuredQueryPlan.model_validate(payload)


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


def _render_available_actions_for_classifier(context: AgentContext) -> str:
    visible_tools = list_model_visible_tool_definitions_for_context(context)
    action_tools = [tool for tool in visible_tools if tool.plane.value == "ui_action"]
    if not action_tools:
        return "(none)"
    return "\n".join(
        f"- {tool.name.value}: {tool.title}。{tool.description}"
        for tool in action_tools
    )
