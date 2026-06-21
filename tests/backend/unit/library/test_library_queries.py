from __future__ import annotations

from types import SimpleNamespace

from backend.video_summary.library.usecases import GetSeriesMindmap


class FakeWorkspace:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self.mindmap = SimpleNamespace(series_id="s1", mindmap={"id": "root"})

    def get_series_mindmap(self, series_id: str):
        self.calls.append(series_id)
        return self.mindmap


def test_get_series_mindmap_delegates_to_workspace() -> None:
    workspace = FakeWorkspace()
    use_case = GetSeriesMindmap(workspace)

    result = use_case.run("s1")

    assert result is workspace.mindmap
    assert workspace.calls == ["s1"]
