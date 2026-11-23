"""视频课件（PPT / 板书页）提取与 PDF 导出用例。"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
import shutil
from typing import Any, Protocol
from uuid import uuid4

from PIL import Image

from backend.core.ids import new_ulid


@dataclass(frozen=True)
class ExtractedSlideFile:
    """单页已抽取并落盘于 staging 的课件图片。"""

    ordinal: int
    start_seconds: float
    end_seconds: float
    capture_seconds: float
    image_filename: str
    path: Path
    width: int
    height: int


@dataclass(frozen=True)
class ExtractedCourseware:
    """一次视频课件提取的完整结果。"""

    duration_seconds: float
    slides: list[ExtractedSlideFile]


class CoursewareExtractor(Protocol):
    """从源视频文件中按画面跳变提取课件页的端口。"""

    def extract(
        self,
        video_path: Path,
        output_dir: Path,
        *,
        on_progress: Callable[[str, float, str], None] | None = None,
    ) -> ExtractedCourseware: ...


class GenerateVideoCourseware:
    """为单个视频提取课件页并持久化到工作区。"""

    def __init__(self, workspace, extractor: CoursewareExtractor, *, temp_root: Path) -> None:
        self._workspace = workspace
        self._extractor = extractor
        self._temp_root = temp_root

    async def arun(
        self,
        series_id: str,
        video_id: str,
        *,
        on_progress: Callable[[str, float, str], None] | None = None,
    ) -> dict[str, Any] | None:
        return await asyncio.to_thread(self.run, series_id, video_id, on_progress=on_progress)

    def run(
        self,
        series_id: str,
        video_id: str,
        *,
        on_progress: Callable[[str, float, str], None] | None = None,
    ) -> dict[str, Any] | None:
        if self._workspace.is_audio_only_media(series_id, video_id):
            raise ValueError("纯音频文件不支持提取视频课件。")
        source = self._workspace.get_video_source(series_id, video_id)
        if source is None or not source.source_path.is_file():
            return None

        staging_dir = self._temp_root / "courseware-staging" / f"{video_id}-{uuid4().hex}"
        staging_dir.mkdir(parents=True, exist_ok=True)
        try:
            if on_progress is not None:
                on_progress("courseware", 10.0, "正在扫描视频画面跳变")
            extracted = self._extractor.extract(
                source.source_path,
                staging_dir,
                on_progress=on_progress,
            )
            slide_payloads: list[dict[str, Any]] = []
            slide_files: list[Path] = []
            for slide in extracted.slides:
                if not slide.path.is_file():
                    continue
                slide_files.append(slide.path)
                slide_payloads.append(
                    {
                        "id": new_ulid(),
                        "ordinal": slide.ordinal,
                        "start_seconds": round(slide.start_seconds, 3),
                        "end_seconds": round(slide.end_seconds, 3),
                        "capture_seconds": round(slide.capture_seconds, 3),
                        "image_filename": slide.image_filename,
                        "width": slide.width,
                        "height": slide.height,
                    }
                )
            if on_progress is not None:
                on_progress("courseware", 92.0, "正在保存课件页面")
            deck = {
                "id": new_ulid(),
                "extractor_version": 1,
                "title": source.title,
                "duration_seconds": round(extracted.duration_seconds, 3),
                "slides": slide_payloads,
            }
            return self._workspace.save_video_courseware(
                series_id,
                video_id,
                deck=deck,
                slide_files=slide_files,
            )
        finally:
            shutil.rmtree(staging_dir, ignore_errors=True)


def render_courseware_pdf(slide_paths: list[Path]) -> bytes:
    """将一组课件页图片合成为多页 PDF 字节流。"""
    existing = [path for path in slide_paths if path.is_file()]
    if not existing:
        raise ValueError("没有可导出的课件页面。")
    rgb_images: list[Image.Image] = []
    try:
        for path in existing:
            with Image.open(path) as img:
                rgb_images.append(img.convert("RGB"))
        buffer = BytesIO()
        first, rest = rgb_images[0], rgb_images[1:]
        first.save(
            buffer,
            format="PDF",
            save_all=True,
            append_images=rest,
            resolution=150.0,
        )
        return buffer.getvalue()
    finally:
        for image in rgb_images:
            image.close()
