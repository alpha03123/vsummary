from __future__ import annotations

from backend.video_summary.library.linked_models import LinkedSeries, LinkedVideo
from .bilibili_url_parser import BilibiliUrlInfo


class BilibiliMetaService:
    async def resolve_series(self, url_info: BilibiliUrlInfo) -> LinkedSeries:
        if url_info.url_type == "season":
            return await self._resolve_season(url_info)
        if url_info.url_type == "series":
            return await self._resolve_series_type(url_info)
        if url_info.url_type == "video":
            return await self._resolve_multi_page_video(url_info)
        raise ValueError(f"不支持的 url_type: {url_info.url_type}")

    async def resolve_single_video(self, url_info: BilibiliUrlInfo) -> LinkedVideo:
        if url_info.url_type != "video" or not url_info.bvid:
            raise ValueError("resolve_single_video 仅适用于 video 类型")

        from bilibili_api import video as bili_video  # type: ignore[import]

        video = bili_video.Video(bvid=url_info.bvid)
        info = await video.get_info()
        return LinkedVideo(
            bvid=url_info.bvid,
            page=1,
            title=str(info.get("title", url_info.bvid)),
            cover_url=str(info.get("pic", "")),
            duration_seconds=int(info.get("duration", 0)),
            source_url=f"https://www.bilibili.com/video/{url_info.bvid}",
        )

    async def _resolve_season(self, url_info: BilibiliUrlInfo) -> LinkedSeries:
        assert url_info.sid is not None

        from bilibili_api import ChannelSeriesType, channel_series  # type: ignore[import]

        series = channel_series.ChannelSeries(
            uid=url_info.uid or -1,
            type_=ChannelSeriesType.SEASON,
            id_=url_info.sid,
        )
        meta = await series.get_meta()
        return LinkedSeries(
            series_id=f"bilibili-season-{url_info.sid}",
            title=str(meta.get("name", f"合集 {url_info.sid}")),
            cover_url=str(meta.get("cover", "")),
            source_url=f"https://space.bilibili.com/{url_info.uid}/channel/collectiondetail?sid={url_info.sid}",
            videos=await self._fetch_all_collection_videos(series),
        )

    async def _resolve_series_type(self, url_info: BilibiliUrlInfo) -> LinkedSeries:
        assert url_info.sid is not None

        from bilibili_api import ChannelSeriesType, channel_series  # type: ignore[import]

        series = channel_series.ChannelSeries(
            uid=url_info.uid or -1,
            type_=ChannelSeriesType.SERIES,
            id_=url_info.sid,
        )
        meta = await series.get_meta()
        meta_info = meta.get("meta", {})
        return LinkedSeries(
            series_id=f"bilibili-series-{url_info.sid}",
            title=str(meta_info.get("name", f"系列 {url_info.sid}")),
            cover_url=str(meta_info.get("cover", "")),
            source_url=f"https://space.bilibili.com/{url_info.uid}/channel/seriesdetail?sid={url_info.sid}",
            videos=await self._fetch_all_collection_videos(series),
        )

    async def _resolve_multi_page_video(self, url_info: BilibiliUrlInfo) -> LinkedSeries:
        assert url_info.bvid is not None

        from bilibili_api import video as bili_video  # type: ignore[import]

        video = bili_video.Video(bvid=url_info.bvid)
        info = await video.get_info()
        pages = info.get("pages", [])
        source_url = f"https://www.bilibili.com/video/{url_info.bvid}"

        videos = [
            LinkedVideo(
                bvid=url_info.bvid,
                page=page.get("page", index + 1),
                title=str(page.get("part", f"P{index + 1}")),
                cover_url=str(info.get("pic", "")),
                duration_seconds=int(page.get("duration", 0)),
                source_url=f"{source_url}?p={page.get('page', index + 1)}",
            )
            for index, page in enumerate(pages)
        ]

        return LinkedSeries(
            series_id=f"bilibili-video-{url_info.bvid}",
            title=str(info.get("title", url_info.bvid)),
            cover_url=str(info.get("pic", "")),
            source_url=source_url,
            videos=videos,
        )

    async def _fetch_all_collection_videos(self, series) -> list[LinkedVideo]:
        from bilibili_api.channel_series import ChannelOrder  # type: ignore[import]

        videos: list[LinkedVideo] = []
        pn = 1
        ps = 50

        while True:
            result = await series.get_videos(sort=ChannelOrder.DEFAULT, pn=pn, ps=ps)
            archives = result.get("archives", [])
            if not archives:
                break

            for item in archives:
                bvid = str(item.get("bvid", "")).strip()
                if not bvid:
                    continue
                videos.append(
                    LinkedVideo(
                        bvid=bvid,
                        page=1,
                        title=str(item.get("title", bvid)),
                        cover_url=str(item.get("pic", "")),
                        duration_seconds=int(item.get("duration", 0)),
                        source_url=f"https://www.bilibili.com/video/{bvid}",
                    )
                )

            meta = result.get("meta", {})
            page_info = result.get("page", {})
            has_more = bool(meta.get("has_more", False))
            total = int(page_info.get("total", len(archives)))
            if not has_more and pn * ps >= total:
                break
            pn += 1

        return videos
