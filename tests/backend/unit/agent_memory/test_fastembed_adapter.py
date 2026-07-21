from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.video_summary.infrastructure.rag.agent_memory import fastembed_adapter
from backend.video_summary.infrastructure.rag.agent_memory.fastembed_adapter import FastEmbedEmbedding


class FastEmbedEmbeddingTests(unittest.TestCase):
    def test_uses_fastembed_for_text_and_query_embeddings(self) -> None:
        with patch(
            "backend.video_summary.infrastructure.rag.agent_memory.fastembed_adapter._load_text_embedding_cls",
            return_value=_FakeTextEmbedding,
        ):
            embedding = FastEmbedEmbedding(
                model_name="BAAI/bge-small-zh-v1.5",
                device="cpu",
                embed_batch_size=2,
                cache_dir="data/models/fastembed",
            )

            self.assertEqual(_FakeTextEmbedding.created[-1]["cache_dir"], "data/models/fastembed")
            self.assertEqual(embedding._get_query_embedding("问题"), [2.0, 3.0])
            self.assertEqual(embedding._get_text_embeddings(["a", "abcd"]), [[1.0, 2.0], [4.0, 5.0]])

    def test_gpu_device_uses_cuda_provider_without_cpu_fallback(self) -> None:
        _FakeTextEmbedding.created = []
        _FakeTextEmbedding.active_providers = ["CUDAExecutionProvider", "CPUExecutionProvider"]
        with (
            patch(
                "backend.video_summary.infrastructure.rag.agent_memory.fastembed_adapter._load_text_embedding_cls",
                return_value=_FakeTextEmbedding,
            ),
            patch("backend.video_summary.infrastructure.rag.agent_memory.fastembed_adapter._prepare_cuda_runtime") as prepare,
        ):
            FastEmbedEmbedding(model_name="model", device="gpu", embed_batch_size=4)

        self.assertEqual(_FakeTextEmbedding.created[-1]["providers"], ["CUDAExecutionProvider"])
        self.assertNotIn("cuda", _FakeTextEmbedding.created[-1]["kwargs"])
        prepare.assert_called_once_with()

    def test_gpu_device_rejects_cpu_fallback(self) -> None:
        _FakeTextEmbedding.created = []
        _FakeTextEmbedding.active_providers = ["CPUExecutionProvider"]
        with (
            patch(
                "backend.video_summary.infrastructure.rag.agent_memory.fastembed_adapter._load_text_embedding_cls",
                return_value=_FakeTextEmbedding,
            ),
            patch("backend.video_summary.infrastructure.rag.agent_memory.fastembed_adapter._prepare_cuda_runtime"),
        ):
            with self.assertRaisesRegex(RuntimeError, "CUDAExecutionProvider 未激活"):
                FastEmbedEmbedding(model_name="model", device="gpu", embed_batch_size=4)

    def test_cuda_dll_dirs_precede_system_cuda_path_idempotently(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            package_dirs = [root / "runtime" / "nvidia" / name / "bin" for name in ("cublas", "cudnn")]
            for path in package_dirs:
                path.mkdir(parents=True)
            system_cuda_dir = root / "system-cuda" / "bin"
            system_cuda_dir.mkdir(parents=True)

            with (
                patch.object(fastembed_adapter, "_iter_python_environment_cuda_dll_dirs", return_value=package_dirs),
                patch.dict(os.environ, {"PATH": os.pathsep.join([str(system_cuda_dir), str(package_dirs[0])])}, clear=True),
            ):
                fastembed_adapter._prepend_python_environment_cuda_dll_dirs_to_path()
                first_path = os.environ["PATH"]
                fastembed_adapter._prepend_python_environment_cuda_dll_dirs_to_path()
                self.assertEqual(os.environ["PATH"], first_path)
                self.assertEqual(
                    first_path.split(os.pathsep),
                    [str(package_dirs[0]), str(package_dirs[1]), str(system_cuda_dir)],
                )


class _FakeTextEmbedding:
    created = []
    active_providers = ["CPUExecutionProvider"]

    def __init__(self, *, model_name: str, cache_dir=None, providers=None, cuda=False, **kwargs) -> None:
        self.created.append(
            {
                "model_name": model_name,
                "cache_dir": cache_dir,
                "providers": providers,
                "cuda": cuda,
                "kwargs": kwargs,
            }
        )
        self.model = _FakeFastEmbedInnerModel(self.active_providers)

    def embed(self, texts, batch_size=256):
        del batch_size
        for text in texts:
            yield [float(len(text)), float(len(text) + 1)]

    def query_embed(self, query):
        return iter([[float(len(query)), float(len(query) + 1)]])


class _FakeFastEmbedInnerModel:
    def __init__(self, active_providers: list[str]) -> None:
        self.model = _FakeOnnxSession(active_providers)


class _FakeOnnxSession:
    def __init__(self, active_providers: list[str]) -> None:
        self._active_providers = active_providers

    def get_providers(self) -> list[str]:
        return self._active_providers


if __name__ == "__main__":
    unittest.main()
