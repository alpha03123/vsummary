"""Inspect and import a user-selected legacy Local directory."""

from __future__ import annotations

import hashlib
import json
import shutil
from copy import deepcopy
from pathlib import Path
from threading import Lock, Thread
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from backend.core.blob_store import BlobReference
from backend.core.ids import new_ulid
from backend.local.persistence.file_blob_store import FileBlobStore
from backend.local.persistence.legacy_workspace_importer import LegacyWorkspaceImporter
from backend.video_summary.infrastructure.persistence.models import LegacyImportItem, LegacyMigrationRun, MediaObject, Series
from backend.video_summary.library.constants import MEDIA_SUFFIXES


COPYABLE_DATA_DIRECTORIES = frozenset({"models", "bilibili", "youtube", "douyin", "chaoxing"})
REBUILDABLE_DATA_DIRECTORIES = frozenset({"downloads", "playwright-browsers", "agent_graph"})


class LegacyMigrationError(RuntimeError):
    pass


def select_legacy_directory() -> str | None:
    import tkinter as tk
    from tkinter import filedialog

    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    try:
        selected = filedialog.askdirectory(title="选择旧版 VSummary 目录", parent=root, mustexist=True)
    finally:
        root.destroy()
    return str(Path(selected).resolve()) if selected else None


def _looks_like_legacy_root(path: Path) -> bool:
    workspace = path / "workspace"
    videos = path / "videos"
    return (
        workspace.is_dir()
        and any((item / "series_meta.json").is_file() or (item / "linked_series.json").is_file() for item in workspace.iterdir() if item.is_dir())
    ) or (videos.is_dir() and any(item.is_dir() for item in videos.iterdir()))


def find_legacy_roots(selected: Path) -> list[Path]:
    selected = selected.expanduser().resolve()
    if not selected.is_dir():
        raise ValueError(f"旧版目录不存在：{selected}")
    if _looks_like_legacy_root(selected):
        return [selected]
    return sorted(path for path in selected.iterdir() if path.is_dir() and _looks_like_legacy_root(path))


def _directory_usage(path: Path) -> tuple[int, int]:
    count = size = 0
    for item in path.rglob("*"):
        if item.is_file():
            count += 1
            size += item.stat().st_size
    return count, size


