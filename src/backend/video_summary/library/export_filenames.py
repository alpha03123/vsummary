"""导出文件名：用视频标题或原文件名生成用户看得懂、Windows 能保存的名字。"""

from __future__ import annotations

import re
from pathlib import PurePath

MAX_STEM_LENGTH = 60

# Windows 不允许的半角符号换成形近的全角符号，标题语义不丢。
_LOOKALIKES = str.maketrans({":": "：", "?": "？", "*": "＊", "<": "《", ">": "》", "|": "｜", "/": "／", "\\": "＼"})
_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]")
_HASHTAG = re.compile(r"(?:^|\s)#\S+")
_WHITESPACE = re.compile(r"\s+")
_RESERVED_NAMES = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}


def clean_filename_stem(value: str, fallback: str = "export") -> str:
    """把标题清洗成文件名主体（不含后缀）。

    只取第一行，去掉平台标题里的 #话题，把 Windows 不允许的符号换成全角，
    压缩空白，截断过长部分，避开 CON/NUL 等保留名。
    """
    lines = (value or "").strip().splitlines()
    text = lines[0] if lines else ""
    without_tags = _HASHTAG.sub(" ", text)
    if without_tags.strip():
        text = without_tags
    text = _pair_quotes(_CONTROL_CHARS.sub(" ", text)).translate(_LOOKALIKES)
    text = _WHITESPACE.sub(" ", text).strip(" .")
    if len(text) > MAX_STEM_LENGTH:
        text = text[:MAX_STEM_LENGTH].rstrip(" .")
    if not text:
        return fallback
    if text.split(".")[0].upper() in _RESERVED_NAMES:
        text = f"_{text}"
    return text


def _pair_quotes(text: str) -> str:
    """半角双引号按出现顺序换成成对的“”。"""
    parts = text.split('"')
    return "".join(part + ("“" if index % 2 == 0 else "”") for index, part in enumerate(parts[:-1])) + parts[-1]


def video_title_stem(title: str, video_id: str) -> str:
    """Markdown 等导出用视频标题命名。"""
    return clean_filename_stem(title, fallback=clean_filename_stem(video_id))


def video_media_stem(title: str, source_name: str, video_id: str, *, is_linked: bool = False) -> str:
    """字幕和视频导出优先用本地原文件名，播放器才能自动匹配字幕。

    链接导入的视频 source_name 是站点名，没有意义，此时退回标题。
    """
    if not is_linked and source_name and PurePath(source_name).suffix:
        stem = clean_filename_stem(PurePath(source_name).stem, fallback="")
        if stem:
            return stem
    return video_title_stem(title, video_id)


def unique_filename(filename: str, used: set[str]) -> str:
    """同一个压缩包里重名时追加 (2)、(3)。"""
    path = PurePath(filename)
    candidate = filename
    counter = 2
    while candidate.casefold() in used:
        candidate = f"{path.stem} ({counter}){path.suffix}"
        counter += 1
    used.add(candidate.casefold())
    return candidate
