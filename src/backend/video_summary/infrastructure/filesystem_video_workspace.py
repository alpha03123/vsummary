"""以本地文件系统为后端的工作区存储与导入/删除实现。

本模块是 `VideoLibraryReader/VideoLibraryWriter/VideoImporter` 等端口的
`FileSystem` 适配器，负责：

- 把视频库中的"系列 / 视频 / 制品"以目录 + JSON 文件的形式落到磁盘；
- 提供笔记等需要"按视频串行化"的写入能力（基于 `KeyedLockManager`）；
- 在导入系列 / 视频时做去重、原子复制与失败回滚；
- 在删除系列 / 视频时同步清理本地媒体与制品目录，必要时回写 linked 元数据。

目录布局约定：
    ``<root_dir>/videos/<series_id>/<video_stem>.<ext>``     # 原始媒体
    ``<root_dir>/workspace/<series_id>/series_meta.json``   # 系列元数据
    ``<root_dir>/workspace/<series_id>/linked_series.json`` # 外部链接系列的元数据
    ``<root_dir>/workspace/<series_id>/series_catalog.json``# 系列目录（Agent 知识记忆用）
    ``<root_dir>/workspace/<series_id>/<video_id>/summary.json``
    ``<root_dir>/workspace/<series_id>/<video_id>/summary.md``
    ``<root_dir>/workspace/<series_id>/<video_id>/transcript.cleaned.json``
    ``<root_dir>/workspace/<series_id>/<video_id>/transcript.enhanced.json``
    ``<root_dir>/workspace/<series_id>/<video_id>/knowledge_cards.json``
    ``<root_dir>/workspace/<series_id>/<video_id>/mindmap.json``
    ``<root_dir>/workspace/<series_id>/<video_id>/notes.json``

线程安全：笔记的 CRUD 通过 `KeyedLockManager` 按 `(series_id, video_id)`
串行化；其他路径不做并发控制，依赖上层用例的互斥。
"""

from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from backend.shared.filesystem import KeyedLockManager, atomic_write_text
from backend.video_summary.infrastructure.agent_memory.document_schema import SeriesCatalogPayload
from backend.video_summary.library.constants import PLAYGROUND_SERIES_ID
from backend.video_summary.library.linked_models import LinkedSeries, LinkedVideo
from backend.video_summary.library.models import (
    ChapterCardDTO as ChapterCardDTO,
    KnowledgeCardDTO as KnowledgeCardDTO,
    LibrarySeriesDTO as LibrarySeriesDTO,
    LibraryVideoCardDTO as LibraryVideoCardDTO,
    TranscriptSegmentDTO as TranscriptSegmentDTO,
    VideoChapterCardsDTO as VideoChapterCardsDTO,
    VideoKnowledgeCardsDTO as VideoKnowledgeCardsDTO,
    VideoMindmapDTO as VideoMindmapDTO,
    VideoNoteDTO as VideoNoteDTO,
    VideoNotesDTO as VideoNotesDTO,
    VideoSourceDTO as VideoSourceDTO,
    VideoSummaryDTO as VideoSummaryDTO,
    VideoTranscriptDTO as VideoTranscriptDTO,
    VideoWorkspaceToolsDTO as VideoWorkspaceToolsDTO,
    WorkspaceDTO as WorkspaceDTO,
    WorkspaceToolDTO as WorkspaceToolDTO,
)

VIDEO_SUFFIXES = {".mp4", ".mov", ".mkv", ".avi", ".webm", ".m4v"}
AUDIO_SUFFIXES = {".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg", ".opus", ".wma"}
MEDIA_SUFFIXES = VIDEO_SUFFIXES | AUDIO_SUFFIXES

LINKED_SERIES_META_FILE = "linked_series.json"
SERIES_META_FILE = "series_meta.json"
SERIES_CATALOG_FILE = "series_catalog.json"


