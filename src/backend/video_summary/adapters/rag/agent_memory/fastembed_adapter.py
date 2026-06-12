from __future__ import annotations

import ctypes
import os
import site
import sys
from pathlib import Path
from typing import Any

from llama_index.core.embeddings import BaseEmbedding
from pydantic import PrivateAttr


_DLL_DIRECTORY_HANDLES: list[object] = []
_PRELOADED_CUDA_DLLS: list[object] = []
_CUDA_DLL_PRELOAD_ORDER = (
    "cublasLt64_12.dll",
    "cublas64_12.dll",
    "cufft64_11.dll",
    "cudart64_12.dll",
    "cudnn_engines_runtime_compiled64_9.dll",
    "cudnn_engines_precompiled64_9.dll",
    "cudnn_heuristic64_9.dll",
    "cudnn_ops64_9.dll",
    "cudnn_adv64_9.dll",
    "cudnn_graph64_9.dll",
    "cudnn64_9.dll",
)


class FastEmbedEmbedding(BaseEmbedding):
    device: str = "cpu"
    _embedding: Any = PrivateAttr()

    def __init__(
        self,
        *,
        model_name: str,
        device: str = "cpu",
        embed_batch_size: int = 8,
        cache_dir: str | None = None,
    ) -> None:
        super().__init__(model_name=model_name, embed_batch_size=embed_batch_size)
        self.device = _normalize_device(device)
        self._embedding = _create_text_embedding(
            model_name=model_name,
            device=self.device,
            cache_dir=cache_dir,
        )
        if self.device == "gpu":
            _require_cuda_provider(self._embedding)

    def _get_query_embedding(self, query: str) -> list[float]:
        return [float(value) for value in next(self._embedding.query_embed(query))]

    async def _aget_query_embedding(self, query: str) -> list[float]:
        return self._get_query_embedding(query)

    def _get_text_embedding(self, text: str) -> list[float]:
        return self._get_text_embeddings([text])[0]

    def _get_text_embeddings(self, texts: list[str]) -> list[list[float]]:
        return [
            [float(value) for value in embedding]
            for embedding in self._embedding.embed(texts, batch_size=self.embed_batch_size)
        ]


def build_fastembed_embedding(
    *,
    model_name: str,
    device: str,
    embed_batch_size: int,
    cache_dir: str | None = None,
) -> FastEmbedEmbedding:
    return FastEmbedEmbedding(
        model_name=model_name,
        device=device,
        embed_batch_size=embed_batch_size,
        cache_dir=cache_dir,
    )


def _create_text_embedding(*, model_name: str, device: str, cache_dir: str | None):
    if device == "gpu":
        _prepare_cuda_runtime()
    text_embedding_cls = _load_text_embedding_cls()
    kwargs: dict[str, object] = {"model_name": model_name}
    if cache_dir is not None:
        kwargs["cache_dir"] = cache_dir
        specific_model_path = _resolve_specific_model_path(model_name, Path(cache_dir))
        if specific_model_path is not None:
            kwargs["specific_model_path"] = str(specific_model_path)
    if device == "gpu":
        kwargs["providers"] = ["CUDAExecutionProvider"]
    elif device == "cpu":
        kwargs["providers"] = ["CPUExecutionProvider"]
    return text_embedding_cls(**kwargs)


def _resolve_specific_model_path(model_name: str, cache_dir: Path) -> Path | None:
    model_basename = model_name.rstrip("/").split("/")[-1]
    candidates = [
        cache_dir / f"fast-{model_basename}",
        cache_dir / model_basename,
    ]
    for candidate in candidates:
        if _is_complete_fastembed_model_dir(candidate):
            return candidate
    return None


def _is_complete_fastembed_model_dir(model_dir: Path) -> bool:
    required_files = (
        "config.json",
        "model_optimized.onnx",
        "special_tokens_map.json",
        "tokenizer_config.json",
        "tokenizer.json",
    )
    return model_dir.is_dir() and all((model_dir / name).is_file() for name in required_files)


