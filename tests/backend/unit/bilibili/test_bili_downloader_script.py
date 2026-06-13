from __future__ import annotations

import pytest

from scripts.bili_downloader import (
    BiliApiError,
    parse_video_identifier,
    safe_filename,
    select_standard_durl,
    validate_api_payload,
)


def test_parse_video_identifier_reads_bvid_from_multi_page_url() -> None:
    identifier = parse_video_identifier("https://www.bilibili.com/video/BV1xx411c7mD/?p=3")

    assert identifier == {"bvid": "BV1xx411c7mD"}


def test_parse_video_identifier_reads_aid_from_av_url() -> None:
    identifier = parse_video_identifier("https://www.bilibili.com/video/av170001")

    assert identifier == {"aid": "170001"}


def test_safe_filename_removes_windows_forbidden_chars() -> None:
    assert safe_filename('标题:第/一<P>|"测试"*?') == "标题_第_一_P___测试___"


def test_validate_api_payload_raises_for_bili_error_code() -> None:
    with pytest.raises(BiliApiError, match="B站 API 返回错误"):
        validate_api_payload({"code": -400, "message": "请求错误"})


def test_select_standard_durl_rejects_dash_only_payload() -> None:
    with pytest.raises(BiliApiError, match="未返回标清单文件下载地址"):
        select_standard_durl({"dash": {"video": []}})


def test_select_standard_durl_returns_first_durl_entry() -> None:
    url = select_standard_durl({"durl": [{"url": "https://example.test/video.mp4"}]})

    assert url == "https://example.test/video.mp4"