class FileSystemVideoWorkspace:
    """以本地目录树为后端的工作区适配器。

    业务目的：为上层用例（视频库读取、制品写入、本地导入、笔记 CRUD 等）提供
    一套以"目录 + JSON 文件"为基本存储介质的实现，使得整个视频库在无数据库
    依赖的情况下也能完成列表 / 检索 / 编辑 / 删除等操作。

    关键不变量：
        - `videos/<series_id>/` 内的媒体文件名（不含后缀）即 `video_id`；
        - `workspace/<series_id>/<video_id>/` 存放该视频的所有制品；
        - 笔记的并发写受 `KeyedLockManager` 保护，其他写操作依赖上层互斥。
    """

    def __init__(self, root_dir: Path) -> None:
        """记录工作区根目录、计算 `videos/` 与 `workspace/` 子目录路径。

        Args:
            root_dir: 工作区根目录（包含 `videos/` 与 `workspace/` 两个子目录）。
        """
        self._root_dir = root_dir
        self._videos_dir = root_dir / "videos"
        self._workspace_dir = root_dir / "workspace"
        self._notes_locks = KeyedLockManager()

    def get_workspace(self) -> WorkspaceDTO:
        """返回工作区自身的 DTO：id 取根目录名，title 经标题化处理。"""
        workspace_id = self._root_dir.name
        return WorkspaceDTO(
            id=workspace_id,
            title=_to_title(workspace_id),
        )

    def list_series(self) -> list[LibrarySeriesDTO]:
        """列出工作区内的所有系列，合并本地系列与 linked 系列并去重。

        关键规则：
            - 优先扫描 `videos/<series_id>/`，每个子目录视为一个本地系列；
            - 再扫描 `workspace/<series_id>/linked_series.json`，存在则视为
              linked 系列，标题/source_url 从元数据回填；
            - 同一 `series_id` 在两边都存在时，linked 元数据覆盖本地目录；
            - 若不存在 `PLAYGROUND_SERIES_ID` 则补一条空的 Playground 占位记录。

        Returns:
            按目录遍历顺序（`sorted`）汇总的 `LibrarySeriesDTO` 列表。
        """
        local_series: dict[str, LibrarySeriesDTO] = {}

        if self._videos_dir.exists():
            for series_dir in sorted(self._videos_dir.iterdir()):
                if not series_dir.is_dir():
                    continue
                series_title = self._read_series_title(series_dir.name) or _to_title(series_dir.name)
                local_series[series_dir.name] = LibrarySeriesDTO(
                    id=series_dir.name,
                    title=series_title,
                    videos=self._list_videos_for_series(series_dir),
                )

        if self._workspace_dir.exists():
            for ws_dir in sorted(self._workspace_dir.iterdir()):
                if not ws_dir.is_dir():
                    continue
                linked_meta_path = ws_dir / LINKED_SERIES_META_FILE
                if not linked_meta_path.exists():
                    continue
                payload = json.loads(linked_meta_path.read_text(encoding="utf-8"))
                series_id = ws_dir.name
                local_series[series_id] = LibrarySeriesDTO(
                    id=series_id,
                    title=str(payload.get("title", _to_title(series_id))).strip() or _to_title(series_id),
                    videos=self._list_videos_for_linked_series(
                        series_id=series_id,
                        linked_meta=payload,
                        local_video_dir=self._videos_dir / series_id,
                    ),
                    is_linked=series_id != PLAYGROUND_SERIES_ID,
                    source_url=str(payload.get("source_url", "")),
                )

        if PLAYGROUND_SERIES_ID not in local_series:
            local_series[PLAYGROUND_SERIES_ID] = LibrarySeriesDTO(
                id=PLAYGROUND_SERIES_ID,
                title="Playground",
                videos=[],
                is_linked=False,
                source_url="",
            )

        return list(local_series.values())

    def get_video_source(self, series_id: str, video_id: str) -> VideoSourceDTO | None:
        """按 `(series_id, video_id)` 找到原始媒体文件并返回视频源 DTO。

        `video_id` 约定等于媒体文件名（不含扩展名）。当系列不存在、没有匹配
        文件或匹配到多个同名 stem 时返回 `None` / 抛 `ValueError`。

        Args:
            series_id: 所属系列 ID。
            video_id: 视频 ID（即媒体文件 stem）。

        Returns:
            含 source 路径、output_dir、`processed` 标记的 `VideoSourceDTO`；
            系列或视频不存在时返回 `None`。

        Raises:
            ValueError: 同一系列下出现重复的媒体 stem。
        """
        series_dir = self._videos_dir / series_id
        if not series_dir.exists() or not series_dir.is_dir():
            return None

        matches = [path for path in sorted(series_dir.iterdir()) if _is_media_file(path) and path.stem == video_id]
        if not matches:
            return None
        if len(matches) > 1:
            raise ValueError(f"Series '{series_id}' contains duplicate media stem '{video_id}'")

        video_path = matches[0]
        output_dir = self._workspace_dir / series_id / video_id
        return VideoSourceDTO(
            series_id=series_id,
            video_id=video_id,
            title=video_path.stem,
            source_name=video_path.name,
            source_type=_source_type_for_path(video_path),
            source_path=video_path,
            output_dir=output_dir,
            processed=(output_dir / "summary.json").exists(),
        )

    def get_video_summary(self, series_id: str, video_id: str) -> VideoSummaryDTO | None:
        """读取视频总结 JSON 并把对应章节的转写片段附加到 chapters 上。

        Args:
            series_id: 所属系列 ID。
            video_id: 视频 ID。

        Returns:
            含完整 summary（含 `transcript_segments`）的 `VideoSummaryDTO`；
            视频不存在或 `summary.json` 缺失时返回 `None`。
        """
        video = self.get_video_source(series_id, video_id)
        if video is None:
            return None

        summary_path = self._workspace_dir / series_id / video_id / "summary.json"
        if not summary_path.exists():
            return None

        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        transcript = _load_transcript_segments(self._workspace_dir / series_id / video_id / "transcript.cleaned.json")
        summary = _attach_chapter_transcript(summary, transcript)
        title = str(summary.get("title", video.title)).strip() or video.title
        return VideoSummaryDTO(
            series_id=series_id,
            video_id=video_id,
            title=title,
            summary=summary,
        )

    def get_series_catalog(self, series_id: str) -> dict[str, object] | None:
        """读取系列目录（Agent 知识记忆用）并按 `SeriesCatalogPayload` 校验。

        Args:
            series_id: 目标系列 ID。

        Returns:
            通过 Pydantic 校验后 `model_dump` 得到的 dict；文件不存在时返回 `None`。
        """
        payload_path = self._workspace_dir / series_id / SERIES_CATALOG_FILE
        if not payload_path.exists():
            return None
        payload = json.loads(payload_path.read_text(encoding="utf-8"))
        return SeriesCatalogPayload.model_validate(payload).model_dump(mode="json")

    def save_series_catalog(self, series_id: str, payload: dict[str, object]) -> None:
        """校验 + 序列化 + 原子写系列目录 payload（自动创建 series 目录）。

        Args:
            series_id: 目标系列 ID。
            payload: 任意可被 `SeriesCatalogPayload` 校验的字典。
        """
        normalized = SeriesCatalogPayload.model_validate(payload).model_dump(mode="json")
        output_dir = self._workspace_dir / series_id
        output_dir.mkdir(parents=True, exist_ok=True)
        atomic_write_text(
            output_dir / SERIES_CATALOG_FILE,
            json.dumps(normalized, ensure_ascii=False, indent=2),
        )

    def get_video_transcript(self, series_id: str, video_id: str) -> VideoTranscriptDTO | None:
        """读取 `transcript.cleaned.json` 并反序列化为转写 DTO。

        Args:
            series_id: 所属系列 ID。
            video_id: 视频 ID。

        Returns:
            含 `segments` / `duration_seconds` 等字段的 `VideoTranscriptDTO`；
            视频不存在或文件缺失时返回 `None`。
        """
        video = self.get_video_source(series_id, video_id)
        if video is None:
            return None

        transcript_path = self._workspace_dir / series_id / video_id / "transcript.cleaned.json"
        if not transcript_path.exists():
            return None

        payload = json.loads(transcript_path.read_text(encoding="utf-8"))
        title = str(payload.get("title", video.title)).strip() or video.title
        return VideoTranscriptDTO(
            series_id=series_id,
            video_id=video_id,
            title=title,
            duration_seconds=_as_seconds(payload.get("duration_seconds")),
            segments=[
                TranscriptSegmentDTO(
                    start_seconds=segment["start_seconds"],
                    end_seconds=segment["end_seconds"],
                    text=segment["text"],
                )
                for segment in _normalize_transcript_segments(payload.get("segments"))
            ],
        )

    def get_video_mindmap(self, series_id: str, video_id: str) -> VideoMindmapDTO | None:
        """读取 `mindmap.json` 并以总结标题（缺失时退回视频标题）组装 DTO。

        Args:
            series_id: 所属系列 ID。
            video_id: 视频 ID。

        Returns:
            思维导图 DTO；视频不存在或 `mindmap.json` 缺失时返回 `None`。
        """
        video = self.get_video_source(series_id, video_id)
        if video is None:
            return None

        mindmap_path = self._get_video_output_dir(series_id, video_id) / "mindmap.json"
        if not mindmap_path.exists():
            return None

        summary = self.get_video_summary(series_id, video_id)
        title = summary.title if summary is not None else video.title
        return VideoMindmapDTO(
            series_id=series_id,
            video_id=video_id,
            title=title,
            mindmap=json.loads(mindmap_path.read_text(encoding="utf-8")),
        )

    def get_video_chapter_cards(self, series_id: str, video_id: str) -> VideoChapterCardsDTO | None:
        """从视频总结中提取章节卡 + 关键结论卡，统一包装为章节卡列表。

        Args:
            series_id: 所属系列 ID。
            video_id: 视频 ID。

        Returns:
            含章节与关键结论卡片的 DTO；视频总结缺失时返回 `None`。
        """
        summary = self.get_video_summary(series_id, video_id)
        if summary is None:
            return None

        return VideoChapterCardsDTO(
            series_id=series_id,
            video_id=video_id,
            title=summary.title,
            cards=_build_chapter_cards(summary.summary),
        )

    def get_video_knowledge_cards(self, series_id: str, video_id: str) -> VideoKnowledgeCardsDTO | None:
        """读取 `knowledge_cards.json` 并把每条卡片解析为 `KnowledgeCardDTO`。

        Args:
            series_id: 所属系列 ID。
            video_id: 视频 ID。

        Returns:
            含 `cards` 列表的知识卡 DTO；视频不存在或文件缺失时返回 `None`。
        """
        video = self.get_video_source(series_id, video_id)
        if video is None:
            return None

        knowledge_cards_path = self._get_video_output_dir(series_id, video_id) / "knowledge_cards.json"
        if not knowledge_cards_path.exists():
            return None

        payload = json.loads(knowledge_cards_path.read_text(encoding="utf-8"))
        cards = payload.get("cards", [])
        if not isinstance(cards, list):
            raise ValueError("knowledge_cards.json 格式错误：cards 必须是数组。")

        return VideoKnowledgeCardsDTO(
            series_id=series_id,
            video_id=video_id,
            title=str(payload.get("title", video.title)).strip() or video.title,
            cards=[_to_knowledge_card_view(card) for card in cards],
        )

    def save_video_knowledge_cards(
        self,
        series_id: str,
        video_id: str,
        *,
        title: str,
        cards: list[KnowledgeCardDTO],
    ) -> None:
        """把知识卡列表原子写为 `knowledge_cards.json`（自动创建 output 目录）。

        Args:
            series_id: 所属系列 ID。
            video_id: 视频 ID。
            title: 卡片所属的"视频级"标题。
            cards: 待写入的 `KnowledgeCardDTO` 列表。
        """
        cards_payload = {
            "title": title,
            "cards": [_serialize_knowledge_card(card) for card in cards],
        }
        output_dir = self._get_video_output_dir(series_id, video_id)
        output_dir.mkdir(parents=True, exist_ok=True)
        atomic_write_text(
            output_dir / "knowledge_cards.json",
            json.dumps(cards_payload, ensure_ascii=False, indent=2),
        )

    def get_video_notes(self, series_id: str, video_id: str) -> VideoNotesDTO | None:
        """读取 `notes.json` 并以视频标题为标题包装为 DTO。

        Args:
            series_id: 所属系列 ID。
            video_id: 视频 ID。

        Returns:
            含全部笔记的 `VideoNotesDTO`；视频不存在时返回 `None`。
        """
        video = self.get_video_source(series_id, video_id)
        if video is None:
            return None

        notes_payload = self._read_notes_payload(series_id, video_id)
        return VideoNotesDTO(
            series_id=series_id,
            video_id=video_id,
            title=video.title,
            notes=[
                _to_note_view(note)
                for note in notes_payload["notes"]
            ],
        )

    def create_video_note(
        self,
        series_id: str,
        video_id: str,
        *,
        title: str,
        content: str,
        source: str,
    ) -> VideoNoteDTO | None:
        """在指定视频下追加一条笔记，全程在 `KeyedLockManager` 保护下完成。

        笔记 ID 形如 `note-<uuid4 hex>`，创建/更新时间均以 UTC ISO 字符串记录。

        Args:
            series_id: 所属系列 ID。
            video_id: 视频 ID。
            title: 笔记标题（不能为空）。
            content: 笔记正文（不能为空）。
            source: 笔记来源（仅允许 `manual` / `agent`）。

        Returns:
            新建后的 `VideoNoteDTO`；视频不存在时返回 `None`。
        """
        if self.get_video_source(series_id, video_id) is None:
            return None

        next_title = _require_note_text(title, "title")
        next_content = _require_note_text(content, "content")
        next_source = _require_note_source(source)
        now = _now_iso()
        note_record = {
            "id": f"note-{uuid4().hex}",
            "title": next_title,
            "content": next_content,
            "source": next_source,
            "created_at": now,
            "updated_at": now,
        }
        with self._notes_locks.hold(_notes_lock_key(series_id, video_id)):
            notes_payload = self._read_notes_payload(series_id, video_id)
            notes_payload["notes"].append(note_record)
            self._write_notes_payload(series_id, video_id, notes_payload)
        return _to_note_view(note_record)

    def update_video_note(
        self,
        series_id: str,
        video_id: str,
        note_id: str,
        *,
        title: str,
        content: str,
    ) -> VideoNoteDTO | None:
        """按 `note_id` 原地更新笔记的标题/正文并刷新 `updated_at` 字段。

        Args:
            series_id: 所属系列 ID。
            video_id: 视频 ID。
            note_id: 目标笔记 ID。
            title: 新标题（不能为空）。
            content: 新正文（不能为空）。

        Returns:
            更新后的 `VideoNoteDTO`；视频不存在返回 `None`，未找到 `note_id` 时
            同样返回 `None`。
        """
        if self.get_video_source(series_id, video_id) is None:
            return None

        next_title = _require_note_text(title, "title")
        next_content = _require_note_text(content, "content")
        with self._notes_locks.hold(_notes_lock_key(series_id, video_id)):
            notes_payload = self._read_notes_payload(series_id, video_id)
            for note in notes_payload["notes"]:
                if note["id"] != note_id:
                    continue
                note["title"] = next_title
                note["content"] = next_content
                note["updated_at"] = _now_iso()
                self._write_notes_payload(series_id, video_id, notes_payload)
                return _to_note_view(note)
        return None

    def delete_video_note(self, series_id: str, video_id: str, note_id: str) -> bool | None:
        """按 `note_id` 从 `notes.json` 中删除该笔记。

        Args:
            series_id: 所属系列 ID。
            video_id: 视频 ID。
            note_id: 目标笔记 ID。

        Returns:
            - `True` 删除成功；
            - `False` 未找到 `note_id`（视频存在但笔记已被删）；
            - `None` 视频本身不存在。
        """
        if self.get_video_source(series_id, video_id) is None:
            return None

        with self._notes_locks.hold(_notes_lock_key(series_id, video_id)):
            notes_payload = self._read_notes_payload(series_id, video_id)
            remaining_notes = [note for note in notes_payload["notes"] if note["id"] != note_id]
            if len(remaining_notes) == len(notes_payload["notes"]):
                return False

            self._write_notes_payload(series_id, video_id, {"notes": remaining_notes})
        return True

    def get_video_workspace_tools(self, series_id: str, video_id: str) -> VideoWorkspaceToolsDTO | None:
        """汇总视频工作区侧栏五个工具的"是否可用 / 是否已生成 / 当前状态"。

        状态机：
            - 概览（AI概况）依赖 `summary.json` 存在；
            - 知识卡、思维导图需"先有概览"才能解锁（`available`），
              再各自检查对应制品是否存在（`generated` + `ready`）；
            - 笔记与预览始终可用。

        Args:
            series_id: 所属系列 ID。
            video_id: 视频 ID。

        Returns:
            含五个工具 + AI 提示语的 DTO；视频不存在时返回 `None`。
        """
        video = self.get_video_source(series_id, video_id)
        if video is None:
            return None

        summary_exists = (video.output_dir / "summary.json").exists()
        knowledge_cards_exists = (video.output_dir / "knowledge_cards.json").exists()
        mindmap_exists = (video.output_dir / "mindmap.json").exists()
        preview_url = f"/api/videos/{series_id}/{video_id}/preview"
        preview_title = "音频预览" if video.source_type == "audio" else "视频预览"
        return VideoWorkspaceToolsDTO(
            series_id=series_id,
            video_id=video_id,
            overview=WorkspaceToolDTO(
                id="overview",
                title="AI概况",
                available=True,
                generated=summary_exists,
                status="ready" if summary_exists else "pending",
            ),
            knowledge_cards=WorkspaceToolDTO(
                id="knowledge-cards",
                title="知识卡片",
                available=summary_exists,
                generated=knowledge_cards_exists,
                status="ready" if knowledge_cards_exists else ("available" if summary_exists else "blocked"),
            ),
            mindmap=WorkspaceToolDTO(
                id="mindmap",
                title="思维导图",
                available=summary_exists,
                generated=mindmap_exists,
                status="ready" if mindmap_exists else ("available" if summary_exists else "blocked"),
            ),
            notes=WorkspaceToolDTO(
                id="notes",
                title="笔记",
                available=True,
                generated=True,
                status="ready",
            ),
            preview=WorkspaceToolDTO(
                id="preview",
                title=preview_title,
                available=True,
                generated=True,
                status="ready",
                preview_url=preview_url,
            ),
            ai_todo="当前已支持 AI 切换概况、知识卡片、笔记和媒体预览，并可定位时间点或整理笔记。",
        )

    def import_local_series(self, *, title: str, files: list[tuple[str, object]]) -> LibrarySeriesDTO:
        """在 `videos/<series_id>/` 下创建新系列目录并把所有媒体复制进去。

        关键步骤：
            1. 规范化 `title` 得到 `series_id`；命中 `PLAYGROUND_SERIES_ID` 时
               抛错，提示走"添加 Playground 媒体"入口；
            2. 若目标系列目录或 `linked_series.json` 已存在则抛错；
            3. `mkdir(parents=True, exist_ok=False)` 创建目录后写入
               `series_meta.json` 并复制媒体流；
            4. 任意步骤失败时回滚：删除新建目录与残留元数据文件并重抛异常。

        Args:
            title: 用户填写的系列标题（用于生成 `series_id` 与 `series_meta`）。
            files: `[(filename, file_like), ...]` 形式的待复制媒体。

        Returns:
            创建成功的 `LibrarySeriesDTO`。

        Raises:
            ValueError: 标题为空/不合法、命名空间冲突或媒体重复。
        """
        series_id = _normalize_series_id(title)
        if series_id == PLAYGROUND_SERIES_ID:
            raise ValueError("Playground 请使用单独的“添加 Playground 媒体”入口。")
        series_dir = self._videos_dir / series_id
        linked_meta_path = self._workspace_dir / series_id / LINKED_SERIES_META_FILE
        if series_dir.exists() or linked_meta_path.exists():
            raise ValueError(f"系列已存在：{series_id}")

        try:
            series_dir.mkdir(parents=True, exist_ok=False)
            self._write_series_title(series_id, title.strip())
            self._copy_video_streams(series_dir=series_dir, files=files)
            return LibrarySeriesDTO(
                id=series_id,
                title=title.strip(),
                videos=self._list_videos_for_series(series_dir),
            )
        except Exception:
            if series_dir.exists():
                shutil.rmtree(series_dir)
            meta_path = self._workspace_dir / series_id / SERIES_META_FILE
            if meta_path.exists():
                meta_path.unlink()
            raise

    def import_local_playground_videos(self, *, files: list[tuple[str, object]]) -> list[LibraryVideoCardDTO]:
        """把媒体导入到 Playground 系列（无独立 series_id 标题，不检查去重）。

        Args:
            files: `[(filename, file_like), ...]` 形式的待复制媒体。

        Returns:
            新增到 Playground 系列下的视频卡片列表。
        """
        series_dir = self._videos_dir / PLAYGROUND_SERIES_ID
        series_dir.mkdir(parents=True, exist_ok=True)
        imported_paths = self._copy_video_streams(series_dir=series_dir, files=files)
        return [self._build_local_video_card(PLAYGROUND_SERIES_ID, path) for path in imported_paths]

    def import_local_series_videos(self, *, series_id: str, files: list[tuple[str, object]]) -> list[LibraryVideoCardDTO]:
        """把媒体追加到既有本地系列；Playground 系列则转交 playground 入口。

        Args:
            series_id: 目标系列 ID。
            files: `[(filename, file_like), ...]` 形式的待复制媒体。

        Returns:
            新增的视频卡片列表。

        Raises:
            ValueError: 系列不存在或导入文件名与现有媒体冲突。
        """
        if series_id == PLAYGROUND_SERIES_ID:
            return self.import_local_playground_videos(files=files)
        if not self._series_exists(series_id):
            raise ValueError(f"系列不存在：{series_id}")
        series_dir = self._videos_dir / series_id
        series_dir.mkdir(parents=True, exist_ok=True)
        imported_paths = self._copy_video_streams(series_dir=series_dir, files=files)
        return [self._build_local_video_card(series_id, path) for path in imported_paths]

    def _list_videos_for_series(self, series_dir: Path) -> list[LibraryVideoCardDTO]:
        """把系列目录下的所有媒体文件包装为本地视频卡片；同 stem 重复则抛错。"""
        videos = [path for path in sorted(series_dir.iterdir()) if _is_media_file(path)]
        stems = [path.stem for path in videos]
        duplicate_stems = sorted({stem for stem in stems if stems.count(stem) > 1})
        if duplicate_stems:
            raise ValueError(
                f"Series '{series_dir.name}' contains duplicate media stems: {', '.join(duplicate_stems)}"
            )

        return [self._build_local_video_card(series_dir.name, video_path) for video_path in videos]

    def _list_videos_for_linked_series(
        self,
        *,
        series_id: str,
        linked_meta: dict[str, object],
        local_video_dir: Path,
    ) -> list[LibraryVideoCardDTO]:
        """把 `linked_series.json` 中的视频逐条解析为卡片，本地已下载则合并。

        关键规则：
            - `bvid` + `page=1` 组成 `video_id`，多 page 时拼接 `_p<page>`；
            - 若 `videos/<series_id>/<video_id>.<ext>` 已存在，本地副本覆盖
              元数据中的标题/封面/状态；
            - 元数据中存在的条目而本地没有的，按"linked 但未下载"展示。

        Args:
            series_id: 所属系列 ID。
            linked_meta: `linked_series.json` 解析后的字典。
            local_video_dir: `videos/<series_id>/` 路径。

        Returns:
            合并后的视频卡片列表（linked + 本地额外视频）。
        """
        cards: list[LibraryVideoCardDTO] = []
        consumed_video_ids: set[str] = set()
        local_paths_by_stem = {
            path.stem: path
            for path in sorted(local_video_dir.iterdir())
            if local_video_dir.exists() and _is_media_file(path)
        } if local_video_dir.exists() else {}

        videos = linked_meta.get("videos", [])
        if not isinstance(videos, list):
            raise ValueError("linked_series.json 格式错误：videos 必须是数组。")
        for item in videos:
            if not isinstance(item, dict):
                raise ValueError("linked_series.json 格式错误：video 必须是对象。")
            bvid = _require_text(item.get("bvid"), "linked_video.bvid")
            page = _as_positive_int(item.get("page"), 1)
            video_id = bvid if page == 1 else f"{bvid}_p{page}"
            consumed_video_ids.add(video_id)
            local_file = local_paths_by_stem.get(video_id)
            if local_file is not None:
                cards.append(
                    LibraryVideoCardDTO(
                        id=video_id,
                        title=str(item.get("title", video_id)).strip() or video_id,
                        source_name=local_file.name,
                        source_type=_source_type_for_path(local_file),
                        processed=(self._workspace_dir / series_id / video_id / "summary.json").exists(),
                        status="ready" if (self._workspace_dir / series_id / video_id / "summary.json").exists() else "pending",
                        is_linked=False,
                        bilibili_bvid=bvid,
                        bilibili_page=page,
                        source_url=str(item.get("source_url", "")),
                        provider=str(item.get("provider", "bilibili")).strip() or "bilibili",
                    )
                )
                continue
            cards.append(
                LibraryVideoCardDTO(
                    id=video_id,
                    title=str(item.get("title", video_id)).strip() or video_id,
                    source_name=f"{video_id}.mp4",
                    source_type="video",
                    processed=False,
                    status="linked",
                    is_linked=True,
                    bilibili_bvid=bvid,
                    bilibili_page=page,
                    source_url=str(item.get("source_url", "")),
                    provider=str(item.get("provider", "bilibili")).strip() or "bilibili",
                )
            )

        for video_id, local_path in local_paths_by_stem.items():
            if video_id not in consumed_video_ids:
                cards.append(self._build_local_video_card(series_id, local_path))
        return cards

    def _build_local_video_card(self, series_id: str, video_path: Path) -> LibraryVideoCardDTO:
        """按媒体文件路径构造本地视频卡片，状态以 `summary.json` 是否存在为判据。"""
        processed = (self._workspace_dir / series_id / video_path.stem / "summary.json").exists()
        return LibraryVideoCardDTO(
            id=video_path.stem,
            title=video_path.stem,
            source_name=video_path.name,
            source_type=_source_type_for_path(video_path),
            processed=processed,
            status="ready" if processed else "pending",
        )

    def _copy_video_streams(self, *, series_dir: Path, files: list[tuple[str, object]]) -> list[Path]:
        """把 `[(filename, stream), ...]` 复制到目标系列目录中。

        校验与处理：
            - 文件名 / 扩展名校验在 `_normalize_import_files` 内完成；
            - 同批次内 stem 重复 / 与既有媒体冲突立即抛错；
            - 复制前 `stream.seek(0)`，保证 `shutil.copyfileobj` 从头开始读。

        Args:
            series_dir: 目标系列目录。
            files: 规范化前的 `[(filename, stream), ...]`。

        Returns:
            成功写入的 `Path` 列表（按入参顺序）。
        """
        normalized_files = _normalize_import_files(files)
        existing_stems = {path.stem for path in series_dir.iterdir() if _is_media_file(path)} if series_dir.exists() else set()
        incoming_stems = [Path(filename).stem for filename, _ in normalized_files]
        duplicate_stems = sorted({stem for stem in incoming_stems if incoming_stems.count(stem) > 1})
        if duplicate_stems:
            raise ValueError(f"导入文件存在重复媒体名：{', '.join(duplicate_stems)}")
        conflicting_stems = sorted(existing_stems.intersection(incoming_stems))
        if conflicting_stems:
            raise ValueError(f"目标目录中已存在同名媒体：{', '.join(conflicting_stems)}")

        copied_paths: list[Path] = []
        for filename, stream in normalized_files:
            target_path = series_dir / filename
            if target_path.exists():
                raise ValueError(f"目标目录中已存在文件：{filename}")
            if hasattr(stream, "seek"):
                stream.seek(0)
            with target_path.open("wb") as handle:
                shutil.copyfileobj(stream, handle)
            copied_paths.append(target_path)
        return copied_paths

    def save_linked_series(self, series: LinkedSeries) -> None:
        """把 linked 系列（含其视频列表）原子写为 `linked_series.json`。"""
        payload = {
            "title": series.title,
            "cover_url": series.cover_url,
            "source_url": series.source_url,
            "videos": [
                {
                    "bvid": video.bvid,
                    "page": video.page,
                    "title": video.title,
                    "cover_url": video.cover_url,
                    "duration_seconds": video.duration_seconds,
                    "source_url": video.source_url,
                    "provider": video.provider,
                    "download_key": video.download_key,
                }
                for video in series.videos
            ],
        }
        atomic_write_text(
            self._workspace_dir / series.series_id / LINKED_SERIES_META_FILE,
            json.dumps(payload, ensure_ascii=False, indent=2),
        )

    def get_linked_series(self, series_id: str) -> LinkedSeries | None:
        """读取 `linked_series.json` 并把每条视频反序列化为 `LinkedVideo`。

        Args:
            series_id: 目标系列 ID。

        Returns:
            解析后的 `LinkedSeries`；文件不存在时返回 `None`。

        Raises:
            ValueError: JSON 结构不符合预期（videos 不是数组 / 条目不是对象）。
        """
        meta_path = self._workspace_dir / series_id / LINKED_SERIES_META_FILE
        if not meta_path.exists():
            return None
        payload = json.loads(meta_path.read_text(encoding="utf-8"))
        videos = payload.get("videos", [])
        if not isinstance(videos, list):
            raise ValueError("linked_series.json 格式错误：videos 必须是数组。")
        return LinkedSeries(
            series_id=series_id,
            title=str(payload.get("title", _to_title(series_id))).strip() or _to_title(series_id),
            cover_url=str(payload.get("cover_url", "")),
            source_url=str(payload.get("source_url", "")),
            videos=[
                LinkedVideo(
                    bvid=_require_text(item.get("bvid"), "linked_video.bvid"),
                    page=_as_positive_int(item.get("page"), 1),
                    title=str(item.get("title", "")).strip() or _require_text(item.get("bvid"), "linked_video.bvid"),
                    cover_url=str(item.get("cover_url", "")),
                    duration_seconds=_as_positive_int(item.get("duration_seconds"), 0),
                    source_url=str(item.get("source_url", "")),
                    provider=str(item.get("provider", "bilibili")).strip() or "bilibili",
                    download_key=str(item.get("download_key", "")).strip(),
                )
                for item in videos
                if isinstance(item, dict)
            ],
        )

    def delete_linked_series(self, series_id: str) -> bool:
        """删除 `linked_series.json`（不动其他目录），文件不存在则返回 `False`。"""
        meta_path = self._workspace_dir / series_id / LINKED_SERIES_META_FILE
        if not meta_path.exists():
            return False
        meta_path.unlink()
        return True

    def delete_series(self, series_id: str) -> bool:
        """整系列删除：`videos/<series_id>/` 与 `workspace/<series_id>/` 一并清空。

        Playground 系列因无独立元数据不允许整批删除。

        Args:
            series_id: 目标系列 ID。

        Returns:
            是否有任意路径被删除（`videos/` 或 `workspace/` 存在即视为成功）。

        Raises:
            ValueError: 尝试删除 Playground 系列。
        """
        if series_id == PLAYGROUND_SERIES_ID:
            raise ValueError("Playground 不能整体删除，请按视频删除。")

        removed = False
        local_dir = self._videos_dir / series_id
        workspace_dir = self._workspace_dir / series_id

        if local_dir.exists():
            shutil.rmtree(local_dir)
            removed = True

        if workspace_dir.exists():
            shutil.rmtree(workspace_dir)
            removed = True

        return removed

    def delete_video(self, series_id: str, video_id: str) -> bool:
        """删除单个视频：清掉原始媒体、制品目录；必要时回写 linked 元数据。

        Args:
            series_id: 所属系列 ID。
            video_id: 视频 ID。

        Returns:
            是否有任意文件被删除（媒体 / 制品 / linked 元数据）。
        """
        removed = False
        local_dir = self._videos_dir / series_id
        if local_dir.exists():
            matches = [path for path in local_dir.iterdir() if _is_media_file(path) and path.stem == video_id]
            for match in matches:
                match.unlink()
                removed = True

        output_dir = self._workspace_dir / series_id / video_id
        if output_dir.exists():
            shutil.rmtree(output_dir)
            removed = True

        linked_series = self.get_linked_series(series_id)
        if linked_series is not None:
            remaining_videos = [video for video in linked_series.videos if video.video_id != video_id]
            if len(remaining_videos) != len(linked_series.videos):
                self.save_linked_series(
                    LinkedSeries(
                        series_id=linked_series.series_id,
                        title=linked_series.title,
                        cover_url=linked_series.cover_url,
                        source_url=linked_series.source_url,
                        videos=remaining_videos,
                    )
                )
                removed = True

        return removed

    def _series_exists(self, series_id: str) -> bool:
        """判断系列是否存在于 `videos/` 或 `workspace/` 任一目录。"""
        return (self._videos_dir / series_id).exists() or (self._workspace_dir / series_id).exists()

    def _read_series_title(self, series_id: str) -> str | None:
        """从 `series_meta.json` 读取系列标题；文件不存在或 title 为空时返回 `None`。"""
        meta_path = self._workspace_dir / series_id / SERIES_META_FILE
        if not meta_path.exists():
            return None
        payload = json.loads(meta_path.read_text(encoding="utf-8"))
        title = payload.get("title")
        if not isinstance(title, str) or not title.strip():
            return None
        return title.strip()

    def _write_series_title(self, series_id: str, title: str) -> None:
        """把系列标题原子写为 `series_meta.json`，按需创建 series 目录。"""
        output_dir = self._workspace_dir / series_id
        output_dir.mkdir(parents=True, exist_ok=True)
        atomic_write_text(
            output_dir / SERIES_META_FILE,
            json.dumps({"title": title}, ensure_ascii=False, indent=2),
        )

    def _get_video_output_dir(self, series_id: str, video_id: str) -> Path:
        """返回 `workspace/<series_id>/<video_id>/`（不保证目录已存在）。"""
        return self._workspace_dir / series_id / video_id

    def _read_notes_payload(self, series_id: str, video_id: str) -> dict[str, list[dict[str, str]]]:
        """读取并校验 `notes.json`；文件不存在返回 `{"notes": []}`，格式错误抛 `ValueError`。"""
        notes_path = self._get_video_output_dir(series_id, video_id) / "notes.json"
        if not notes_path.exists():
            return {"notes": []}

        payload = json.loads(notes_path.read_text(encoding="utf-8"))
        notes = payload.get("notes", [])
        if not isinstance(notes, list):
            raise ValueError("notes.json 格式错误：notes 必须是数组。")

        normalized_notes = []
        for note in notes:
            if not isinstance(note, dict):
                raise ValueError("notes.json 格式错误：note 必须是对象。")
            normalized_notes.append(
                {
                    "id": _require_note_text(note.get("id"), "id"),
                    "title": _require_note_text(note.get("title"), "title"),
                    "content": _require_note_text(note.get("content"), "content"),
                    "source": _require_note_source(note.get("source")),
                    "created_at": _require_note_text(note.get("created_at"), "created_at"),
                    "updated_at": _require_note_text(note.get("updated_at"), "updated_at"),
                }
            )
        return {"notes": normalized_notes}

    def _write_notes_payload(self, series_id: str, video_id: str, payload: dict[str, list[dict[str, str]]]) -> None:
        """把笔记 payload 原子写为 `notes.json`，按需创建 output 目录。"""
        output_dir = self._get_video_output_dir(series_id, video_id)
        output_dir.mkdir(parents=True, exist_ok=True)
        atomic_write_text(
            output_dir / "notes.json",
            json.dumps(payload, ensure_ascii=False, indent=2),
        )


