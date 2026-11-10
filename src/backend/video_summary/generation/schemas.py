"""生成层 Pydantic 载荷模型。

定义 LLM 输出与制品之间互相转换所用的 DTO 形态：章节、整篇总结、
思维导图节点、转写片段、转写增强结果。
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, ValidationInfo, model_validator

from backend.shared.llm.diagnostics import log_llm_event

# 校验上下文键：开启后 `SummaryPayload` 在校验前自动修正 LLM 常见的章节时间小错。
# 只给 LLM 生成路径开启；用户手动编辑总结时仍按原规则严格校验。
REPAIR_CHAPTERS_CONTEXT_KEY = "repair_summary_chapters"
VIDEO_DURATION_CONTEXT_KEY = "video_duration_seconds"


def summary_repair_context(video_duration_seconds: float | None) -> dict[str, object]:
    """构造开启章节自动修正的 Pydantic 校验上下文。"""
    return {REPAIR_CHAPTERS_CONTEXT_KEY: True, VIDEO_DURATION_CONTEXT_KEY: video_duration_seconds}


class SummaryChapterPayload(BaseModel):
    """单章节总结的载荷模型。

    Attributes:
        id: 章节业务 ID，对应前端锚点定位。
        title: 章节标题。
        start_seconds: 章节起始时间（秒）。
        end_seconds: 章节结束时间（秒）。
        summary: 章节小结文本。
        key_points: 章节要点列表。
    """

    id: str
    title: str
    start_seconds: float = Field(default=0.0, allow_inf_nan=False)
    end_seconds: float = Field(default=0.0, allow_inf_nan=False)
    summary: str = ""
    key_points: list[str] = Field(default_factory=list)
    image_timestamp_seconds: float | None = Field(default=None, allow_inf_nan=False)

    @model_validator(mode="after")
    def validate_time_range(self) -> "SummaryChapterPayload":
        if self.start_seconds < 0:
            raise ValueError("章节 start_seconds 不能小于 0。")
        if self.end_seconds <= self.start_seconds:
            raise ValueError("章节 end_seconds 必须严格大于 start_seconds。")
        if (
            self.image_timestamp_seconds is not None
            and not self.start_seconds <= self.image_timestamp_seconds <= self.end_seconds
        ):
            raise ValueError("章节 image_timestamp_seconds 必须位于章节时间范围内。")
        return self


class SummaryPayload(BaseModel):
    """整篇视频总结的载荷模型。

    Attributes:
        title: 视频标题。
        one_sentence_summary: 一句话总结。
        core_problem: 视频核心要解决的问题。
        chapters: 章节总结列表。
        key_takeaways: 关键结论列表。
    """

    title: str
    one_sentence_summary: str = ""
    core_problem: str = ""
    chapters: list[SummaryChapterPayload] = Field(default_factory=list)
    key_takeaways: list[str] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def repair_chapter_times(cls, data: Any, info: ValidationInfo) -> Any:
        context = info.context or {}
        if not context.get(REPAIR_CHAPTERS_CONTEXT_KEY) or not isinstance(data, dict):
            return data
        chapters = data.get("chapters")
        if not isinstance(chapters, list) or not chapters:
            return data
        repaired, actions = repair_chapters(chapters, context.get(VIDEO_DURATION_CONTEXT_KEY))
        if not actions:
            return data
        log_llm_event("summary_chapters_repaired", actions=actions)
        return {**data, "chapters": repaired}

    @model_validator(mode="after")
    def validate_chapter_sequence(self) -> "SummaryPayload":
        if len({chapter.id for chapter in self.chapters}) != len(self.chapters):
            raise ValueError("章节 id 不能重复。")
        for previous, current in zip(self.chapters, self.chapters[1:]):
            if current.start_seconds < previous.end_seconds:
                raise ValueError(
                    f"章节必须按时间排序且互不重叠：{current.id} 的 start_seconds "
                    f"({current.start_seconds}) 不能小于 {previous.id} 的 end_seconds ({previous.end_seconds})。"
                )
        return self


def repair_chapters(chapters: list[Any], video_duration_seconds: float | None) -> tuple[list[Any], list[str]]:
    """确定性地修正 LLM 章节时间里能明确判断怎么改的小错，避免整份重新生成。

    依次：最后一章结束时间不足视频时长时补到视频末尾；后一章开始早于前一章结束时，
    把前一章结束改成后一章开始；零长或倒序章节并入上一章（第一章则并入下一章）；
    配图时间截回本章范围。任何时间字段无法解析为数字时原样返回，交给校验报错。

    Returns:
        (修正后的章节列表, 修正动作描述列表)；没有修正时动作列表为空。
    """
    items = [dict(item.model_dump() if isinstance(item, BaseModel) else item) for item in chapters
        if isinstance(item, (dict, BaseModel))]
    if len(items) != len(chapters):
        return chapters, []
    times: list[list[float | None]] = []
    for item in items:
        start, end = _as_number(item.get("start_seconds", 0.0)), _as_number(item.get("end_seconds", 0.0))
        image = item.get("image_timestamp_seconds")
        image_value = None if image is None else _as_number(image)
        if start is None or end is None or (image is not None and image_value is None):
            return chapters, []
        times.append([start, end, image_value])

    actions: list[str] = []
    duration = _as_number(video_duration_seconds) if video_duration_seconds is not None else None
    last = times[-1]
    # 提示词里的时长只保留一位小数，差不到 1 秒是取整误差，不算错误。
    if duration is not None and last[0] < duration and duration - last[1] >= 1.0:
        actions.append(f"{_chapter_label(items[-1])}: end {last[1]:g} -> {duration:g} (video end)")
        last[1] = duration
    for index in range(1, len(times)):
        previous, current = times[index - 1], times[index]
        if current[0] < previous[1]:
            actions.append(f"{_chapter_label(items[index - 1])}: end {previous[1]:g} -> {current[0]:g} (overlap)")
            previous[1] = current[0]

    index = 0
    while index < len(items) and len(items) > 1:
        start, end, _ = times[index]
        if end > start:
            index += 1
            continue
        if index > 0:
            target = index - 1
            covered = max(start, end)
            if index + 1 < len(times):
                covered = min(covered, times[index + 1][0])
            times[target][1] = max(times[target][1], covered)
        else:
            target = 1
            times[target][0] = min(times[target][0], start)
        actions.append(f"{_chapter_label(items[index])}: zero-length [{start:g}, {end:g}] merged into "
            f"{_chapter_label(items[target])}")
        _merge_key_points(items[target], items[index], prepend=target > index)
        del items[index], times[index]
        if index > 0:
            index -= 1

    for item, (start, end, image) in zip(items, times):
        item["start_seconds"], item["end_seconds"] = start, end
        if image is not None and end > start and not start <= image <= end:
            clamped = min(max(image, start), end)
            actions.append(f"{_chapter_label(item)}: image {image:g} -> {clamped:g}")
            image = clamped
        if image is not None:
            item["image_timestamp_seconds"] = image
    return items, actions


def _as_number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number == number and number not in (float("inf"), float("-inf")) else None


def _chapter_label(item: dict) -> str:
    return str(item.get("id") or item.get("title") or "?")


def _merge_key_points(target: dict, source: dict, *, prepend: bool = False) -> None:
    points = target.get("key_points")
    extra = source.get("key_points")
    if not isinstance(points, list) or not isinstance(extra, list):
        return
    added = [point for point in extra if point not in points]
    target["key_points"] = [*added, *points] if prepend else [*points, *added]


class VisualEvidenceFramePayload(BaseModel):
    """一张已抽取视频帧的可检索文字证据。"""

    chapter_id: str = Field(min_length=1)
    timestamp_seconds: float = Field(allow_inf_nan=False)
    image_filename: str = Field(min_length=1)
    text: str = Field(min_length=1)


class VisualEvidencePayload(BaseModel):
    """一次多模态总结生成的逐帧视觉证据集合。"""

    frames: list[VisualEvidenceFramePayload] = Field(default_factory=list)


class MultimodalSummaryPayload(BaseModel):
    """多模态最终化调用的结构化响应。"""

    summary: SummaryPayload
    visual_evidence: VisualEvidencePayload


class MindmapNodePayload(BaseModel):
    """思维导图节点的载荷模型（递归结构）。

    Attributes:
        id: 节点业务 ID。
        title: 节点标题。
        summary: 节点摘要文本。
        start_seconds: 节点对应的时间起点（秒）；无时间锚点时为 0.0。
        end_seconds: 节点对应的时间终点（秒）；无时间锚点时为 0.0。
        children: 子节点列表。
    """

    id: str
    title: str
    summary: str = ""
    start_seconds: float = Field(default=0.0)
    end_seconds: float = Field(default=0.0)
    children: list["MindmapNodePayload"] = Field(default_factory=list)


class FlatMindmapNodePayload(BaseModel):
    """非递归思维导图节点载荷。

    ``parent_id`` 将节点组织关系从递归 ``children`` 移到平铺节点表中，
    使本地模型服务可以使用不含循环引用的 JSON Schema 约束输出。
    """

    id: str = Field(min_length=1)
    parent_id: str | None
    title: str = Field(min_length=1)
    summary: str = ""
    start_seconds: float = Field(default=0.0)
    end_seconds: float = Field(default=0.0)


class FlatMindmapPayload(BaseModel):
    """用于非递归 JSON Schema 的思维导图节点表。"""

    nodes: list[FlatMindmapNodePayload] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_tree(self) -> "FlatMindmapPayload":
        """验证节点关系确实能还原为一棵树，根节点通过 parent_id=None 推导。"""
        node_by_id = {node.id: node for node in self.nodes}
        if len(node_by_id) != len(self.nodes):
            raise ValueError("思维导图节点 id 不能重复。")

        # 找出所有根节点（parent_id 为 None）
        root_nodes = [node for node in self.nodes if node.parent_id is None]
        if len(root_nodes) == 0:
            raise ValueError("至少需要一个根节点（parent_id 为 null）。")
        if len(root_nodes) > 1:
            raise ValueError("只能有一个根节点，但找到多个 parent_id 为 null 的节点。")

        root = root_nodes[0]

        # 验证所有非根节点都能连接到根节点
        for node in self.nodes:
            if node.id == root.id:
                continue
            if node.parent_id is None:
                raise ValueError("只能有一个根节点（parent_id 为 null）。")
            if node.parent_id not in node_by_id:
                raise ValueError(f"节点 {node.id} 的 parent_id 不存在。")

            path: set[str] = set()
            current = node
            while current.id != root.id:
                if current.id in path:
                    raise ValueError("思维导图节点不能形成父子环。")
                path.add(current.id)
                parent_id = current.parent_id
                if parent_id is None:
                    raise ValueError("所有非根节点必须连接到根节点。")
                current = node_by_id[parent_id]

        return self

    def to_tree(self) -> MindmapNodePayload:
        """将已验证的节点表转换为前端沿用的递归树结构。"""
        node_by_id = {node.id: node for node in self.nodes}
        children_by_parent: dict[str, list[FlatMindmapNodePayload]] = {
            node.id: [] for node in self.nodes
        }
        for node in self.nodes:
            if node.parent_id is not None:
                children_by_parent[node.parent_id].append(node)

        def build_node(node_id: str) -> MindmapNodePayload:
            node = node_by_id[node_id]
            return MindmapNodePayload(
                id=node.id,
                title=node.title,
                summary=node.summary,
                start_seconds=node.start_seconds,
                end_seconds=node.end_seconds,
                children=[build_node(child.id) for child in children_by_parent[node_id]],
            )

        # 找到根节点（parent_id 为 None）
        root = next(node for node in self.nodes if node.parent_id is None)
        return build_node(root.id)


class TranscriptSegmentPayload(BaseModel):
    """转写片段的载荷模型。

    Attributes:
        start_seconds: 片段起始时间（秒）。
        end_seconds: 片段结束时间（秒）。
        text: 片段文本。
    """

    start_seconds: float = Field(default=0.0)
    end_seconds: float = Field(default=0.0)
    text: str


class TranscriptEnhancementPayload(BaseModel):
    """转写增强结果的载荷模型。

    Attributes:
        segments: 增强后的转写片段列表。
    """

    segments: list[TranscriptSegmentPayload] = Field(default_factory=list)
