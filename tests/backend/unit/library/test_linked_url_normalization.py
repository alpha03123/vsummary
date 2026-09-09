from backend.video_summary.library.usecases.linked_videos import _normalize_external_url


def test_douyin_jingxuan_modal_url_normalizes_to_video_url() -> None:
    normalized = _normalize_external_url(
        "https://www.douyin.com/jingxuan?modal_id=7673754688373689615",
        "douyin",
    )

    assert normalized == "https://www.douyin.com/video/7673754688373689615"