def _is_media_file(path: Path) -> bool:
    """判断路径是否指向一个支持的媒体文件（白名单后缀 + is_file）。"""
    return path.is_file() and path.suffix.lower() in MEDIA_SUFFIXES


def _notes_lock_key(series_id: str, video_id: str) -> str:
    """构造 `KeyedLockManager` 用的笔记锁 key：`{series_id}/{video_id}`。"""
    return f"{series_id}/{video_id}"


def _normalize_series_id(value: str) -> str:
    """把用户输入的系列标题规范化为合法的 `series_id`。

    校验规则：
        - 去除两端空白，且不能为空；
        - 拒绝相对路径符号 `.` / `..`、路径分隔符、`<>:"/\\|?*`、末尾
          空格/句点；
        - 拒绝 Windows 系统保留名（`CON/PRN/AUX/NUL/COMx/LPTx`）。

    Args:
        value: 用户输入的系列标题。

    Returns:
        去除两端空白的字符串。

    Raises:
        ValueError: 违反任一规则时。
    """
    normalized = value.strip()
    if not normalized:
        raise ValueError("系列名称不能为空。")
    if normalized in {".", ".."}:
        raise ValueError("系列名称不合法。")
    if any(char in normalized for char in '<>:"/\\|?*'):
        raise ValueError('系列名称不能包含 <>:"/\\\\|?* 这些字符。')
    if normalized.endswith(" ") or normalized.endswith("."):
        raise ValueError("系列名称不能以空格或句点结尾。")
    reserved = {
        "con", "prn", "aux", "nul",
        *(f"com{index}" for index in range(1, 10)),
        *(f"lpt{index}" for index in range(1, 10)),
    }
    if normalized.lower() in reserved:
        raise ValueError("系列名称不能使用系统保留字。")
    return normalized