def inspect_legacy_root(source_root: Path, blob_store: FileBlobStore, *, convert_hardlinks: bool = False) -> dict[str, Any]:
    source_root = source_root.expanduser().resolve()
    if not _looks_like_legacy_root(source_root):
        raise ValueError(f"未在目录中发现可迁移的旧版视频库：{source_root}")
    workspace = source_root / "workspace"
    videos = source_root / "videos"
    names = {path.name for path in videos.iterdir() if path.is_dir()} if videos.is_dir() else set()
    if workspace.is_dir():
        names.update(path.name for path in workspace.iterdir() if path.is_dir() and ((path / "series_meta.json").is_file() or (path / "linked_series.json").is_file()))
    series: list[dict[str, Any]] = []
    warnings: list[str] = []
    copy_bytes = 0
    artifact_bytes = 0
    for name in sorted(names):
        workspace_series = workspace / name
        meta = workspace_series / "series_meta.json"
        payload = json.loads(meta.read_text(encoding="utf-8")) if meta.is_file() else {}
        mode = payload.get("storage_mode", "copy")
        if mode not in {"copy", "hardlink", "external_reference"}:
            raise ValueError(f"系列 {name} 的存储方式无效：{mode}")
        media_dir = videos / name
        media = []
        if media_dir.is_dir():
            for path in sorted(media_dir.iterdir()):
                if path.is_file() and path.suffix.lower() in MEDIA_SUFFIXES:
                    media.append({"name": path.name, "bytes": path.stat().st_size, "state": "pending", "video_id": None})
        external = []
        if workspace_series.is_dir():
            for path in sorted(workspace_series.glob("*/source.json")):
                source = json.loads(path.read_text(encoding="utf-8")).get("source_path")
                if not isinstance(source, str) or not Path(source).is_absolute():
                    raise ValueError(f"外部媒体路径无效：{path}")
                external.append({"name": path.parent.name, "path": source, "exists": Path(source).is_file(), "state": "pending"})
                if not Path(source).is_file():
                    warnings.append(f"外部文件暂不可用：{name}/{path.parent.name}")
            artifact_bytes += sum(path.stat().st_size for pattern in ("*/screenshots/*.jpg", "*/frames/*.jpg") for path in workspace_series.glob(pattern) if path.is_file())
        effective_mode = mode
        if mode == "hardlink" and any(not blob_store.can_hardlink(media_dir / item["name"]) for item in media):
            if convert_hardlinks:
                effective_mode = "copy"
                warnings.append(f"系列 {name} 的硬链接将按用户选择转换为复制")
            else:
                warnings.append(f"系列 {name} 与目标 Blob 跨卷；需调整数据根目录或明确转换为复制")
        if effective_mode == "copy":
            copy_bytes += sum(item["bytes"] for item in media)
        series.append({"name": name, "mode": mode, "effective_mode": effective_mode, "linked": (workspace_series / "linked_series.json").is_file(), "media": media, "external": external})
    data_items = []
    data_root = source_root / "data"
    if data_root.is_dir():
        for path in sorted(data_root.iterdir()):
            if path.is_dir():
                count, size = _directory_usage(path)
                category = "copyable" if path.name in COPYABLE_DATA_DIRECTORIES else "rebuildable" if path.name in REBUILDABLE_DATA_DIRECTORIES else "sql" if path.name in {"agent_sessions", "usage"} else "unknown"
                data_items.append({"name": path.name, "files": count, "bytes": size, "category": category})
    fingerprint = hashlib.sha256(json.dumps({"source": str(source_root), "series": series, "data": data_items}, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()
    return {
        "source_root": str(source_root),
        "fingerprint": fingerprint,
        "found": {name: (source_root / name).is_dir() for name in ("data", "workspace", "videos")},
        "series": series,
        "data": data_items,
        "total_videos": sum(len(item["media"]) + len(item["external"]) for item in series),
        "copy_bytes": copy_bytes,
        "artifact_bytes": artifact_bytes,
        "target_free_bytes": shutil.disk_usage(_existing_ancestor(blob_store.root)).free,
        "warnings": warnings,
    }


class LegacyMigrationService:
    def __init__(self, *, session_factory: sessionmaker[Session], blob_store: FileBlobStore, installation_root: Path) -> None:
        self._sessions = session_factory
        self._blobs = blob_store
        self._installation_root = installation_root.resolve()
        self._lock = Lock()
        self._thread: Thread | None = None

    def inspect(self, selected: Path, *, convert_hardlinks: bool = False) -> dict[str, Any]:
        roots = find_legacy_roots(selected)
        if not roots:
            raise ValueError("所选目录或其直接子目录中没有旧版 VSummary 数据")
        if len(roots) > 1:
            return {"candidates": [str(path) for path in roots]}
        preview = inspect_legacy_root(roots[0], self._blobs, convert_hardlinks=convert_hardlinks)
        preview["installation_free_bytes"] = shutil.disk_usage(_existing_ancestor(self._installation_root)).free
        return preview

    def create_run(self, selected: Path, *, include_data: list[str], convert_hardlinks: bool = False) -> dict[str, Any]:
        preview = self.inspect(selected, convert_hardlinks=convert_hardlinks)
        if "candidates" in preview:
            raise ValueError("请选择一个明确的旧版 VSummary 根目录")
        invalid = set(include_data) - COPYABLE_DATA_DIRECTORIES
        if invalid:
            raise ValueError(f"不支持迁移的数据目录：{', '.join(sorted(invalid))}")
        if any(item["mode"] == "hardlink" and item["effective_mode"] != "hardlink" for item in preview["series"]) and not convert_hardlinks:
            raise ValueError("硬链接系列与目标 Blob 跨卷")
        if any("跨卷" in warning for warning in preview["warnings"]):
            raise ValueError("硬链接系列与目标 Blob 跨卷；需明确选择转换为复制")
        source_root = preview["source_root"]
        source_path = Path(source_root)
        blob_root = self._blobs.root.resolve()
        if self._installation_root != source_path and self._installation_root.is_relative_to(source_path):
            raise ValueError("新安装目录不能位于旧版来源目录内")
        if blob_root.is_relative_to(source_path):
            raise ValueError("目标 Blob 目录不能位于旧版来源目录内")
        blob_bytes = preview["copy_bytes"] + preview["artifact_bytes"]
        data_bytes = sum(item["bytes"] for item in preview["data"] if item["name"] in include_data)
        same_volume = _existing_ancestor(self._blobs.root).stat().st_dev == _existing_ancestor(self._installation_root).stat().st_dev
        if same_volume and blob_bytes + data_bytes > preview["target_free_bytes"]:
            raise ValueError("目标盘空间不足，请调整数据根目录或减少复制内容")
        if not same_volume and (blob_bytes > preview["target_free_bytes"] or data_bytes > preview["installation_free_bytes"]):
            raise ValueError("目标盘空间不足，请调整数据根目录或减少复制内容")
        with self._sessions.begin() as session:
            existing = session.scalar(select(LegacyMigrationRun).where(LegacyMigrationRun.source_root == source_root).order_by(LegacyMigrationRun.created_at.desc()))
            if existing is not None:
                if existing.status == "running":
                    raise ValueError("这个目录已有运行中的迁移")
                if existing.status != "completed" and existing.verified_videos == 0:
                    existing.manifest = preview
                    existing.include_data = include_data
                    existing.total_videos = preview["total_videos"]
                return self._summary(existing)
            run = LegacyMigrationRun(id=new_ulid(), source_root=source_root, manifest=preview, include_data=include_data, status="ready", total_videos=preview["total_videos"])
            session.add(run)
            session.flush()
            return self._summary(run)

    def start(self, run_id: str) -> dict[str, Any]:
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                raise ValueError("已有迁移任务正在执行")
            with self._sessions.begin() as session:
                run = session.get(LegacyMigrationRun, run_id, with_for_update=True)
                if run is None:
                    raise LookupError("迁移任务不存在")
                if run.status == "completed":
                    return self._summary(run)
                run.status = "running"
                run.error = None
                run.cancel_requested = False
                summary = self._summary(run)
            self._thread = Thread(target=self._run, args=(run_id,), daemon=True, name=f"legacy-migration-{run_id}")
            self._thread.start()
            return summary

    def cancel(self, run_id: str) -> dict[str, Any]:
        with self._sessions.begin() as session:
            run = session.get(LegacyMigrationRun, run_id, with_for_update=True)
            if run is None:
                raise LookupError("迁移任务不存在")
            if run.status == "running":
                run.cancel_requested = True
            return self._summary(run)

    def status(self, run_id: str) -> dict[str, Any]:
        with self._sessions() as session:
            run = session.get(LegacyMigrationRun, run_id)
            if run is None:
                raise LookupError("迁移任务不存在")
            summary = self._summary(run)
        if summary["status"] == "running" and (self._thread is None or not self._thread.is_alive()):
            with self._sessions.begin() as session:
                run = session.get(LegacyMigrationRun, run_id, with_for_update=True)
                if run.status == "running":
                    run.status = "interrupted"
                summary = self._summary(run)
        return summary

    def latest(self) -> dict[str, Any] | None:
        with self._sessions() as session:
            run = session.scalar(select(LegacyMigrationRun).order_by(LegacyMigrationRun.created_at.desc()))
        return self.status(run.id) if run is not None else None

    def is_active(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def _run(self, run_id: str) -> None:
        try:
            self._execute(run_id)
        except _MigrationCancelled:
            return
        except Exception as error:
            with self._sessions.begin() as session:
                run = session.get(LegacyMigrationRun, run_id, with_for_update=True)
                run.status = "failed"
                run.error = str(error)

    def _execute(self, run_id: str) -> None:
        with self._sessions() as session:
            run = session.get(LegacyMigrationRun, run_id)
            manifest = deepcopy(run.manifest)
            source_root = Path(run.source_root)
            include_data = list(run.include_data)
        importer = LegacyWorkspaceImporter(root_dir=source_root, session_factory=self._sessions, blob_store=self._blobs, source_namespace=run_id)
        workspace_id = importer._workspace_id()
        for position, item in enumerate(manifest["series"]):
            self._check_cancel(run_id)
            name = item["name"]
            workspace_series = source_root / "workspace" / name
            if item["linked"]:
                importer._import_linked_series(workspace_id, name, workspace_series / "linked_series.json")
            if not item["media"] and not item["external"]:
                continue
            series_id, _ = importer._series_id(workspace_id, source_root / "videos" / name, position, item["effective_mode"])
            for external in item["external"]:
                if external["state"] == "verified":
                    continue
                self._check_cancel(run_id)
                source_file = workspace_series / external["name"] / "source.json"
                video_id, _ = importer._external_video_id(series_id, name, source_file)
                importer._import_external_media(video_id, source_file)
                importer._import_video_records(workspace_id, series_id, video_id, name, external["name"])
                external["state"] = "verified"
                self._save_manifest(run_id, manifest)
            for media in item["media"]:
                self._check_cancel(run_id)
                source_path = source_root / "videos" / name / media["name"]
                if media["state"] == "source_removed":
                    self._verify_target(media["video_id"], media["bytes"])
                    continue
                if source_path.is_file():
                    video_id, _ = importer._video_id(series_id, name, source_path)
                    importer._import_media(video_id, source_path, storage_mode=item["effective_mode"])
                    importer._import_video_records(workspace_id, series_id, video_id, name, source_path.stem)
                    self._verify_target(video_id, media["bytes"], source_path=source_path)
                    media["video_id"] = video_id
                    media["state"] = "verified"
                    self._save_manifest(run_id, manifest)
                    source_path.unlink()
                elif media["state"] != "verified" or not media["video_id"]:
                    raise LegacyMigrationError(f"旧视频在核验前丢失：{source_path}")
                else:
                    self._verify_target(media["video_id"], media["bytes"])
                media["state"] = "source_removed"
                self._save_manifest(run_id, manifest)
        importer._import_agent_sessions(workspace_id)
        importer._import_llm_usage()
        self._copy_data(source_root, include_data)
        videos_root = source_root / "videos"
        for item in manifest["series"]:
            media_dir = videos_root / item["name"]
            if media_dir.is_dir() and not any(media_dir.iterdir()):
                media_dir.rmdir()
        if videos_root.is_dir() and not any(videos_root.iterdir()):
            videos_root.rmdir()
        with self._sessions.begin() as session:
            run = session.get(LegacyMigrationRun, run_id, with_for_update=True)
            session.query(Series).filter(Series.migration_run_id == run_id).update({Series.import_published: True})
            run.status = "completed"
            run.error = None

    def _verify_target(self, video_id: str | None, expected_bytes: int, *, source_path: Path | None = None) -> None:
        if not video_id:
            raise LegacyMigrationError("迁移记录缺少目标视频 ID")
        with self._sessions() as session:
            media = session.scalar(select(MediaObject).where(MediaObject.video_id == video_id))
        if media is None:
            raise LegacyMigrationError(f"目标视频缺少 Blob 记录：{video_id}")
        reference = BlobReference(media.blob_key, media.sha256, media.byte_size, media.media_type)
        actual = self._blobs.stat(reference)
        if actual.byte_size != expected_bytes or actual.sha256 != media.sha256:
            raise LegacyMigrationError(f"目标视频校验失败：{video_id}")
        if source_path is not None and _sha256_file(source_path) != actual.sha256:
            raise LegacyMigrationError(f"目标与旧视频内容不一致：{source_path}")

    def _copy_data(self, source_root: Path, include_data: list[str]) -> None:
        for name in include_data:
            source_dir = source_root / "data" / name
            target_dir = self._installation_root / "data" / name
            if not source_dir.is_dir() or source_dir.resolve() == target_dir.resolve():
                continue
            for source in source_dir.rglob("*"):
                if not source.is_file():
                    continue
                target = target_dir / source.relative_to(source_dir)
                target.parent.mkdir(parents=True, exist_ok=True)
                if target.exists():
                    if _sha256_file(target) != _sha256_file(source):
                        raise LegacyMigrationError(f"目标数据文件冲突：{target}")
                    continue
                staging = target.with_name(target.name + ".migrating")
                shutil.copy2(source, staging)
                if _sha256_file(staging) != _sha256_file(source):
                    staging.unlink(missing_ok=True)
                    raise LegacyMigrationError(f"数据文件校验失败：{source}")
                staging.replace(target)

    def _check_cancel(self, run_id: str) -> None:
        with self._sessions() as session:
            run = session.get(LegacyMigrationRun, run_id)
            cancelled = run.cancel_requested
        if cancelled:
            with self._sessions.begin() as session:
                session.get(LegacyMigrationRun, run_id).status = "cancelled"
            raise _MigrationCancelled()

    def _save_manifest(self, run_id: str, manifest: dict[str, Any]) -> None:
        with self._sessions.begin() as session:
            run = session.get(LegacyMigrationRun, run_id, with_for_update=True)
            run.manifest = deepcopy(manifest)
            run.verified_videos = sum(1 for series in manifest["series"] for item in series["media"] + series["external"] if item["state"] != "pending")
            run.removed_videos = sum(1 for series in manifest["series"] for item in series["media"] if item["state"] == "source_removed")

    @staticmethod
    def _summary(run: LegacyMigrationRun) -> dict[str, Any]:
        return {"id": run.id, "source_root": run.source_root, "status": run.status, "error": run.error, "total_videos": run.total_videos, "verified_videos": run.verified_videos, "removed_videos": run.removed_videos, "manifest": run.manifest, "include_data": run.include_data}


class _MigrationCancelled(Exception):
    pass


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _existing_ancestor(path: Path) -> Path:
    while not path.exists():
        if path.parent == path:
            raise FileNotFoundError(path)
        path = path.parent
    return path
