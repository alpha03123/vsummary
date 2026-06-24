"""基于 faster-whisper 的本地 ASR 转写器实现。

负责把音频文件按段转写为领域 `Transcript`，并处理：
- device 解析（`auto` / `cpu` / `gpu`，依赖 `nvidia-smi` 探测）；
- Windows 下 CUDA DLL 路径注册（避免 ctranslate2 找不到 cublas/cudnn）；
- 按 `transcription_mode` 选择 beam_size 等解码参数；
- 通过 `on_progress` 回调实时上报按时间计算的进度比例。
"""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path
from typing import Callable

from backend.video_summary.domain.models import Transcript, TranscriptSegment

_CUDA_DLL_HANDLES: list[object] = []
_CUDA_DLL_DIRS_READY = False


class FasterWhisperTranscriber:
    """faster-whisper 转写器：在 GPU/CPU 上把音频转写为 `Transcript` 段。

    业务目的：单视频生成流程的核心步骤之一，把 16kHz 单声道音频切成带时间戳
    的段落供后续总结/检索使用。本类在构造时就把模型加载到内存，因此调用方
    通常以"全局单例/单 process 持有"的方式复用。

    Attributes:
        cache_identity: 由类名 + 关键参数（模型、设备、计算精度、转写模式、语言）
            拼接而成的字符串，用于上层判断"两个转写器实例是否可复用 cache"。
    """

    def __init__(
        self,
        model_size: str,
        device: str,
        compute_type: str,
        transcription_mode: str,
        language: str = "zh",
    ) -> None:
        """加载 faster-whisper 模型并预编译解码参数。

        Args:
            model_size: 模型标识或本地模型目录路径；由
                `FasterWhisperModelManager.resolve_model_source` 提供。
            device: 设备标识，取值 `auto` / `cpu` / `gpu` / `cuda`。
            compute_type: faster-whisper 计算精度（如 `int8` / `float16`）。
            transcription_mode: 转写模式，决定 beam_size 等解码参数
                （见 `_build_decode_options`）。
            language: 强制指定的语言代码，默认 `zh`。

        Raises:
            RuntimeError: faster-whisper 未安装，或要求 GPU 但未检测到 NVIDIA runtime。
        """
        resolved_device = _resolve_device(device)
        if resolved_device == "cuda":
            _ensure_windows_cuda_dll_dirs()

        self.cache_identity = "|".join(
            [
                type(self).__module__,
                type(self).__qualname__,
                str(model_size),
                resolved_device,
                compute_type,
                transcription_mode,
                language,
            ]
        )
        try:
            from faster_whisper import WhisperModel
        except ImportError as error:
            raise RuntimeError("faster-whisper is not installed.") from error

        self._language = language
        self._decode_options = _build_decode_options(transcription_mode)
        self._model = WhisperModel(
            model_size,
            device=resolved_device,
            compute_type=compute_type,
        )

    def transcribe(
        self,
        audio_path: Path,
        output_stem: Path,
        on_progress: Callable[[float], None] | None = None,
    ) -> Transcript:
        """把音频文件转写为带时间戳的段落集合。

        关键行为：
        - 自动开启 VAD 过滤静音段；
        - 跳过空文本段；
        - 若提供了 `on_progress`，每读到一个 segment 会按
          `segment.end / info.duration` 报告一次 0~1 的进度比例；
        - 写入路径由 `output_stem` 决定，本方法只确保 `output_stem.parent` 存在，
          实际写盘由调用方负责。

        Args:
            audio_path: 待转写的音频文件路径（建议为 16kHz 单声道 WAV，由
                `FfmpegMediaProcessor.extract_audio` 预先生成）。
            output_stem: 用于定位输出目录的"目标路径前缀"，本方法只会确保其
                父目录存在。
            on_progress: 进度回调，参数为 `0~1` 的浮点进度。

        Returns:
            包含语言与 `TranscriptSegment` 列表的领域 `Transcript`。
        """
        output_stem.parent.mkdir(parents=True, exist_ok=True)
        segments_iter, info = self._model.transcribe(
            str(audio_path),
            language=self._language,
            vad_filter=True,
            **self._decode_options,
        )
        total_duration = getattr(info, "duration", None)
        segments = []
        for segment in segments_iter:
            if not segment.text.strip():
                continue
            segments.append(
                TranscriptSegment(
                    start_seconds=float(segment.start),
                    end_seconds=float(segment.end),
                    text=segment.text.strip(),
                ),
            )
            if on_progress is not None and total_duration:
                on_progress(float(segment.end) / float(total_duration))
        return Transcript(language=getattr(info, "language", self._language), segments=segments)


