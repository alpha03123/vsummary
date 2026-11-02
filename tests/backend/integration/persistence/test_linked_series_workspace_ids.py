from backend.core.ids import new_ulid
from backend.video_summary.infrastructure.persistence.control_plane_repository import SqlControlPlaneRepository
from backend.video_summary.infrastructure.persistence.file_blob_store import FileBlobStore
from backend.video_summary.infrastructure.persistence.sql_video_workspace import SqlVideoWorkspace
from backend.video_summary.library.linked_models import LinkedSeries, LinkedVideo


def _linked_series():
    return LinkedSeries(
        series_id="bilibili-BV1SJnH6hEQp",
        title="GPU Daily",
        cover_url="",
        source_url="https://www.bilibili.com/video/BV1SJnH6hEQp",
        videos=[
            LinkedVideo(
                source_id="BV1SJnH6hEQp",
                item_index=1,
                title="Episode 1",
                cover_url="",
                duration_seconds=60,
                source_url="https://www.bilibili.com/video/BV1SJnH6hEQp",
            )
        ],
    )


def _workspace(sessions, root, workspace_id):
    return SqlVideoWorkspace(
        session_factory=sessions,
        blob_store=FileBlobStore(root / "blobs"),
        cache_root=root / "cache",
        workspace_id=workspace_id,
    )


def test_linked_series_ids_are_scoped_by_workspace(mysql_sessions, tmp_path):
    control = SqlControlPlaneRepository(mysql_sessions)
    first_workspace_id = control.create_workspace(owner_scope_id=f"first-{new_ulid()}", title="First")
    second_workspace_id = control.create_workspace(owner_scope_id=f"second-{new_ulid()}", title="Second")
    first = _workspace(mysql_sessions, tmp_path / "first", first_workspace_id)
    second = _workspace(mysql_sessions, tmp_path / "second", second_workspace_id)

    first_saved = first.save_linked_series(_linked_series())
    second_saved = second.save_linked_series(_linked_series())
    second_saved_again = second.save_linked_series(_linked_series())

    assert first_saved.series_id != "bilibili-BV1SJnH6hEQp"
    assert second_saved.series_id != "bilibili-BV1SJnH6hEQp"
    assert first_saved.series_id != second_saved.series_id
    assert second_saved_again.series_id == second_saved.series_id
    assert second.get_linked_series(second_saved.series_id).source_url == _linked_series().source_url