def _normalize_import_files(files: list[tuple[str, object]]) -> list[tuple[str, object]]:
    """对导入文件做最少一项目 / 文件名 / 扩展名校验。

    Args:
        files: `[(filename, stream), ...]`，`stream` 一般为 FastAPI `UploadFile`。

    Returns:
        过滤后的 `[(filename, stream), ...]`，`filename` 仅保留 `Path.name`。

    Raises:
        ValueError: 列表为空、文件名缺失或扩展名不在 `MEDIA_SUFFIXES` 中。
    """
    if not files:
        raise ValueError("至少选择一个媒体文件。")
    normalized: list[tuple[str, object]] = []
    for filename, stream in files:
        path = Path(filename or "")
        if not path.name:
            raise ValueError("存在缺少文件名的导入项。")
        if not _is_media_suffix(path.suffix):
            raise ValueError(f"不支持的媒体格式：{path.name}")
        normalized.append((path.name, stream))
    return normalized


def _is_media_suffix(suffix: str) -> bool:
    """判断扩展名（大小写不敏感）是否在受支持的媒体白名单中。"""
    return suffix.lower() in MEDIA_SUFFIXES


def _source_type_for_path(path: Path) -> str:
    """按文件扩展名把媒体分类为 `audio` / `video`，用于 `VideoSourceDTO.source_type`。"""
    if path.suffix.lower() in AUDIO_SUFFIXES:
        return "audio"
    return "video"