def _resolve_device(device: str) -> str:
    """把 settings 中的设备字符串归一化为 faster-whisper 接受的 `cuda` / `cpu`。

    `auto` 时调用 `nvidia-smi` 探测 NVIDIA runtime 是否可用；`gpu` / `cuda`
    时强制要求可用，否则抛 `RuntimeError`；其余值一律回落为 `cpu`。
    """
    if device == "auto":
        return "cuda" if _is_nvidia_gpu_available() else "cpu"
    if device in {"gpu", "cuda"}:
        if not _is_nvidia_gpu_available():
            raise RuntimeError("GPU mode requested, but NVIDIA runtime is not available.")
        return "cuda"
    return "cpu"


def _is_nvidia_gpu_available() -> bool:
    """通过 `nvidia-smi` 命令探测 NVIDIA 驱动是否可用。

    Returns:
        `nvidia-smi` 命令返回成功且 stdout 中包含 `NVIDIA-SMI` 时返回 `True`；
        命令不存在、退出码非零或解析失败时返回 `False`。
    """
    try:
        import subprocess

        result = subprocess.run(
            ["nvidia-smi"],
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        return False
    return "NVIDIA-SMI" in result.stdout


def _ensure_windows_cuda_dll_dirs() -> None:
    """在 Windows 下把 nvidia 包的 `bin/` 目录加入 DLL 搜索路径。

    解决 ctranslate2 在打包/精简环境里找不到 `cublas` / `cudnn` 动态库的问题：
    - 通过 `os.add_dll_directory` 注册（Python 3.8+）；
    - 同时把这些目录 prepend 到 `PATH`，覆盖子进程场景。

    全局只执行一次（`_CUDA_DLL_DIRS_READY` 哨兵）。
    """
    global _CUDA_DLL_DIRS_READY

    if _CUDA_DLL_DIRS_READY or sys.platform != "win32" or not hasattr(os, "add_dll_directory"):
        return

    candidates = _discover_nvidia_bin_dirs()

    existing_path_entries = os.environ.get("PATH", "").split(os.pathsep)
    prepended_entries: list[str] = []

    for path in candidates:
        if not path.exists():
            continue

        resolved = str(path)
        _CUDA_DLL_HANDLES.append(os.add_dll_directory(resolved))
        if resolved not in existing_path_entries and resolved not in prepended_entries:
            prepended_entries.append(resolved)

    if prepended_entries:
        os.environ["PATH"] = os.pathsep.join([*prepended_entries, *existing_path_entries])

    _CUDA_DLL_DIRS_READY = True


def _discover_nvidia_bin_dirs() -> list[Path]:
    """枚举已安装 nvidia 包（cublas / cudnn / cuda_nvrtc / cuda_runtime）的 `bin/` 目录。

    Returns:
        去重后的 `bin/` 路径列表；若某个 nvidia 包未安装则静默跳过。
    """
    package_names = (
        "nvidia.cublas",
        "nvidia.cudnn",
        "nvidia.cuda_nvrtc",
        "nvidia.cuda_runtime",
    )
    candidates: list[Path] = []
    for package_name in package_names:
        try:
            spec = importlib.util.find_spec(package_name)
        except ModuleNotFoundError:
            continue
        locations = getattr(spec, "submodule_search_locations", None)
        if not locations:
            continue
        for location in locations:
            bin_dir = Path(location) / "bin"
            if bin_dir.exists() and bin_dir not in candidates:
                candidates.append(bin_dir)
    return candidates


def _build_decode_options(transcription_mode: str) -> dict[str, object]:
    """根据 `transcription_mode` 构造 faster-whisper 的解码参数。

    模式：
        - `accurate`：beam_size=5，多温度重采样，启用 `condition_on_previous_text`；
        - `balanced`：beam_size=3，单温度，确定性解码；
        - `fast`（默认/未知）：beam_size=1，不引用上文，最快。

    Args:
        transcription_mode: 模式名，大小写不敏感；未知值走 fast 路径。

    Returns:
        将被 `WhisperModel.transcribe` 解包为关键字参数的 dict。
    """
    if transcription_mode == "accurate":
        return {
            "beam_size": 5,
            "best_of": 5,
            "condition_on_previous_text": True,
            "temperature": [0.0, 0.2, 0.4, 0.6, 0.8, 1.0],
        }
    if transcription_mode == "balanced":
        return {
            "beam_size": 3,
            "best_of": 3,
            "condition_on_previous_text": True,
            "temperature": 0.0,
        }
    return {
        "beam_size": 1,
        "best_of": 1,
        "condition_on_previous_text": False,
        "temperature": 0.0,
    }
