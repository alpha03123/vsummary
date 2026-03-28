from __future__ import annotations

from pathlib import Path
from typing import Protocol

from domain.models import SummaryDocument, Transcript


class Transcriber(Protocol):
    def transcribe(self, audio_path: Path, output_stem: Path) -> Transcript:
        ...


class Summarizer(Protocol):
    def summarize(self, video, transcript: Transcript, output_dir: Path) -> SummaryDocument:
        ...