def _require_cuda_provider(embedding) -> None:
    providers = _resolve_active_providers(embedding)
    if "CUDAExecutionProvider" not in providers:
        raise RuntimeError(
            "FastEmbed GPU 初始化失败：CUDAExecutionProvider 未激活。"
            f"当前 ONNX Runtime providers: {providers or ['unknown']}。"
        )


def _resolve_active_providers(embedding) -> list[str]:
    inner_model = getattr(embedding, "model", None)
    session = getattr(inner_model, "model", None)
    get_providers = getattr(session, "get_providers", None)
    if callable(get_providers):
        return [str(provider) for provider in get_providers()]
    return []


def _add_python_environment_cuda_dll_directories() -> None:
    if sys.platform != "win32" or not hasattr(os, "add_dll_directory"):
        return
    for dll_dir in _iter_python_environment_cuda_dll_dirs():
        try:
            _DLL_DIRECTORY_HANDLES.append(os.add_dll_directory(str(dll_dir)))
        except OSError:
            continue


def _prepare_cuda_runtime() -> None:
    if sys.platform != "win32":
        return
    _add_python_environment_cuda_dll_directories()
    _preload_python_environment_cuda_dlls()


def _preload_python_environment_cuda_dlls() -> None:
    if sys.platform != "win32":
        return
    dll_dirs = _iter_python_environment_cuda_dll_dirs()
    for dll_name in _CUDA_DLL_PRELOAD_ORDER:
        dll_path = _find_cuda_dll(dll_dirs, dll_name)
        if dll_path is None:
            continue
        _PRELOADED_CUDA_DLLS.append(ctypes.CDLL(str(dll_path)))


def _find_cuda_dll(dll_dirs: list[Path], dll_name: str) -> Path | None:
    normalized = dll_name.lower()
    for dll_dir in dll_dirs:
        dll_path = dll_dir / dll_name
        if dll_path.is_file():
            return dll_path
        for child in dll_dir.glob("*.dll"):
            if child.name.lower() == normalized:
                return child
    return None


def _iter_python_environment_cuda_dll_dirs() -> list[Path]:
    roots = [Path(sys.prefix)]
    roots.extend(Path(path) for path in site.getsitepackages())
    candidates: list[Path] = []
    for root in roots:
        candidates.extend(
            [
                root / "Library" / "bin",
                root / "Lib" / "site-packages" / "ctranslate2",
                root / "nvidia" / "cublas" / "bin",
                root / "nvidia" / "cuda_runtime" / "bin",
                root / "nvidia" / "cudnn" / "bin",
                root / "nvidia" / "cuda_nvrtc" / "bin",
                root / "nvidia" / "cufft" / "bin",
                root / "nvidia" / "curand" / "bin",
                root / "nvidia" / "cusolver" / "bin",
                root / "nvidia" / "cusparse" / "bin",
                root / "nvidia" / "nvjitlink" / "bin",
            ]
        )
    seen: set[Path] = set()
    existing: list[Path] = []
    for candidate in candidates:
        resolved = candidate.resolve()
        if resolved in seen or not resolved.is_dir():
            continue
        seen.add(resolved)
        existing.append(resolved)
    return existing


def _load_text_embedding_cls():
    try:
        from fastembed import TextEmbedding
    except ImportError as error:
        raise RuntimeError("缺少本地 embedding 依赖。请安装 fastembed 或 fastembed-gpu。") from error
    return TextEmbedding


def _normalize_device(device: str) -> str:
    normalized = (device or "cpu").strip().lower()
    if normalized == "cuda":
        return "gpu"
    if normalized == "auto":
        return "cpu"
    if normalized in {"cpu", "gpu"}:
        return normalized
    raise ValueError(f"Unsupported fastembed device: {device!r}")
