import asyncio
from types import SimpleNamespace

from backend.bilibili.ytdlp_bilibili import YtDlpBilibiliResolver


def test_season_reads_nested_video_durations():
    view = {'ugc_season': {'sections': [{'episodes': [
        {'bvid': 'BV15Hev6yEw1', 'title': '第一集', 'arc': {'duration': 557}},
        {'bvid': 'BV1BH8q6mECG', 'title': '第二集', 'page': {'duration': 602}},
    ]}]}}
    resolver = YtDlpBilibiliResolver(extractor=lambda _: {'id': 'BV15Hev6yEw1'}, view_extractor=lambda _: view)
    result = asyncio.run(resolver.resolve_series(SimpleNamespace(url='https://www.bilibili.com/video/BV15Hev6yEw1/')))
    assert [video.duration_seconds for video in result.videos] == [557, 602]


def test_flat_entries_with_titles_still_fetch_missing_durations():
    calls = []
    def view(bvid):
        calls.append(bvid)
        return {'pages': [{'page': 1, 'part': '课程', 'duration': 120}]}
    resolver = YtDlpBilibiliResolver(extractor=lambda _: {
        'id': 'BV15Hev6yEw1', 'title': '课程', 'entries': [{'id': 'BV15Hev6yEw1', 'title': '课程'}],
    }, view_extractor=view)
    result = asyncio.run(resolver.resolve_series(SimpleNamespace(url='https://www.bilibili.com/video/BV15Hev6yEw1/')))
    assert calls == ['BV15Hev6yEw1']
    assert result.videos[0].duration_seconds == 120
