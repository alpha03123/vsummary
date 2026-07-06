from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path

from tests import _path_setup  # noqa: F401


def _load_diagnose_gpu_module():
    script_path = Path(__file__).resolve().parents[4] / "diagnose_gpu.py"
    spec = importlib.util.spec_from_file_location("diagnose_gpu", script_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("failed to load diagnose_gpu.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class DiagnoseGpuScriptTests(unittest.TestCase):
    def test_resolves_package_root_from_script_path(self) -> None:
        module = _load_diagnose_gpu_module()

        script_path = Path("C:/tools/vsummary-gpu/diagnose_gpu.py")

        self.assertEqual(module.resolve_package_root(script_path), Path("C:/tools/vsummary-gpu"))

    def test_collects_runtime_dll_dirs_from_packaged_runtime_layout(self) -> None:
        module = _load_diagnose_gpu_module()

        runtime_root = Path("C:/tools/vsummary-gpu/runtime")

        self.assertEqual(
            module.collect_runtime_dll_dir_candidates(runtime_root),
            [
                runtime_root,
                runtime_root / "Library" / "bin",
                runtime_root / "Scripts",
                runtime_root / "Lib" / "site-packages" / "nvidia" / "*" / "bin",
                runtime_root / "nvidia" / "*" / "bin",
                runtime_root / "Lib" / "site-packages" / "onnxruntime" / "capi",
                runtime_root / "Lib" / "site-packages" / "ctranslate2",
            ],
        )

    def test_vc_runtime_probe_includes_cpp_runtime_dlls(self) -> None:
        module = _load_diagnose_gpu_module()

        self.assertIn("vcruntime140.dll", module.VC_RUNTIME_DLLS)
        self.assertIn("vcruntime140_1.dll", module.VC_RUNTIME_DLLS)
        self.assertIn("msvcp140.dll", module.VC_RUNTIME_DLLS)

    def test_cuda_provider_result_requires_cuda_execution_provider(self) -> None:
        module = _load_diagnose_gpu_module()

        self.assertEqual(module.classify_cuda_provider(["CUDAExecutionProvider"]), "ok")
        self.assertEqual(module.classify_cuda_provider(["CPUExecutionProvider"]), "missing")
        self.assertEqual(module.classify_cuda_provider([]), "missing")

    def test_detects_onnxruntime_gpu_cuda13_mismatch_with_cuda12_runtime(self) -> None:
        module = _load_diagnose_gpu_module()

        self.assertTrue(module.is_cuda13_onnxruntime_gpu_with_cuda12_runtime("1.27.0", ["nvidia-cublas-cu12"]))
        self.assertFalse(module.is_cuda13_onnxruntime_gpu_with_cuda12_runtime("1.26.0", ["nvidia-cublas-cu12"]))
        self.assertFalse(module.is_cuda13_onnxruntime_gpu_with_cuda12_runtime("1.27.0", ["nvidia-cublas-cu13"]))

    def test_reads_bom_prefixed_json_files(self) -> None:
        module = _load_diagnose_gpu_module()

        with tempfile.TemporaryDirectory() as temp_dir:
            json_path = Path(temp_dir) / "installed.json"
            json_path.write_text('{"variant": "gpu"}', encoding="utf-8-sig")

            self.assertEqual(module.read_json_file(json_path), {"variant": "gpu"})


if __name__ == "__main__":
    unittest.main()
