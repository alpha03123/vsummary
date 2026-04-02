from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from backend.video_summary.bootstrap import load_video_summary_application


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
    application = load_video_summary_application(
        config_path=config_path,
        root_dir=ROOT,
        base_url=os.environ.get("OPENAI_BASE_URL"),
        model=os.environ.get("OPENAI_MODEL"),
    )
    summary = application.use_case.run(video_path=video_path, output_dir=output_dir)

    print(f"视频: {video_path}")
    print(f"输出目录: {output_dir}")
    print(f"ASR Provider: {application.runtime.asr.provider}")
    print(f"设备: {application.runtime.asr.device}")
    print(f"ASR 模型: {application.runtime.asr.model_label}")
    print(f"模型: {application.runtime.model}")
    print(f"接口: {application.runtime.base_url}")
    if application.runtime.asr.executable_path is not None:
        print(f"执行文件: {application.runtime.asr.executable_path}")
    if application.settings.asr.provider == "faster_whisper":
        print(f"compute_type: {application.settings.asr.faster_whisper.compute_type}")
    print(f"总结文件: {output_dir / 'summary.md'}")
    print()
    print(summary.markdown[:1200])


if __name__ == "__main__":
    main()
