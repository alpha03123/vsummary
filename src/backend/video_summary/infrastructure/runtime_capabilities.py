"""检测本机可用于本地推理的硬件能力。"""

from __future__ import annotations

from dataclasses import dataclass
import platform
import subprocess


@dataclass(frozen=True)
class RuntimeCapabilities:
    """设置页与配置校验共用的本机运行能力快照。"""

    platform: str
    accelerator: str
    nvidia_cuda_available: bool
    faster_whisper_available: bool
    gpu_embedding_available: bool
    unavailable_reason: str | None


def detect_runtime_capabilities() -> RuntimeCapabilities:
    """检测当前进程能否使用项目的 NVIDIA CUDA 加速链路。

    faster-whisper 与 FastEmbed 的 GPU 实现均依赖 CUDAExecutionProvider 或 CUDA，
    因而只有检测到可用 NVIDIA runtime 时才暴露对应选项。macOS 与 AMD-only
    Windows 机器会明确标识为不支持，而不是在运行转写时才报错。
    """
    system_name = platform.system().lower()
    nvidia_cuda_available = _is_nvidia_cuda_available()
    accelerator = _detect_accelerator(system_name, nvidia_cuda_available)
    local_cuda_available = nvidia_cuda_available and system_name != "darwin"
    unavailable_reason = None if local_cuda_available else _build_unavailable_reason(system_name, accelerator)
    return RuntimeCapabilities(
        platform=system_name,
        accelerator=accelerator,
        nvidia_cuda_available=nvidia_cuda_available,
        faster_whisper_available=local_cuda_available,
        gpu_embedding_available=local_cuda_available,
        unavailable_reason=unavailable_reason,
    )


def _is_nvidia_cuda_available() -> bool:
    try:
        completed = subprocess.run(
            ["nvidia-smi"],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
    except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
        return False
    return completed.returncode == 0 and "NVIDIA-SMI" in completed.stdout


def _detect_accelerator(system_name: str, nvidia_cuda_available: bool) -> str:
    if system_name == "darwin":
        return "apple"
    if nvidia_cuda_available:
        return "nvidia"
    if system_name == "windows" and _has_amd_display_adapter():
        return "amd"
    return "unknown"


def _has_amd_display_adapter() -> bool:
    try:
        completed = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                "(Get-CimInstance Win32_VideoController).Name",
            ],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
    except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
        return False
    adapters = completed.stdout.lower()
    return completed.returncode == 0 and ("amd" in adapters or "radeon" in adapters)


def _build_unavailable_reason(system_name: str, accelerator: str) -> str:
    if system_name == "darwin":
        return "macOS 不支持项目当前的 CUDA 加速链路；请使用 whisper.cpp，检索模型请选择 CPU 或自动。"
    if accelerator == "amd":
        return "检测到 AMD 显卡；项目当前的 faster-whisper 与 FastEmbed GPU 仅支持 NVIDIA CUDA。请使用 whisper.cpp，检索模型请选择 CPU 或自动。"
    return "未检测到可用 NVIDIA CUDA runtime；faster-whisper 与 FastEmbed GPU 不可用。"
