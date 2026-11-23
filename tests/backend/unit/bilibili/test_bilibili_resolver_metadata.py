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


def test_season_expands_multi_page_episodes_and_normalizes_short_link_source_url():
    view = {
        'bvid': 'BV1ZiJC6KErq',
        'title': 'Blender MCP 动画',
        'pages': [
            {'page': 1, 'part': 'video_trimmed', 'duration': 577},
            {'page': 2, 'part': 'original_with_subs', 'duration': 583},
        ],
        'ugc_season': {
            'title': 'AI 创作',
            'sections': [{
                'episodes': [
                    {'bvid': 'BV1DkhF6aEaC', 'title': '第一集', 'arc': {'duration': 300}},
                    {
                        'bvid': 'BV1ZiJC6KErq',
                        'title': 'Blender MCP 动画',
                        'arc': {'duration': 1160},
                        'page': {'page': 1, 'part': 'video_trimmed', 'duration': 577},
                        'pages': [
                            {'page': 1, 'part': 'video_trimmed', 'duration': 577},
                            {'page': 2, 'part': 'original_with_subs', 'duration': 583},
                        ],
                    },
                ],
            }],
        },
    }
    resolver = YtDlpBilibiliResolver(
        extractor=lambda _: {'id': 'BV1ZiJC6KErq_p1', 'title': 'Blender MCP 动画'},
        view_extractor=lambda _: view,
    )
    result = asyncio.run(resolver.resolve_series(SimpleNamespace(url='https://b23.tv/fQ1qTYW')))
    assert result.source_url == 'https://www.bilibili.com/video/BV1ZiJC6KErq'
    assert [(v.video_id, v.item_index, v.title, v.duration_seconds, v.source_url) for v in result.videos] == [
        ('BV1DkhF6aEaC', 1, '第一集', 300, 'https://www.bilibili.com/video/BV1DkhF6aEaC'),
        ('BV1ZiJC6KErq', 1, 'Blender MCP 动画 - video_trimmed', 577, 'https://www.bilibili.com/video/BV1ZiJC6KErq'),
        ('BV1ZiJC6KErq_p2', 2, 'Blender MCP 动画 - original_with_subs', 583, 'https://www.bilibili.com/video/BV1ZiJC6KErq?p=2'),
    ]
