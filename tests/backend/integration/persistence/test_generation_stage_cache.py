from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from PIL import Image

from backend.video_summary.domain.models import SummaryDocument, Transcript, TranscriptSegment
from backend.video_summary.generation.renderers import render_markdown
from backend.video_summary.generation.schemas import SummaryPayload
from backend.video_summary.generation.usecases.generate_summary import GenerateCancelledError, GenerateVideoSummary
from backend.video_summary.infrastructure.application_builders import VideoSummaryApplication
from backend.video_summary.infrastructure.concurrent_ai_summary_runner import ConcurrentAiSummaryRunner
from backend.video_summary.infrastructure.config.settings import load_settings
from backend.video_summary.infrastructure.persistence.sql_generation_adapters import SqlBackedVideoSummaryGenerator
from backend.video_summary.infrastructure.storage.temporary_generation_artifact_store import TemporaryGenerationArtifactStore
from backend.video_summary.infrastructure.video_summary_workflow import ConfiguredVideoSummaryWorkflow
from backend.video_summary.library.models import GeneratedVideoAiNoteDTO


class MediaProcessor:
    cache_identity = "test-audio-extractor-v1"

    def __init__(self):
        self.audio_calls = 0
        self.frame_calls = 0

    def probe_duration(self, video_path):
        return 3.0

    def extract_audio(self, video_path, audio_path, cancellation=None):
        self.audio_calls += 1
        audio_path.write_bytes(video_path.read_bytes())
        return audio_path

    def extract_frame(self, video_path, timestamp_seconds, output_path):
        self.frame_calls += 1
        output_path.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (64, 36), (int(timestamp_seconds * 60), len(video_path.read_bytes()), 30)).save(output_path)
        return output_path


class Transcriber:
    def __init__(self, model):
        self.cache_identity = f"test-asr:{model}"
        self.model = model
        self.calls = 0
        self.fail = False

    def transcribe(self, audio_path, output_stem, on_progress=None):
        self.calls += 1
        if self.fail:
            raise RuntimeError("Injected ASR failure")
        return Transcript(language="zh", segments=[TranscriptSegment(0, 3, f"{self.model}:{audio_path.read_text()}")])


class Enhancer:
    def __init__(self, model):
        self.cache_identity = f"test-enhancer:{model}"
        self.model = model
        self.calls = 0
        self.fail = False

    async def enhance(self, video, transcript, cancellation=None):
        self.calls += 1
        if self.fail:
            raise RuntimeError("Injected enhancement failure")
        return Transcript(language="zh", segments=[TranscriptSegment(0, 3, f"{self.model}:{transcript.full_text}")])


class Summarizer:
    def __init__(self, title, outcome):
        self.title = title
        self.outcome = outcome
        self.calls = 0

    async def summarize(self, video, transcript, cancellation=None):
        self.calls += 1
        if self.outcome == "failed":
            raise RuntimeError("Injected model failure after transcription")
        if self.outcome == "cancelled":
            cancellation.request_cancel()
            raise GenerateCancelledError("Injected cancellation after transcription")
        payload = SummaryPayload.model_validate({"title": self.title, "chapters": [
            {"id": "chapter-1", "title": "Chapter", "start_seconds": 0, "end_seconds": 3},
        ]}).model_dump()
        return SummaryDocument(markdown=render_markdown(payload), summary_data=payload)


class NoteGenerator:
    def __init__(self, fail):
        self.fail = fail
        self.calls = 0
        self.frames = []

    def run_ai_summary(self, **arguments):
        self.calls += 1
        self.frames = arguments["visual_context"].frames
        assert all(frame.image_path.is_file() for frame in self.frames)
        if self.fail:
            raise RuntimeError("Injected visual model failure after sampling")
        return GeneratedVideoAiNoteDTO(
            content="# Note\nGenerated content", note_visual_mode="off", note_max_images=0,
            note_image_min_gap_seconds=0, citations=[], visual_evidence=[],
        )


class RecordingWorkflow(ConfiguredVideoSummaryWorkflow):
    def __init__(self, root, application):
        super().__init__(root)
        self.application = application
        self.output_dirs = []

    def _get_application(self, transcript_enhancement_enabled):
        return self.application

    async def run(self, source_path, output_dir, **arguments):
        self.output_dirs.append(output_dir)
        return await super().run(source_path, output_dir, **arguments)


class Pipeline:
    def __init__(self, stored_video, root, *, outcome=None, asr_model="asr-1", enhancer_model="enhancer-1", visual=None, fail_visual=False):
        self.workspace, self.series_id, self.video_id = stored_video
        self.media = MediaProcessor()
        self.asr = Transcriber(asr_model)
        self.enhancer = Enhancer(enhancer_model)
        self.summarizer = Summarizer(root.name, outcome)
        self.note = NoteGenerator(fail_visual)
        runner = ConcurrentAiSummaryRunner(
            generator=self.note, media_processor=self.media, max_input_images=1, multimodal_enabled=visual,
            note_visual_mode="off", note_max_images=0, note_image_min_gap_seconds=0,
        ) if visual is not None else None
        use_case = GenerateVideoSummary(
            media_processor=self.media, transcriber=self.asr, transcript_enhancer=self.enhancer,
            summarizer=self.summarizer, artifact_store=TemporaryGenerationArtifactStore(),
            ai_summary_runner=runner.run if runner else None,
        )
        root.mkdir(parents=True)
        config = root / "settings.toml"
        config.write_text((Path(__file__).resolve().parents[4] / "config" / "settings.toml.example").read_text(encoding="utf-8"), encoding="utf-8")
        self.workflow = RecordingWorkflow(root, VideoSummaryApplication(settings=load_settings(config, root), use_case=use_case))
        self.generator = SqlBackedVideoSummaryGenerator(workspace=self.workspace, workflow=self.workflow, temp_root=root / "tasks")

    def run(self, reporter=None):
        asyncio.run(self.generator.run(series_id=self.series_id, video_id=self.video_id, progress_reporter=reporter))

    def transcript_text(self):
        return self.workspace.get_video_transcript(self.series_id, self.video_id).segments[0].text


