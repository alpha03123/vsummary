"""Copy linked videos' platform covers into artifact storage.

Platform cover URLs (B站 hdslb, YouTube, 抖音) are hotlink-protected or short-lived, so the library
serves its own copy. The worker's maintenance loop calls ``run``; downloads happen on a background
thread so a slow image host never delays job reconciliation.
"""

from __future__ import annotations

import logging
import subprocess
import time
import urllib.request
from collections.abc import Callable
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Lock, Thread

from sqlalchemy import text

from backend.video_summary.infrastructure.persistence.sql_video_workspace import SqlVideoWorkspace, _linked_video_sources

LOGGER = logging.getLogger(__name__)

COVER_KIND = "cover"
COVER_FILENAME = "cover.jpg"
COVER_WIDTH = 480
MAX_COVER_BYTES = 5 * 1024 * 1024
RUN_INTERVAL_SECONDS = 10
BATCH_SIZE = 8
RETRY_AFTER_SECONDS = 3600
_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"


def cover_source_url(url: str) -> str:
    """Normalise a platform cover URL; B站 serves protocol-relative and plain-http image links."""
    url = url.strip()
    if url.startswith("//"):
        url = "https:" + url
    if url.startswith("http://") and ".hdslb.com/" in url:
        url = "https://" + url[len("http://"):]
    return url


def download_cover(url: str, target: Path) -> None:
    """Fetch one cover and re-encode it as a small JPEG; raises on any failure."""
    request = urllib.request.Request(cover_source_url(url), headers={"User-Agent": _USER_AGENT})
    with urllib.request.urlopen(request, timeout=10) as response:
        data = response.read(MAX_COVER_BYTES + 1)
    if not data or len(data) > MAX_COVER_BYTES:
        raise ValueError("Cover image is empty or too large.")
    raw = target.with_suffix(".source")
    raw.write_bytes(data)
    subprocess.run(
        ["ffmpeg", "-loglevel", "error", "-y", "-i", str(raw), "-frames:v", "1",
         "-vf", f"scale='min({COVER_WIDTH},iw)':-2", "-q:v", "4", str(target)],
        check=True, capture_output=True, timeout=30,
    )
    raw.unlink(missing_ok=True)


class LinkedCoverSync:
    """Find linked videos without a stored cover and fetch a few at a time."""

    def __init__(
        self,
        session_factory,
        workspace_for: Callable[[str], SqlVideoWorkspace],
        *,
        fetch: Callable[[str, Path], None] = download_cover,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._sessions = session_factory
        self._workspace_for = workspace_for
        self._fetch = fetch
        self._clock = clock
        self._lock = Lock()
        self._thread: Thread | None = None
        self._next_run = 0.0
        self._failed: dict[tuple[str, str], float] = {}

    def run(self) -> None:
        """Start one background batch unless one is running or the last started recently."""
        with self._lock:
            if (self._thread is not None and self._thread.is_alive()) or self._clock() < self._next_run:
                return
            self._next_run = self._clock() + RUN_INTERVAL_SECONDS
            self._thread = Thread(target=self._run_logged, name="vsummary-cover-sync", daemon=True)
            self._thread.start()

    def _run_logged(self) -> None:
        try:
            self.sync_batch()
        except Exception:
            LOGGER.exception("cover sync failed")

    def pending(self) -> list[tuple[str, str, str]]:
        """Return ``(workspace_id, video_id, cover_url)`` for linked videos still missing a cover."""
        with self._sessions() as session:
            rows = session.execute(text("""SELECT s.workspace_id,s.id AS series_id,v.id AS video_id,v.external_source_id,m.payload
                FROM videos v JOIN series s ON s.id=v.series_id JOIN linked_series_metadata m ON m.series_id=s.id
                WHERE v.deleted_at IS NULL AND s.deleted_at IS NULL AND v.external_source_id IS NOT NULL
                  AND NOT EXISTS (SELECT 1 FROM artifacts a WHERE a.video_id=v.id AND a.kind=:kind)
                ORDER BY v.created_at DESC LIMIT 500"""), {"kind": COVER_KIND}).mappings().all()
        sources: dict[str, dict] = {}
        pending = []
        now = self._clock()
        for row in rows:
            if row["series_id"] not in sources:
                sources[row["series_id"]] = _linked_video_sources(row["payload"])
            source = sources[row["series_id"]].get(row["external_source_id"])
            url = source.cover_url.strip() if source is not None else ""
            if url and self._failed.get((row["video_id"], url), 0.0) <= now:
                pending.append((row["workspace_id"], row["video_id"], url))
        return pending

    def sync_batch(self) -> int:
        """Store up to ``BATCH_SIZE`` covers; returns how many were saved."""
        saved = 0
        for workspace_id, video_id, url in self.pending()[:BATCH_SIZE]:
            with TemporaryDirectory(prefix="vsummary-cover-") as directory:
                target = Path(directory) / COVER_FILENAME
                try:
                    self._fetch(url, target)
                    self._workspace_for(workspace_id).save_generated_artifact(
                        video_id=video_id, kind=COVER_KIND, source_path=target, media_type="image/jpeg")
                except LookupError:
                    continue  # The video was deleted while its cover downloaded.
                except Exception as error:
                    self._failed[(video_id, url)] = self._clock() + RETRY_AFTER_SECONDS
                    LOGGER.warning("cover download failed for %s: %s", video_id, error)
                    continue
            saved += 1
        return saved
