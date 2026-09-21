from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any

import httpx


VIEW_API_URL = "https://api.bilibili.com/x/web-interface/view"
PLAYURL_API_URL = "https://api.bilibili.com/x/player/playurl"
STANDARD_QUALITY = 16
CHUNK_SIZE = 1024 * 1024
WINDOWS_FORBIDDEN_CHARS = '<>:"/\\|?*'


class BiliApiError(RuntimeError):
    pass


def parse_video_identifier(value: str) -> dict[str, str]:
    text = value.strip()
    bvid_match = re.search(r"(BV[0-9A-Za-z]{10})", text)
    if bvid_match:
        return {"bvid": bvid_match.group(1)}

    aid_match = re.search(r"(?:^|/)av(\d+)(?:\D|$)", text, flags=re.IGNORECASE)
    if aid_match:
        return {"aid": aid_match.group(1)}

    raise BiliApiError("无法从输入中解析 BV 号或 av 号")


def safe_filename(value: str) -> str:
    translation = str.maketrans({char: "_" for char in WINDOWS_FORBIDDEN_CHARS})
    name = value.translate(translation).strip().rstrip(".")
    return name or "untitled"


def validate_api_payload(payload: dict[str, Any]) -> dict[str, Any]:
    code = payload.get("code")
    if code != 0:
        message = payload.get("message") or payload.get("msg") or "未知错误"
        raise BiliApiError(f"B站 API 返回错误：{message} ({code})")
    data = payload.get("data")
    if not isinstance(data, dict):
        raise BiliApiError("B站 API 返回结构缺少 data")
    return data


def select_standard_durl(playurl_data: dict[str, Any]) -> str:
    durl = playurl_data.get("durl")
    if not isinstance(durl, list) or not durl:
        raise BiliApiError("未返回标清单文件下载地址")
    first = durl[0]
    if not isinstance(first, dict):
        raise BiliApiError("标清下载地址结构无效")
    url = first.get("url")
    if isinstance(url, str) and url:
        return url
    backup_urls = first.get("backup_url")
    if isinstance(backup_urls, list):
        for backup_url in backup_urls:
            if isinstance(backup_url, str) and backup_url:
                return backup_url
    raise BiliApiError("标清下载地址为空")


class BiliDownloader:
    def __init__(self, *, output_root: Path) -> None:
        self._output_root = output_root
        self._client = httpx.Client(
            timeout=httpx.Timeout(60.0, read=None),
            follow_redirects=True,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
                "Referer": "https://www.bilibili.com/",
            },
        )

    def close(self) -> None:
        self._client.close()

    def download(self, video_link: str) -> Path:
        identifier = parse_video_identifier(video_link)
        view_data = self._get_json(VIEW_API_URL, identifier)
        title = _expect_text(view_data, "title")
        bvid = _expect_text(view_data, "bvid")
        pages = view_data.get("pages")
        if not isinstance(pages, list) or not pages:
            raise BiliApiError("视频没有可下载的分 P 信息")

        video_dir = self._output_root / safe_filename(f"{title}-{bvid}")
        video_dir.mkdir(parents=True, exist_ok=True)
        print(f"输出目录：{video_dir}")

        for index, page in enumerate(pages, start=1):
            if not isinstance(page, dict):
                raise BiliApiError("分 P 数据结构无效")
            cid = page.get("cid")
            if not isinstance(cid, int):
                raise BiliApiError(f"第 {index} P 缺少 cid")
            part = str(page.get("part") or f"P{index}")
            output_file = video_dir / f"P{index:02d}-{safe_filename(part)}.mp4"
            playurl_data = self._fetch_playurl(identifier, cid)
            video_url = select_standard_durl(playurl_data)
            print(f"[{index}/{len(pages)}] 下载：{output_file.name}")
            self._download_file(video_url, output_file)

        return video_dir

    def _fetch_playurl(self, identifier: dict[str, str], cid: int) -> dict[str, Any]:
        params = {
            **identifier,
            "cid": str(cid),
            "qn": str(STANDARD_QUALITY),
            "fnval": "0",
            "fourk": "0",
        }
        return self._get_json(PLAYURL_API_URL, params)

    def _get_json(self, url: str, params: dict[str, str]) -> dict[str, Any]:
        response = self._client.get(url, params=params)
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise BiliApiError("B站 API 返回非 JSON 对象")
        return validate_api_payload(payload)

    def _download_file(self, url: str, output_file: Path) -> None:
        temp_file = output_file.with_suffix(output_file.suffix + ".download")
        try:
            with self._client.stream("GET", url) as response:
                response.raise_for_status()
                with temp_file.open("wb") as file:
                    for chunk in response.iter_bytes(CHUNK_SIZE):
                        if chunk:
                            file.write(chunk)
            temp_file.replace(output_file)
        except Exception:
            if temp_file.exists():
                temp_file.unlink()
            raise


def _expect_text(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise BiliApiError(f"B站 API 返回结构缺少 {key}")
    return value.strip()


def _default_output_root() -> Path:
    project_root = Path(__file__).resolve().parents[1]
    return project_root / "temp" / "bili_downloader"


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    video_link = args[0].strip() if args else input("请输入 B 站多 P 视频链接：").strip()
    if not video_link:
        print("未输入视频链接", file=sys.stderr)
        return 2

    downloader = BiliDownloader(output_root=_default_output_root())
    try:
        output_dir = downloader.download(video_link)
    except (BiliApiError, httpx.HTTPError) as error:
        print(f"下载失败：{error}", file=sys.stderr)
        return 1
    finally:
        downloader.close()

    print(f"下载完成：{output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
