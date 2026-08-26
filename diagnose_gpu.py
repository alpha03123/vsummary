from __future__ import annotations

import ctypes
import glob
import importlib.util
import importlib.metadata
import json
import os
import platform
import shutil
import subprocess
import sys
import traceback
from pathlib import Path


REQUIRED_GPU_PACKAGES = (
    "onnxruntime-gpu",
    "fastembed-gpu",
    "nvidia-cublas-cu12",
    "nvidia-cuda-nvrtc-cu12",
    "nvidia-cuda-runtime-cu12",
    "nvidia-cudnn-cu12",
    "nvidia-cufft-cu12",
    "nvidia-curand-cu12",
)
OPTIONAL_RUNTIME_PACKAGES = (
    "faster-whisper",
    "ctranslate2",
)
CPU_PACKAGE_CONFLICTS = (
    "onnxruntime",
    "fastembed",
)
VC_RUNTIME_DLLS = (
    "vcruntime140.dll",
    "vcruntime140_1.dll",
    "msvcp140.dll",
    "concrt140.dll",
)
NVIDIA_DRIVER_DLLS = (
    "nvcuda.dll",
    "nvml.dll",
)
CRITICAL_CUDA_DLLS = (
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
ONNXRUNTIME_PROVIDER_DLLS = (
    "onnxruntime_providers_shared.dll",
    "onnxruntime_providers_cuda.dll",
)


class Reporter:
    def __init__(self) -> None:
        self.lines: list[str] = []
        self.failed = False
        self.warned = False

    def line(self, text: str = "") -> None:
        print(text)
        self.lines.append(text)

    def section(self, title: str) -> None:
        self.line()
        self.line(f"== {title} ==")

    def check(self, label: str, status: str, detail: str = "") -> None:
        normalized = status.upper()
        if normalized == "FAIL":
            self.failed = True
        if normalized == "WARN":
            self.warned = True
        suffix = f" - {detail}" if detail else ""
        self.line(f"[{normalized}] {label}{suffix}")

    def write_log(self, path: Path) -> None:
        path.write_text("\n".join(self.lines) + "\n", encoding="utf-8")


def resolve_package_root(script_path: Path) -> Path:
    return Path(script_path).resolve().parent


def collect_nvidia_bin_dir_candidates(runtime_root: Path) -> list[Path]:
    return [
        runtime_root / "Lib" / "site-packages" / "nvidia" / "*" / "bin",
        runtime_root / "nvidia" / "*" / "bin",
    ]


def classify_cuda_provider(providers: list[str]) -> str:
    return "ok" if "CUDAExecutionProvider" in providers else "missing"


def is_cuda13_onnxruntime_gpu_with_cuda12_runtime(
    onnxruntime_gpu_version: str,
    installed_package_names: list[str],
) -> bool:
    major_minor = _parse_major_minor_version(onnxruntime_gpu_version)
    if major_minor < (1, 27):
        return False
    normalized_names = {name.lower() for name in installed_package_names}
    has_cuda12_runtime = any(name.endswith("-cu12") for name in normalized_names)
    has_cuda13_runtime = any(name.endswith("-cu13") for name in normalized_names)
    return has_cuda12_runtime and not has_cuda13_runtime


def _parse_major_minor_version(version: str) -> tuple[int, int]:
    parts = version.split(".")
    if len(parts) < 2:
        return (0, 0)
    try:
        return (int(parts[0]), int(parts[1]))
    except ValueError:
        return (0, 0)


def main() -> int:
    root = resolve_package_root(Path(__file__))
    reporter = Reporter()
    dll_handles: list[object] = []

    reporter.line("VSummary GPU runtime diagnosis")
    reporter.line(f"package_root: {root}")
    reporter.line(f"python: {sys.executable}")
    reporter.line(f"python_version: {sys.version.replace(os.linesep, ' ')}")
    reporter.line(f"platform: {platform.platform()}")

    try:
        _report_system(reporter)
        _report_environment(reporter)
        _report_package_state(root, reporter)
        runtime_root = root / "runtime"
        _report_runtime_python(root, runtime_root, reporter)
        dll_dirs = _prepare_runtime_path(runtime_root, dll_handles, reporter)
        _report_packages(reporter)
        _report_import_locations(reporter)
        _report_cpp_runtime(reporter)
        _report_nvidia_driver_dlls(reporter)
        _report_nvidia_smi(reporter)
        _report_cuda_dlls(dll_dirs, reporter)
        _report_onnxruntime_provider_dlls(dll_dirs, reporter)
        _report_onnxruntime(reporter)
        _report_ctranslate2(reporter)
        _report_fastembed_gpu_session(root, reporter)
        _report_conclusion(reporter)
    except Exception:
        reporter.failed = True
        reporter.section("Unexpected error")
        reporter.line(traceback.format_exc())
    finally:
        log_path = root / "gpu_diagnose.log"
        reporter.write_log(log_path)
        reporter.line()
        reporter.line(f"log_written: {log_path}")

    return 1 if reporter.failed else 0


def _report_system(reporter: Reporter) -> None:
    reporter.section("System")
    reporter.line(f"machine: {platform.machine()}")
    reporter.line(f"python_architecture: {platform.architecture()[0]}")
    reporter.line(f"is_64bit_python: {sys.maxsize > 2**32}")
    reporter.line(f"processor: {platform.processor() or 'unknown'}")
    if sys.platform == "win32":
        reporter.line(f"windows_version: {platform.version()}")
        reporter.line(f"is_admin: {_is_windows_admin()}")


def _is_windows_admin() -> str:
    try:
        return str(bool(ctypes.windll.shell32.IsUserAnAdmin()))
    except Exception as error:
        return f"unknown ({error!r})"


def _report_environment(reporter: Reporter) -> None:
    reporter.section("Environment")
    for name in (
        "CUDA_PATH",
        "CUDA_PATH_V12_0",
        "CUDA_VISIBLE_DEVICES",
        "CONDA_PREFIX",
        "VIRTUAL_ENV",
        "PYTHONPATH",
        "HF_HOME",
        "HUGGINGFACE_HUB_CACHE",
    ):
        reporter.line(f"{name}: {os.environ.get(name, '<unset>')}")
    path_entries = [entry for entry in os.environ.get("PATH", "").split(os.pathsep) if entry]
    reporter.line("PATH first entries:")
    for entry in path_entries[:12]:
        reporter.line(f"  {entry}")


def _report_package_state(root: Path, reporter: Reporter) -> None:
    reporter.section("Package")
    runtime_id_path = root / "RUNTIME"
    installed_state_path = root / "updater" / "installed.json"

    if runtime_id_path.is_file():
        reporter.check("RUNTIME file", "OK", runtime_id_path.read_text(encoding="utf-8").strip())
    else:
        reporter.check("RUNTIME file", "WARN", "missing")

    if not installed_state_path.is_file():
        reporter.check("installed state", "WARN", "updater/installed.json missing")
        return

    payload = read_json_file(installed_state_path)
    variant = str(payload.get("variant", "")).strip().lower()
    runtime_id = str(payload.get("runtime_id", "")).strip()
    detail = f"variant={variant or 'unknown'}, runtime_id={runtime_id or 'unknown'}"
    if variant == "gpu":
        reporter.check("package variant", "OK", detail)
    else:
        reporter.check("package variant", "FAIL", detail)


def read_json_file(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _report_runtime_python(root: Path, runtime_root: Path, reporter: Reporter) -> None:
    reporter.section("Runtime Python")
    runtime_python = (runtime_root / "python.exe").resolve()
    current_python = Path(sys.executable).resolve()
    if runtime_python.is_file():
        reporter.check("runtime/python.exe exists", "OK", str(runtime_python))
    else:
        reporter.check("runtime/python.exe exists", "FAIL", str(runtime_python))

    if sys.maxsize > 2**32:
        reporter.check("64-bit Python", "OK")
    else:
        reporter.check("64-bit Python", "FAIL", "GPU runtime requires 64-bit Python")

    if current_python == runtime_python:
        reporter.check("running packaged Python", "OK")
    else:
        reporter.check(
            "running packaged Python",
            "FAIL",
            f"use: {runtime_python} {root / 'diagnose_gpu.py'}",
        )


def _prepare_runtime_path(runtime_root: Path, dll_handles: list[object], reporter: Reporter) -> list[Path]:
    reporter.section("DLL search path")
    candidates = _expand_dll_dir_candidates(collect_runtime_dll_dir_candidates(runtime_root))
    existing = _unique_existing_dirs(candidates)
    if not existing:
        reporter.check("runtime DLL directories", "FAIL", "no existing directories found")
        return []

    old_path = os.environ.get("PATH", "")
    os.environ["PATH"] = os.pathsep.join([*(str(path) for path in existing), old_path])
    for dll_dir in existing:
        if hasattr(os, "add_dll_directory"):
            try:
                dll_handles.append(os.add_dll_directory(str(dll_dir)))
            except OSError as error:
                reporter.check("add_dll_directory", "WARN", f"{dll_dir}: {error}")
                continue
        reporter.line(str(dll_dir))

    reporter.check("runtime DLL directories", "OK", f"{len(existing)} directories")
    return existing


def collect_runtime_dll_dir_candidates(runtime_root: Path) -> list[Path]:
    return [
        runtime_root,
        runtime_root / "Library" / "bin",
        runtime_root / "Scripts",
        runtime_root / "Lib" / "site-packages" / "nvidia" / "*" / "bin",
        runtime_root / "nvidia" / "*" / "bin",
        runtime_root / "Lib" / "site-packages" / "onnxruntime" / "capi",
        runtime_root / "Lib" / "site-packages" / "ctranslate2",
    ]


def collect_nvidia_bin_dir_candidates(runtime_root: Path) -> list[Path]:
    return [
        runtime_root / "Lib" / "site-packages" / "nvidia" / "*" / "bin",
        runtime_root / "nvidia" / "*" / "bin",
    ]


def _expand_dll_dir_candidates(candidates: list[Path]) -> list[Path]:
    matches: list[Path] = []
    for candidate in candidates:
        if "*" in str(candidate):
            matches.extend(Path(path) for path in glob.glob(str(candidate)) if Path(path).is_dir())
        else:
            matches.append(candidate)
    return matches


def _unique_existing_dirs(paths: list[Path]) -> list[Path]:
    seen: set[Path] = set()
    result: list[Path] = []
    for path in paths:
        if "*" in str(path):
            continue
        if not path.is_dir():
            continue
        resolved = path.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        result.append(resolved)
    return result


def _report_packages(reporter: Reporter) -> None:
    reporter.section("Python packages")
    installed_package_names: list[str] = []
    onnxruntime_gpu_version: str | None = None
    for package_name in (*REQUIRED_GPU_PACKAGES, *OPTIONAL_RUNTIME_PACKAGES):
        version = _package_version(package_name)
        if version is None:
            status = "FAIL" if package_name in REQUIRED_GPU_PACKAGES else "WARN"
            reporter.check(package_name, status, "missing")
        else:
            installed_package_names.append(package_name)
            if package_name == "onnxruntime-gpu":
                onnxruntime_gpu_version = version
            location = _package_location(package_name)
            detail = f"{version}; {location}" if location else version
            reporter.check(package_name, "OK", detail)

    for package_name in CPU_PACKAGE_CONFLICTS:
        version = _package_version(package_name)
        if version is not None:
            reporter.check(package_name, "WARN", f"CPU package also installed: {version}")

    if onnxruntime_gpu_version is not None and is_cuda13_onnxruntime_gpu_with_cuda12_runtime(
        onnxruntime_gpu_version,
        installed_package_names,
    ):
        reporter.check(
            "onnxruntime-gpu CUDA runtime compatibility",
            "FAIL",
            f"onnxruntime-gpu {onnxruntime_gpu_version} requires CUDA 13 provider DLL dependencies, "
            "but this package bundles CUDA 12 runtime packages; rebuild with onnxruntime-gpu <1.27",
        )


def _package_version(package_name: str) -> str | None:
    try:
        return importlib.metadata.version(package_name)
    except importlib.metadata.PackageNotFoundError:
        return None


def _package_location(package_name: str) -> str:
    try:
        distribution = importlib.metadata.distribution(package_name)
    except importlib.metadata.PackageNotFoundError:
        return ""
    location = getattr(distribution, "_path", None)
    if location is None:
        return ""
    return str(Path(location).parent)


def _report_import_locations(reporter: Reporter) -> None:
    reporter.section("Import locations")
    for module_name in (
        "onnxruntime",
        "fastembed",
        "faster_whisper",
        "ctranslate2",
        "numpy",
    ):
        spec = importlib.util.find_spec(module_name)
        if spec is None:
            reporter.check(module_name, "WARN", "module not importable")
        else:
            reporter.check(module_name, "OK", spec.origin or "namespace package")


def _report_cpp_runtime(reporter: Reporter) -> None:
    reporter.section("VC++ runtime")
    for dll_name in VC_RUNTIME_DLLS:
        result = _load_library_by_name(dll_name)
        if result is None:
            where = _where_first(dll_name)
            detail = where or "LoadLibrary failed and where.exe found nothing"
            reporter.check(dll_name, "FAIL", detail)
        else:
            reporter.check(dll_name, "OK", result)
        all_matches = _where_all(dll_name)
        if len(all_matches) > 1:
            reporter.line(f"{dll_name} where_all: {all_matches}")


def _report_nvidia_driver_dlls(reporter: Reporter) -> None:
    reporter.section("NVIDIA driver DLLs")
    for dll_name in NVIDIA_DRIVER_DLLS:
        result = _load_library_by_name(dll_name)
        if result is None:
            reporter.check(dll_name, "WARN", "LoadLibrary failed")
        else:
            reporter.check(dll_name, "OK", result)
        all_matches = _where_all(dll_name)
        if all_matches:
            reporter.line(f"{dll_name} where_all: {all_matches}")


def _load_library_by_name(dll_name: str) -> str | None:
    try:
        _load_dynamic_library(dll_name)
    except Exception:
        return None
    return _where_first(dll_name) or "LoadLibrary succeeded"


def _load_dynamic_library(path: str) -> object:
    loader = getattr(ctypes, "WinDLL", ctypes.CDLL)
    return loader(path)


def _where_first(name: str) -> str:
    matches = _where_all(name)
    return matches[0] if matches else ""


def _where_all(name: str) -> list[str]:
    if sys.platform != "win32":
        return []
    try:
        result = subprocess.run(
            ["where.exe", name],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=8,
        )
    except Exception:
        return []
    if result.returncode != 0:
        return []
    return result.stdout.strip().splitlines() if result.stdout.strip() else []


def _report_nvidia_smi(reporter: Reporter) -> None:
    reporter.section("NVIDIA driver")
    nvidia_smi = shutil.which("nvidia-smi")
    if nvidia_smi is None:
        reporter.check("nvidia-smi", "FAIL", "command not found")
        return

    result = subprocess.run(
        [nvidia_smi],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=15,
    )
    output = (result.stdout or result.stderr).strip()
    first_line = output.splitlines()[0] if output else ""
    if result.returncode == 0 and "NVIDIA-SMI" in output:
        reporter.check("nvidia-smi", "OK", first_line)
        _report_nvidia_smi_query(nvidia_smi, reporter)
    else:
        reporter.check("nvidia-smi", "FAIL", first_line or f"exit_code={result.returncode}")


def _report_nvidia_smi_query(nvidia_smi: str, reporter: Reporter) -> None:
    result = subprocess.run(
        [
            nvidia_smi,
            "--query-gpu=name,driver_version,memory.total",
            "--format=csv,noheader",
        ],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=15,
    )
    if result.returncode != 0:
        reporter.check("nvidia-smi query", "WARN", (result.stderr or "").strip())
        return
    for line in result.stdout.strip().splitlines():
        reporter.line(f"gpu: {line}")


def _report_cuda_dlls(dll_dirs: list[Path], reporter: Reporter) -> None:
    reporter.section("CUDA DLLs")
    missing: list[str] = []
    for dll_name in CRITICAL_CUDA_DLLS:
        dll_path = _find_dll(dll_dirs, dll_name)
        if dll_path is None:
            missing.append(dll_name)
            reporter.check(dll_name, "FAIL", "not found")
        else:
            reporter.check(dll_name, "OK", str(dll_path))
            load_error = _try_load_dll(dll_path)
            if load_error:
                reporter.check(f"LoadLibrary {dll_name}", "FAIL", load_error)
            else:
                reporter.check(f"LoadLibrary {dll_name}", "OK")

    if not missing:
        reporter.check("critical CUDA DLLs", "OK")


def _find_dll(dll_dirs: list[Path], dll_name: str) -> Path | None:
    normalized = dll_name.lower()
    for dll_dir in dll_dirs:
        direct = dll_dir / dll_name
        if direct.is_file():
            return direct
        for child in dll_dir.glob("*.dll"):
            if child.name.lower() == normalized:
                return child
    return None


def _try_load_dll(dll_path: Path) -> str:
    try:
        _load_dynamic_library(str(dll_path))
    except Exception as error:
        return repr(error)
    return ""


def _report_onnxruntime_provider_dlls(dll_dirs: list[Path], reporter: Reporter) -> None:
    reporter.section("ONNX Runtime provider DLLs")
    for dll_name in ONNXRUNTIME_PROVIDER_DLLS:
        dll_path = _find_dll(dll_dirs, dll_name)
        if dll_path is None:
            reporter.check(dll_name, "FAIL", "not found")
            continue
        reporter.check(dll_name, "OK", str(dll_path))
        load_error = _try_load_dll(dll_path)
        if load_error:
            reporter.check(f"LoadLibrary {dll_name}", "WARN", load_error)
        else:
            reporter.check(f"LoadLibrary {dll_name}", "OK")


def _report_onnxruntime(reporter: Reporter) -> None:
    reporter.section("ONNX Runtime")
    try:
        import onnxruntime as ort
    except Exception as error:
        reporter.check("import onnxruntime", "FAIL", repr(error))
        return

    reporter.check("import onnxruntime", "OK", getattr(ort, "__file__", "unknown"))
    reporter.line(f"onnxruntime_version: {getattr(ort, '__version__', 'unknown')}")
    try:
        providers = [str(provider) for provider in ort.get_available_providers()]
    except Exception as error:
        reporter.check("get_available_providers", "FAIL", repr(error))
        return

    reporter.line(f"available_providers: {providers}")
    if classify_cuda_provider(providers) == "ok":
        reporter.check("CUDAExecutionProvider", "OK")
    else:
        reporter.check("CUDAExecutionProvider", "FAIL", "not in available_providers")

    try:
        device = ort.get_device()
    except Exception as error:
        reporter.check("ort.get_device", "WARN", repr(error))
    else:
        reporter.line(f"ort_device: {device}")


def _report_ctranslate2(reporter: Reporter) -> None:
    reporter.section("CTranslate2 / faster-whisper")
    try:
        import ctranslate2
    except Exception as error:
        reporter.check("import ctranslate2", "FAIL", repr(error))
    else:
        reporter.check("import ctranslate2", "OK", getattr(ctranslate2, "__file__", "unknown"))
        reporter.line(f"ctranslate2_version: {getattr(ctranslate2, '__version__', 'unknown')}")
        get_cuda_device_count = getattr(ctranslate2, "get_cuda_device_count", None)
        if callable(get_cuda_device_count):
            try:
                reporter.line(f"ctranslate2_cuda_device_count: {get_cuda_device_count()}")
            except Exception as error:
                reporter.check("ctranslate2 CUDA probe", "WARN", repr(error))
        get_supported_compute_types = getattr(ctranslate2, "get_supported_compute_types", None)
        if callable(get_supported_compute_types):
            for device in ("cpu", "cuda"):
                try:
                    types = sorted(str(value) for value in get_supported_compute_types(device))
                except Exception as error:
                    reporter.check(f"ctranslate2 compute types {device}", "WARN", repr(error))
                else:
                    reporter.line(f"ctranslate2_compute_types_{device}: {types}")

    try:
        import faster_whisper
    except Exception as error:
        reporter.check("import faster_whisper", "FAIL", repr(error))
    else:
        reporter.check("import faster_whisper", "OK", getattr(faster_whisper, "__file__", "unknown"))


def _report_fastembed_gpu_session(root: Path, reporter: Reporter) -> None:
    """按应用实际配置创建 FastEmbed GPU session，验证 CUDA Provider 真能落地。"""
    reporter.section("FastEmbed GPU session")
    model_name = "BAAI/bge-small-zh-v1.5"
    cache_dir = root / "data" / "models" / "fastembed"
    if not cache_dir.is_dir():
        reporter.check("FastEmbed GPU session", "WARN", f"model cache missing: {cache_dir}")
        return

    source_root = root / "src"
    if source_root.is_dir():
        sys.path.insert(0, str(source_root))

    try:
        from backend.video_summary.infrastructure.rag.agent_memory.fastembed_adapter import build_fastembed_embedding

        embedding = build_fastembed_embedding(
            model_name=model_name,
            device="gpu",
            embed_batch_size=1,
            cache_dir=str(cache_dir),
        )
        providers = _resolve_fastembed_providers(embedding)
    except Exception as error:
        reporter.check("FastEmbed GPU session", "FAIL", repr(error))
        return

    reporter.check("FastEmbed GPU session", "OK", f"providers: {providers}")


def _resolve_fastembed_providers(embedding: object) -> list[str]:
    inner_model = getattr(embedding, "_embedding", None)
    model = getattr(inner_model, "model", None)
    session = getattr(model, "model", None)
    get_providers = getattr(session, "get_providers", None)
    if not callable(get_providers):
        return []
    return [str(provider) for provider in get_providers()]


def _report_conclusion(reporter: Reporter) -> None:
    reporter.section("Conclusion")
    if reporter.failed:
        reporter.line("GPU runtime is not ready. Send gpu_diagnose.log with the bug report.")
        reporter.line("Most common causes: wrong package variant, CPU wheel overwrite, missing CUDA DLLs, or NVIDIA driver not visible to this Python process.")
    elif reporter.warned:
        reporter.line("CUDAExecutionProvider is visible, but warnings above should still be reviewed.")
    else:
        reporter.line("CUDAExecutionProvider is visible to packaged Python.")


if __name__ == "__main__":
    raise SystemExit(main())
