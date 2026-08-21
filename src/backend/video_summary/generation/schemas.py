"""生成层 Pydantic 载荷模型。

定义 LLM 输出与制品之间互相转换所用的 DTO 形态：章节、整篇总结、
思维导图节点、转写片段、转写增强结果。
"""

from __future__ import annotations

from pydantic import BaseModel, Field, model_validator


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

    root_id: str = Field(min_length=1)
    nodes: list[FlatMindmapNodePayload] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_tree(self) -> "FlatMindmapPayload":
        """验证节点关系确实能还原为一棵以 ``root_id`` 为根的树。"""
        node_by_id = {node.id: node for node in self.nodes}
        if len(node_by_id) != len(self.nodes):
            raise ValueError("思维导图节点 id 不能重复。")

        root = node_by_id.get(self.root_id)
        if root is None:
            raise ValueError("root_id 必须引用 nodes 中的节点。")
        if root.parent_id is not None:
            raise ValueError("根节点的 parent_id 必须为 null。")

        for node in self.nodes:
            if node.id == self.root_id:
                continue
            if node.parent_id is None:
                raise ValueError("只有根节点的 parent_id 可以为 null。")
            if node.parent_id not in node_by_id:
                raise ValueError(f"节点 {node.id} 的 parent_id 不存在。")

            path: set[str] = set()
            current = node
            while current.id != self.root_id:
                if current.id in path:
                    raise ValueError("思维导图节点不能形成父子环。")
                path.add(current.id)
                parent_id = current.parent_id
                if parent_id is None:
                    raise ValueError("所有节点必须连接到 root_id。")
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

        return build_node(self.root_id)


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
