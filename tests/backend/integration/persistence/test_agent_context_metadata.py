"""Agent metadata reads must not contend with active video playback."""

from unittest.mock import Mock

from backend.video_summary.agent_adapter import WorkspaceAgentContextLoader


def test_agent_context_uses_sql_metadata_without_materializing_media(stored_video, tmp_path, monkeypatch):
    workspace, _, _ = stored_video
    source = tmp_path / "context-video.mp4"
    source.write_bytes(b"media content")
    series = workspace.import_local_series_from_paths(title="Context series", source_paths=[source])
    video = series.videos[0]
    materialize = Mock(side_effect=PermissionError("Media is currently playing"))
    monkeypatch.setattr(workspace._blobs, "materialize", materialize)

    context = WorkspaceAgentContextLoader(workspace).load(f"video|{series.id}|{video.id}::conversation")

    assert context.video_id == video.id
    assert context.video_title == video.title
    assert context.series_title == "Context series"
    assert context.preview.available
    materialize.assert_not_called()