def _to_title(raw_value: str) -> str:
    """把 series_id / workspace_id 这类下划线/连字符命名转成人类可读标题。"""
    return raw_value.replace("_", " ").replace("-", " ").title()


def _load_transcript_segments(transcript_path: Path) -> list[dict[str, object]]:
    """从 `transcript.cleaned.json` 读出 segments（文件缺失时返回空列表）。"""
    if not transcript_path.exists():
        return []

    payload = json.loads(transcript_path.read_text(encoding="utf-8"))
    return _normalize_transcript_segments(payload.get("segments"))


def _normalize_transcript_segments(value: object) -> list[dict[str, object]]:
    """把转写 segments 规范化为 `{start_seconds, end_seconds, text}` 字典列表。

    过滤规则：跳过非字典条目、缺起止时间或文本为空的 segment；最终 `text` 会
    去除两端空白。
    """
    if not isinstance(value, list):
        return []

    normalized_segments: list[dict[str, object]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        start_seconds = _as_seconds(item.get("start_seconds"))
        end_seconds = _as_seconds(item.get("end_seconds"))
        text = item.get("text")
        if start_seconds is None or end_seconds is None:
            continue
        if not isinstance(text, str) or not text.strip():
            continue
        normalized_segments.append(
            {
                "start_seconds": start_seconds,
                "end_seconds": end_seconds,
                "text": text.strip(),
            }
        )
    return normalized_segments


def _attach_chapter_transcript(summary: dict[str, object], transcript_segments: list[dict[str, object]]) -> dict[str, object]:
    """为 summary 中每个章节附加对应时间窗内的转写分片（不修改原 summary）。

    Args:
        summary: 视频总结的原始字典（含 `chapters` 字段）。
        transcript_segments: 全部转写 segments。

    Returns:
        新字典；`chapters` 字段中每条多了 `transcript_segments`。
    """
    chapters = summary.get("chapters", [])
    if not isinstance(chapters, list):
        return summary

    enriched_chapters = []
    for chapter in chapters:
        if not isinstance(chapter, dict):
            enriched_chapters.append(chapter)
            continue

        chapter_segments = _slice_transcript_segments(
            transcript_segments,
            _as_seconds(chapter.get("start_seconds")),
            _as_seconds(chapter.get("end_seconds")),
        )
        enriched_chapters.append(
            {
                **chapter,
                "transcript_segments": chapter_segments,
            }
        )

    return {
        **summary,
        "chapters": enriched_chapters,
    }


def _slice_transcript_segments(
    transcript_segments: list[dict[str, object]],
    start_seconds: float | None,
    end_seconds: float | None,
) -> list[dict[str, object]]:
    """按时间窗 `[start, end]` 切出与章节对齐的转写分片。

    Args:
        transcript_segments: 全部转写 segments。
        start_seconds: 章节起秒；为 `None` 时返回空列表。
        end_seconds: 章节止秒；为 `None` 时返回空列表。

    Returns:
        与章节时间区间有重叠的 segments（保持原顺序）。
    """
    if start_seconds is None or end_seconds is None:
        return []

    sliced_segments = []
    for segment in transcript_segments:
        segment_start = segment["start_seconds"]
        segment_end = segment["end_seconds"]
        segment_text = segment["text"]
        if segment_end < start_seconds or segment_start > end_seconds:
            continue

        sliced_segments.append(
            {
                "start_seconds": segment_start,
                "end_seconds": segment_end,
                "text": segment_text,
            }
        )

    return sliced_segments


def _as_seconds(value: object) -> float | None:
    """把任意值转成秒数（`int` / `float`），其他类型（含 `bool`）返回 `None`。"""
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _build_chapter_cards(summary: dict[str, object]) -> list[ChapterCardDTO]:
    """把 summary 里的 `chapters` + `key_takeaways` 展开为统一的章节卡列表。

    - 章节卡 `kind=chapter`；
    - 关键结论卡 `kind=takeaway`，id 形如 `takeaway-<n>`。

    过滤掉 id/title/summary 缺失或非字符串的章节；非字符串的要点被丢弃。
    """
    cards: list[ChapterCardDTO] = []

    chapters = summary.get("chapters", [])
    if isinstance(chapters, list):
        for chapter in chapters:
            if not isinstance(chapter, dict):
                continue
            chapter_id = chapter.get("id")
            title = chapter.get("title")
            chapter_summary = chapter.get("summary")
            if not isinstance(chapter_id, str) or not chapter_id.strip():
                continue
            if not isinstance(title, str) or not title.strip():
                continue
            if not isinstance(chapter_summary, str) or not chapter_summary.strip():
                continue
            key_points = chapter.get("key_points", [])
            cards.append(
                ChapterCardDTO(
                    id=chapter_id,
                    title=title.strip(),
                    summary=chapter_summary.strip(),
                    key_points=[
                        point.strip()
                        for point in key_points
                        if isinstance(point, str) and point.strip()
                    ],
                    start_seconds=_as_seconds(chapter.get("start_seconds")),
                    end_seconds=_as_seconds(chapter.get("end_seconds")),
                    kind="chapter",
                )
            )

    takeaways = summary.get("key_takeaways", [])
    if isinstance(takeaways, list):
        for index, takeaway in enumerate(takeaways, start=1):
            if not isinstance(takeaway, str) or not takeaway.strip():
                continue
            cards.append(
                ChapterCardDTO(
                    id=f"takeaway-{index}",
                    title=f"关键结论 {index}",
                    summary=takeaway.strip(),
                    key_points=[],
                    start_seconds=None,
                    end_seconds=None,
                    kind="takeaway",
                )
            )

    return cards


def _serialize_knowledge_card(card: KnowledgeCardDTO) -> dict[str, object]:
    """把 `KnowledgeCardDTO` 序列化为可被 `json.dumps` 持久化的字典（拷贝 list 字段）。"""
    return {
        "id": card.id,
        "title": card.title,
        "kind": card.kind,
        "summary": card.summary,
        "details": card.details,
        "tags": list(card.tags),
        "keywords": list(card.keywords),
        "related_card_ids": list(card.related_card_ids),
    }


def _to_knowledge_card_view(card_record: dict[str, object]) -> KnowledgeCardDTO:
    """把 `knowledge_cards.json` 中的一条 card 反序列化为 `KnowledgeCardDTO`。

    Raises:
        ValueError: 记录不是字典、必填字段为空或字段类型不合法。
    """
    if not isinstance(card_record, dict):
        raise ValueError("knowledge_cards.json 格式错误：card 必须是对象。")
    return KnowledgeCardDTO(
        id=_require_note_text(card_record.get("id"), "id"),
        title=_require_note_text(card_record.get("title"), "title"),
        kind=_require_knowledge_card_kind(card_record.get("kind")),
        summary=_require_note_text(card_record.get("summary"), "summary"),
        details=_require_note_text(card_record.get("details"), "details"),
        tags=_require_string_list(card_record.get("tags"), "tags"),
        keywords=_require_string_list(card_record.get("keywords"), "keywords"),
        related_card_ids=_require_string_list(card_record.get("related_card_ids"), "related_card_ids"),
    )


def _require_string_list(value: object, field_name: str) -> list[str]:
    """校验一个列表字段：必须为数组且每项是非空字符串。

    `value` 为 `None` 时返回空列表。
    """
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError(f"knowledge_cards.json 格式错误：{field_name} 必须是数组。")
    result: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise ValueError(f"knowledge_cards.json 格式错误：{field_name} 项必须是非空字符串。")
        result.append(item.strip())
    return result


def _require_knowledge_card_kind(value: object) -> str:
    """校验知识卡 `kind` 字段必须是允许的枚举值之一（`concept`/`method`/...）。"""
    allowed = {"concept", "method", "case", "term", "conclusion", "insight"}
    if not isinstance(value, str) or value not in allowed:
        raise ValueError(f"knowledge_cards.json 格式错误：kind 必须是 {', '.join(sorted(allowed))}。")
    return value


def _to_note_view(note_record: dict[str, str]) -> VideoNoteDTO:
    """把内存中的笔记字典构造为 `VideoNoteDTO`（字段必须齐全且非空）。"""
    return VideoNoteDTO(
        id=note_record["id"],
        title=note_record["title"],
        content=note_record["content"],
        source=note_record["source"],
        created_at=note_record["created_at"],
        updated_at=note_record["updated_at"],
    )


def _require_note_text(value: object, field_name: str) -> str:
    """校验笔记相关字段为非空字符串；为空时抛 `ValueError`，错误信息含 `note.` 前缀。"""
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"note.{field_name} 不能为空。")
    return value.strip()


def _require_text(value: object, field_name: str) -> str:
    """校验通用字段为非空字符串（与 `_require_note_text` 仅错误前缀不同）。"""
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} 不能为空。")
    return value.strip()


def _as_positive_int(value: object, default: int) -> int:
    """把任意值解析为非负整数；类型不匹配 / 负数 / `bool` 时回落到 `default`。

    `bool` 显式回落避免 `True` 被当作 `1` 这种误用。
    """
    if isinstance(value, bool):
        return default
    if isinstance(value, (int, float)) and value >= 0:
        return int(value)
    return default


def _require_note_source(value: object) -> str:
    """校验笔记 `source` 字段必须是 `manual` 或 `agent`。"""
    if value not in {"manual", "agent"}:
        raise ValueError("note.source 必须是 manual 或 agent。")
    return str(value)


def _now_iso() -> str:
    """返回当前 UTC 时间的 ISO-8601 字符串（`Z` 后缀，替代 `+00:00`）。"""
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
