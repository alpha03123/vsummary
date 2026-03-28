from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from app.video_summary_pipeline import VideoSummaryPipeline
from infra.faster_whisper_transcriber import FasterWhisperTranscriber
from infra.openai_summarizer import OpenAIResponsesClient
from infra.sensevoice import SenseVoiceTranscriber
from infra.settings import load_settings
from infra.whisper_cpp import WhisperCppTranscriber, resolve_whisper_executable


def main() -> None:
    sample_dir = ROOT / "sample"
    sample_files = sorted(path for path in sample_dir.glob("*") if path.is_file())
    if not sample_files:
        raise SystemExit("sample/ has no video files.")

    video_path = sample_files[0]
    output_dir = sample_dir / "output" / video_path.stem
    config_path = ROOT / "config" / "settings.yaml"
    if not config_path.exists():
        raise SystemExit("config/settings.yaml is missing.")
    settings = load_settings(config_path=config_path, root_dir=ROOT)
    base_url = os.environ.get("OPENAI_BASE_URL", settings.openai.base_url)
    model = os.environ.get("OPENAI_MODEL", settings.openai.model)

    if settings.asr.provider == "whisper_cpp":
        executable_path = resolve_whisper_executable(settings.asr.whisper_cpp)
        transcriber = WhisperCppTranscriber(
            executable_path=executable_path,
            model_path=settings.asr.whisper_cpp.model_path,
            language=settings.asr.language,
        )
    elif settings.asr.provider == "faster_whisper":
        executable_path = None
        transcriber = FasterWhisperTranscriber(
            model_size=settings.asr.faster_whisper.model_size,
            device=settings.asr.faster_whisper.device,
            compute_type=settings.asr.faster_whisper.compute_type,
            language=settings.asr.language,
        )
    elif settings.asr.provider == "sensevoice":
        executable_path = None
        transcriber = SenseVoiceTranscriber(
            model_id=settings.asr.sensevoice.model_id,
            device=settings.asr.sensevoice.device,
        )
    else:
        raise SystemExit(f"Unsupported ASR provider: {settings.asr.provider}")

    summarizer = OpenAIResponsesClient(model=model, base_url=base_url)
    pipeline = VideoSummaryPipeline(transcriber=transcriber, summarizer=summarizer)
    summary = pipeline.run(video_path=video_path, output_dir=output_dir)

    print(f"视频: {video_path}")
    print(f"输出目录: {output_dir}")
    print(f"ASR Provider: {settings.asr.provider}")
    print(f"模型: {model}")
    print(f"接口: {base_url}")
    if settings.asr.provider == "whisper_cpp":
        print(f"设备: {settings.asr.whisper_cpp.device}")
        print(f"执行文件: {executable_path}")
    elif settings.asr.provider == "faster_whisper":
        print(f"设备: {settings.asr.faster_whisper.device}")
        print(f"ASR 模型: {settings.asr.faster_whisper.model_size}")
        print(f"compute_type: {settings.asr.faster_whisper.compute_type}")
    else:
        print(f"设备: {settings.asr.sensevoice.device}")
        print(f"ASR 模型: {settings.asr.sensevoice.model_id}")
    print(f"总结文件: {output_dir / 'summary.md'}")
    print()
    print(summary.markdown[:1200])


if __name__ == "__main__":
    main()
