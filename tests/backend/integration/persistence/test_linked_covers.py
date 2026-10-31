from backend.core.ids import new_ulid
from backend.video_summary.infrastructure.persistence.linked_cover_sync import LinkedCoverSync
from backend.video_summary.library.linked_models import LinkedSeries, LinkedVideo


def _linked_video(workspace, cover_url="https://img.example/cover.jpg"):
    series_id = new_ulid()
    workspace.save_linked_series(LinkedSeries(series_id=series_id, title="Linked", cover_url=cover_url, source_url="https://example/s",
        videos=[LinkedVideo(source_id="BV1cover", item_index=1, title="Episode", cover_url=cover_url, duration_seconds=95,
                            source_url="https://example/v")]))
    series = next(item for item in workspace.list_series() if item.id == series_id)
    return series_id, series.videos[0]


def test_linked_video_cover_is_stored_once_and_listed(stored_video, mysql_sessions):
    workspace = stored_video[0]
    series_id, before = _linked_video(workspace)
    assert before.cover_url == "" and before.duration_seconds == 95
    fetched = []

    def fetch(url, target):
        fetched.append(url)
        target.write_bytes(b"\xff\xd8 cover \xff\xd9")

    sync = LinkedCoverSync(mysql_sessions, lambda _workspace_id: workspace, fetch=fetch)
    sync.sync_batch()
    sync.sync_batch()

    # The sweep covers every workspace; other tests may leave covers pending in the shared database.
    assert fetched.count("https://img.example/cover.jpg") == 1
    after = next(item for item in workspace.list_series() if item.id == series_id).videos[0]
    assert after.cover_url.startswith(f"/api/videos/{series_id}/{after.id}/cover?v=")
    cover = workspace.materialize_artifact(video_id=after.id, kind="cover", filename="cover.jpg")
    assert cover is not None and cover.read_bytes() == b"\xff\xd8 cover \xff\xd9"


def test_failed_cover_download_is_not_retried_straight_away(stored_video, mysql_sessions):
    workspace = stored_video[0]
    _series_id, video = _linked_video(workspace, cover_url="https://img.example/broken.jpg")
    attempts = []

    def fetch(url, target):
        attempts.append(url)
        raise OSError("host unreachable")

    sync = LinkedCoverSync(mysql_sessions, lambda _workspace_id: workspace, fetch=fetch)
    sync.sync_batch()
    sync.sync_batch()

    assert attempts.count("https://img.example/broken.jpg") == 1
    assert workspace.materialize_artifact(video_id=video.id, kind="cover", filename="cover.jpg") is None
