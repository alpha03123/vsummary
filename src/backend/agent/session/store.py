"""基于本地 JSON 文件的 Agent 会话存储实现。

每个会话对应 `root_dir/<sha1(session_id)>.json` 一个文件，文件
内容就是 `AgentSessionSnapshot` 的序列化结果。所有写操作通过
`KeyedLockManager` 按 `session_id` 串行化，避免同一会话并发
写入造成覆盖。
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from backend.shared.filesystem import KeyedLockManager, atomic_write_text
from backend.agent.memory.context import AgentContext
from backend.agent.schemas.messages import AgentChatMessage
from backend.agent.session.models import AgentSessionMessageEntry, AgentSessionSnapshot, utc_now_iso


class FileAgentSessionStore:
    """以单文件 JSON 为后端的 `AgentSessionStore` 实现。

    适合单机部署；写操作是「读—改—全量覆盖」，因此即使新会话也是
    直接覆写整张快照（不会留下空文件）。文件路径由 `session_id`
    经 SHA-1 摘要得到，避免会话 ID 中出现路径不安全字符。

    Attributes:
        _root_dir: 快照文件存放目录（构造时确定）。
        _session_locks: 按 `session_id` 加锁的锁管理器，串行化
            同一会话的并发写。
    """

    def __init__(self, root_dir: Path) -> None:
        """初始化文件型会话存储。

        Args:
            root_dir: 快照文件存放目录，调用方需保证目录存在或可创建。
        """

        self._root_dir = root_dir
        self._session_locks = KeyedLockManager()

    def get_snapshot(self, session_id: str) -> AgentSessionSnapshot | None:
        """读取指定会话的快照。

        整个读操作在会话级锁内进行，确保读到的是某次完整写入的
        快照而非并发覆写中间态。

        Args:
            session_id: 会话唯一 ID。

        Returns:
            反序列化后的快照；文件不存在时返回 `None`。
        """

        with self._session_locks.hold(session_id):
            return self._read_snapshot_unlocked(session_id)

    def append_turn(
        self,
        *,
        session_id: str,
        memory_key: str,
        context: AgentContext,
        messages: list[AgentChatMessage],
    ) -> None:
        """把当前轮的上下文 + 消息历史整体写回快照。

        写入语义是「整体覆盖」而非「追加单条消息」：每次都把整份
        消息历史序列化到磁盘（消息历史本身已在内存中由调用方
        维护）。首次写入时若文件不存在会创建快照，否则仅覆盖
        `context` / `memory_key` / `messages` / `updated_at`。

        Args:
            session_id: 会话唯一 ID。
            memory_key: 当前轮次所使用的工作区记忆桶键。
            context: 本轮使用的 `AgentContext`（会被拷贝以切断
                与调用方状态的耦合）。
            messages: 本轮要持久化的消息历史（已含本轮问答）。
        """

        with self._session_locks.hold(session_id):
            snapshot = self._read_snapshot_unlocked(session_id)
            timestamp = utc_now_iso()
            sanitized_context = context.model_copy()
            if snapshot is None:
                snapshot = AgentSessionSnapshot(
                    session_id=session_id,
                    memory_key=memory_key,
                    context=sanitized_context,
                    updated_at=timestamp,
                )

            snapshot.context = sanitized_context
            snapshot.memory_key = memory_key
            snapshot.messages = [
                AgentSessionMessageEntry(
                    role=message.role,
                    content=message.content,
                    created_at=timestamp,
                    citations=message.citations,
                )
                for message in messages
            ]
            snapshot.updated_at = timestamp
            self._write_snapshot(snapshot)

    def clear_snapshot(self, session_id: str) -> None:
        """删除指定会话的快照文件。

        若文件不存在则视为空操作；调用方负责在删除后让上层缓存
        一并失效。

        Args:
            session_id: 会话唯一 ID。
        """

        with self._session_locks.hold(session_id):
            snapshot_path = self._build_snapshot_path(session_id)
            if snapshot_path.exists():
                snapshot_path.unlink()

    def _write_snapshot(self, snapshot: AgentSessionSnapshot) -> None:
        """把快照以格式化 JSON 原子写入磁盘。"""

        snapshot_path = self._build_snapshot_path(snapshot.session_id)
        atomic_write_text(
            snapshot_path,
            snapshot.model_dump_json(indent=2),
        )

    def _read_snapshot_unlocked(self, session_id: str) -> AgentSessionSnapshot | None:
        """无锁读取快照；要求调用方已持有对应会话锁。"""

        snapshot_path = self._build_snapshot_path(session_id)
        if not snapshot_path.exists():
            return None
        payload = json.loads(snapshot_path.read_text(encoding="utf-8"))
        return AgentSessionSnapshot.model_validate(payload)

    def _build_snapshot_path(self, session_id: str) -> Path:
        """把 `session_id` 哈希后映射到具体文件路径。"""

        digest = hashlib.sha1(session_id.encode("utf-8")).hexdigest()
        return self._root_dir / f"{digest}.json"
