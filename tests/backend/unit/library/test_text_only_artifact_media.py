import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from backend.video_summary.library.models import GeneratedVideoAiNoteDTO, TranscriptSegmentDTO, VideoTranscriptDTO
from backend.video_summary.library.usecases.ai_summary import GenerateVideoAiSummary
from backend.video_summary.library.usecases.knowledge_cards import GenerateVideoKnowledgeCards
from backend.video_summary.library.usecases.mindmap_generation import GenerateVideoMindmapFromLibrary


def test_text_only_artifacts_do_not_materialize_media_or_load_saved_frames():
    workspace=Mock()
    workspace.get_video_source.side_effect=AssertionError('Text-only generation must not copy media.')
    workspace.get_video_ai_summary_visual_evidence.side_effect=AssertionError('Visual input is disabled.')
    workspace.get_video_summary.return_value=SimpleNamespace(title='Video',summary={'chapters':[]})
    workspace.get_video_transcript.return_value=VideoTranscriptDTO('series','video','Video',10,
        [TranscriptSegmentDTO(0,10,'Content')])
    mindmap=SimpleNamespace(run=AsyncMock())
    cards=SimpleNamespace(arun=AsyncMock(return_value=[]))
    note=SimpleNamespace(arun_ai_summary=AsyncMock(return_value=GeneratedVideoAiNoteDTO(
        content='Text-only note',note_visual_mode='off',note_max_images=0,note_image_min_gap_seconds=0)))
    saved=Mock(side_effect=AssertionError('Text-only generation must not load visual files.'))
    asyncio.run(GenerateVideoMindmapFromLibrary(workspace,mindmap,visual_input='none',saved_visual_paths=saved).run('series','video'))
    asyncio.run(GenerateVideoKnowledgeCards(workspace,cards,visual_input='none',saved_visual_paths=saved).arun('series','video'))
    asyncio.run(GenerateVideoAiSummary(workspace,note,multimodal_enabled=False,saved_visual_context=saved).arun('series','video'))
    assert 'visual_frame_paths' not in mindmap.run.call_args.kwargs
    assert 'visual_frame_paths' not in cards.arun.call_args.kwargs
    assert note.arun_ai_summary.call_args.kwargs['visual_context'].frames == []