@pytest.mark.parametrize("outcome", ["failed", "cancelled"])
def test_new_job_after_failure_or_cancellation_reuses_completed_stages(stored_video, tmp_path, outcome):
    from backend.video_summary.infrastructure.in_memory_progress_tracker import InMemoryProgressTracker

    first = Pipeline(stored_video, tmp_path / "first-host", outcome=outcome)
    reporter = InMemoryProgressTracker().create_reporter("cache-test")
    expected = GenerateCancelledError if outcome == "cancelled" else RuntimeError
    with pytest.raises(expected):
        first.run(reporter)
    assert first.workspace.get_video_summary(first.series_id, first.video_id) is None
    assert first.workspace.get_video_transcript(first.series_id, first.video_id) is None
    assert not first.workflow.output_dirs[0].exists()
    assert (first.media.audio_calls, first.asr.calls, first.enhancer.calls) == (1, 1, 1)

    second = Pipeline(stored_video, tmp_path / "restarted-host")
    second.run()
    assert (second.media.audio_calls, second.asr.calls, second.enhancer.calls) == (0, 0, 0)
    assert second.transcript_text() == "enhancer-1:asr-1:test video"
    assert second.summarizer.calls == 1
    assert first.workflow.output_dirs[0] != second.workflow.output_dirs[0]
    assert not second.workflow.output_dirs[0].exists()


def test_successful_jobs_reuse_preprocessing_but_generate_new_summary(stored_video, tmp_path):
    first = Pipeline(stored_video, tmp_path / "first-host")
    first.run()
    second = Pipeline(stored_video, tmp_path / "second-host")
    second.run()
    assert (second.media.audio_calls, second.asr.calls, second.enhancer.calls) == (0, 0, 0)
    assert second.summarizer.calls == 1
    assert second.workspace.get_video_summary(second.series_id, second.video_id).title == "second-host"
    assert second.transcript_text() == first.transcript_text()
    assert all(not directory.exists() for directory in first.workflow.output_dirs + second.workflow.output_dirs)


@pytest.mark.parametrize("failed_stage", ["asr", "enhancer"])
def test_retry_reuses_only_stages_that_finished_before_the_failure(stored_video, tmp_path, failed_stage):
    first = Pipeline(stored_video, tmp_path / "first-host")
    getattr(first, failed_stage).fail = True
    with pytest.raises(RuntimeError):
        first.run()
    second = Pipeline(stored_video, tmp_path / "second-host")
    second.run()
    assert second.media.audio_calls == 0
    assert second.asr.calls == (1 if failed_stage == "asr" else 0)
    assert second.enhancer.calls == 1
    assert second.transcript_text() == "enhancer-1:asr-1:test video"


@pytest.mark.parametrize("changed", ["video", "asr", "enhancer"])
def test_only_stages_affected_by_input_changes_are_recomputed(stored_video, tmp_path, changed):
    first = Pipeline(stored_video, tmp_path / "first-host")
    first.run()
    if changed == "video":
        first.workspace.get_video_source(first.series_id, first.video_id).source_path.write_bytes(b"replacement video")
    asr_model = "asr-2" if changed == "asr" else "asr-1"
    enhancer_model = "enhancer-2" if changed == "enhancer" else "enhancer-1"
    second = Pipeline(stored_video, tmp_path / "second-host", asr_model=asr_model, enhancer_model=enhancer_model)
    second.run()
    assert second.media.audio_calls == (1 if changed == "video" else 0)
    assert second.asr.calls == (0 if changed == "enhancer" else 1)
    assert second.enhancer.calls == 1
    source_text = "replacement video" if changed == "video" else "test video"
    assert second.transcript_text() == f"{enhancer_model}:{asr_model}:{source_text}"


@pytest.mark.parametrize("replace_video", [False, True])
def test_failed_visual_generation_keeps_frames_and_invalidates_them_when_video_changes(stored_video, tmp_path, replace_video):
    first = Pipeline(stored_video, tmp_path / "first-host", visual=True, fail_visual=True)
    with pytest.raises(RuntimeError):
        first.run()
    assert first.media.frame_calls == 3
    assert not first.workflow.output_dirs[0].exists()
    if replace_video:
        first.workspace.get_video_source(first.series_id, first.video_id).source_path.write_bytes(b"replacement video")
    second = Pipeline(stored_video, tmp_path / "second-host", visual=True)
    second.run()
    assert second.media.frame_calls == (3 if replace_video else 0)
    assert second.note.calls == 1
    assert second.note.frames
    assert second.workspace.get_video_ai_summary(second.series_id, second.video_id).content == "Generated content"


def test_disabled_visual_processing_generates_notes_without_reading_video_frames(stored_video, tmp_path):
    pipeline = Pipeline(stored_video, tmp_path / "host", visual=False)
    pipeline.run()
    assert pipeline.media.frame_calls == 0
    assert pipeline.note.frames == []
    assert pipeline.note.calls == 1
    assert pipeline.workspace.get_video_ai_summary(pipeline.series_id, pipeline.video_id).content == "Generated content"
