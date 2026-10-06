import asyncio
import json
from pathlib import Path
import sys
import subprocess
from threading import Event, Timer

import pytest
from backend.shared.subprocess_cancellation import watch_process_cancellation
from backend.video_summary.domain.models import VideoAsset, Transcript, TranscriptSegment
from backend.video_summary.generation.cancellation import GenerationCancellationContext, cancellable_await
from backend.video_summary.generation.usecases.generate_summary import GenerateCancelledError
from backend.video_summary.infrastructure.concurrent_ai_summary_runner import ConcurrentAiSummaryRunner
from backend.video_summary.infrastructure.llm.litellm_note_generator import LiteLLMNoteGenerator


def test_cancel_interrupts_async_llm_without_waiting_for_result_or_writing_artifacts(tmp_path):
    async def scenario():
        class Gateway:
            def __init__(self):
                self.started=asyncio.Event();self.cancelled=False;self.calls=0
            async def acomplete_structured(self,*args,**kwargs):
                self.calls+=1;self.started.set()
                try:await asyncio.sleep(60)
                except asyncio.CancelledError:
                    self.cancelled=True;raise
        gateway=Gateway()
        runner=ConcurrentAiSummaryRunner(generator=LiteLLMNoteGenerator(gateway),max_input_images=1,
            multimodal_enabled=False,note_visual_mode='off',note_max_images=0,note_image_min_gap_seconds=0,media_processor=None)
        cancellation=GenerationCancellationContext('test')
        video=VideoAsset(source_path=tmp_path/'video.mp4',title='test',duration_seconds=10)
        transcript=Transcript(language='zh',segments=[TranscriptSegment(0,10,'测试内容')])
        task=asyncio.create_task(cancellable_await(runner.run(video=video,transcript=transcript,output_dir=tmp_path,cache_dir=tmp_path),cancellation))
        await gateway.started.wait()
        cancellation.request_cancel()
        with pytest.raises(GenerateCancelledError):await asyncio.wait_for(task,0.5)
        assert gateway.cancelled and gateway.calls==1
        assert not (tmp_path/'ai_summary.json').exists()
        assert json.loads((tmp_path/'ai_summary.status.json').read_text())['status']=='cancelled'
    asyncio.run(scenario())


def test_already_cancelled_context_never_starts_request():
    async def scenario():
        called=[]
        async def request():called.append(True)
        context=GenerationCancellationContext('test');context.request_cancel()
        with pytest.raises(GenerateCancelledError):await cancellable_await(request(),context)
        assert called==[]
    asyncio.run(scenario())


def test_silent_download_process_is_cancelled_without_stdout():
    requested=Event()
    process=subprocess.Popen([sys.executable,'-c','import time; time.sleep(60)'],stdout=subprocess.PIPE,text=True)
    timer=Timer(0.1,requested.set);timer.start()
    try:
        with watch_process_cancellation(process,requested.is_set) as cancelled:
            assert process.stdout.read()==''
            process.wait(timeout=1)
            assert cancelled.is_set()
    finally:
        timer.cancel()
        if process.poll() is None:process.kill()
        process.wait()


def test_actual_async_gateway_closes_http_request_on_cancel(monkeypatch):
    from backend.shared.llm import LiteLLMCompletionGateway
    monkeypatch.setenv('NO_PROXY','127.0.0.1,localhost')
    async def scenario():
        entered, disconnected=asyncio.Event(),asyncio.Event()
        calls=[]
        async def serve(reader, writer):
            try:
                header=await reader.readuntil(b'\r\n\r\n')
                length=next(int(line.split(b':',1)[1]) for line in header.split(b'\r\n') if line.lower().startswith(b'content-length:'))
                await reader.readexactly(length)
                calls.append(True);entered.set()
                assert await reader.read()==b''
                disconnected.set()
            finally:
                writer.close();await writer.wait_closed()
        server=await asyncio.start_server(serve,'127.0.0.1',0)
        async with server:
            port=server.sockets[0].getsockname()[1]
            gateway=LiteLLMCompletionGateway(provider='openai',model='gpt-4o',base_url=f'http://127.0.0.1:{port}/v1',api_key='local-test')
            task=asyncio.create_task(gateway.acomplete_text([{'role':'user','content':'test'}]))
            await asyncio.wait_for(entered.wait(),10)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):await asyncio.wait_for(task,1)
            await asyncio.wait_for(disconnected.wait(),2)
            assert calls==[True]
    asyncio.run(scenario())
