from __future__ import annotations

from threading import Lock
from threading import Thread
from typing import Callable
import logging

from backend.video_summary.infrastructure.in_memory_progress_tracker import InMemoryProgressTracker


LOGGER = logging.getLogger(__name__)


class _WorkspaceIndexInvalidator:
    def __init__(self, invalidate: Callable[[], None]) -> None:
        self._invalidate = invalidate

    def invalidate(self) -> None:
        self._invalidate()


class _WorkspaceIndexRefresher:
    def __init__(
        self,
        refresh_all: Callable[[], None],
        upsert_video: Callable[[str, str], None],
        delete_video: Callable[[str, str], None],
        delete_series: Callable[[str], None],
        *,
        progress_tracker: InMemoryProgressTracker,
        task_id: str = "agent-memory-refresh",
    ) -> None:
        self._refresh_all = refresh_all
        self._upsert_video = upsert_video
        self._delete_video = delete_video
        self._delete_series = delete_series
        self._progress_tracker = progress_tracker
        self._task_id = task_id
        self._lock = Lock()
        self._in_flight = False
        self._pending_full_rebuild = False
        self._pending_video_upserts: set[tuple[str, str]] = set()
        self._pending_video_deletes: set[tuple[str, str]] = set()
        self._pending_series_deletes: set[str] = set()

    def refresh(self) -> None:
        with self._lock:
            self._pending_full_rebuild = True
            self._pending_video_upserts.clear()
            self._pending_video_deletes.clear()
            self._pending_series_deletes.clear()
            should_start = self._mark_worker_in_flight_locked()
        if should_start:
            self._start_worker()

    def refresh_all(self) -> None:
        self.refresh()

    def upsert_video(self, series_id: str, video_id: str) -> None:
        with self._lock:
            if not self._pending_full_rebuild and series_id not in self._pending_series_deletes:
                self._pending_video_deletes.discard((series_id, video_id))
                self._pending_video_upserts.add((series_id, video_id))
            should_start = self._mark_worker_in_flight_locked()
        if should_start:
            self._start_worker()

    def delete_video(self, series_id: str, video_id: str) -> None:
        with self._lock:
            if not self._pending_full_rebuild and series_id not in self._pending_series_deletes:
                self._pending_video_upserts.discard((series_id, video_id))
                self._pending_video_deletes.add((series_id, video_id))
            should_start = self._mark_worker_in_flight_locked()
        if should_start:
            self._start_worker()

    def delete_series(self, series_id: str) -> None:
        with self._lock:
            if not self._pending_full_rebuild:
                self._pending_series_deletes.add(series_id)
                self._pending_video_upserts = {
                    item for item in self._pending_video_upserts if item[0] != series_id
                }
                self._pending_video_deletes = {
                    item for item in self._pending_video_deletes if item[0] != series_id
                }
            should_start = self._mark_worker_in_flight_locked()
        if should_start:
            self._start_worker()

    def _mark_worker_in_flight_locked(self) -> bool:
        if self._in_flight:
            return False
        self._in_flight = True
        return True

    def _start_worker(self) -> None:
        self._progress_tracker.create_reporter(self._task_id).update(
            "index",
            5.0,
            "数据库整理任务已进入后台队列",
        )
        Thread(target=self._run, daemon=True).start()

    def _run(self) -> None:
        reporter = self._progress_tracker.create_reporter(self._task_id)
        while True:
            try:
                batch = self._drain_pending_batch()
                if batch is None:
                    with self._lock:
                        self._in_flight = False
                    return

                if batch["full_rebuild"]:
                    reporter.update("index", 20.0, "正在重建数据库索引")
                    self._refresh_all()
                else:
                    operations = batch["operations"]
                    total_operations = len(operations)
                    reporter.update("index", 0.0, f"正在更新数据库索引：0/{total_operations}")
                    for completed_count, operation in enumerate(operations, start=1):
                        self._apply_operation(operation)
                        reporter.update(
                            "index",
                            (completed_count / total_operations) * 100.0,
                            f"正在更新数据库索引：{completed_count}/{total_operations}",
                        )
            except Exception as error:
                LOGGER.exception("workspace index refresh failed")
                reporter.failed(str(error))
                with self._lock:
                    self._in_flight = False
                    self._pending_full_rebuild = False
                    self._pending_video_upserts.clear()
                    self._pending_video_deletes.clear()
                    self._pending_series_deletes.clear()
                return

            with self._lock:
                if self._has_pending_operations_locked():
                    continue
                self._in_flight = False
                break

        reporter.completed("数据库整理完成")

    def _drain_pending_batch(self) -> dict[str, object] | None:
        with self._lock:
            if self._pending_full_rebuild:
                self._pending_full_rebuild = False
                return {"full_rebuild": True, "operations": []}

            operations: list[tuple[str, str, str | None]] = []
            for series_id in sorted(self._pending_series_deletes):
                operations.append(("delete_series", series_id, None))
            for series_id, video_id in sorted(self._pending_video_deletes):
                if series_id not in self._pending_series_deletes:
                    operations.append(("delete_video", series_id, video_id))
            for series_id, video_id in sorted(self._pending_video_upserts):
                if series_id not in self._pending_series_deletes and (series_id, video_id) not in self._pending_video_deletes:
                    operations.append(("upsert_video", series_id, video_id))

            self._pending_series_deletes.clear()
            self._pending_video_deletes.clear()
            self._pending_video_upserts.clear()
            if not operations:
                return None
            return {"full_rebuild": False, "operations": operations}

    def _has_pending_operations_locked(self) -> bool:
        return bool(
            self._pending_full_rebuild
            or self._pending_video_upserts
            or self._pending_video_deletes
            or self._pending_series_deletes
        )

    def _apply_operation(self, operation: tuple[str, str, str | None]) -> None:
        kind, series_id, video_id = operation
        if kind == "upsert_video":
            self._upsert_video(series_id, str(video_id))
            return
        if kind == "delete_video":
            self._delete_video(series_id, str(video_id))
            return
        if kind == "delete_series":
            self._delete_series(series_id)
            return
        raise RuntimeError(f"unsupported workspace index operation '{kind}'")