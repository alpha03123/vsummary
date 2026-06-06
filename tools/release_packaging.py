from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class PackageVariant:
    kind: str
    environment_file: Path
    settings_template: Path
    environment_name: str


@dataclass(frozen=True)
class ReleaseLayout:
    pack_root: Path
    build_root: Path
    runtime_root: Path
    package_root: Path


PACKAGE_VARIANTS: dict[str, PackageVariant] = {
    "cpu": PackageVariant(
        kind="cpu",
        environment_file=Path("scripts/package/environment.cpu.yml"),
        settings_template=Path("scripts/package/settings.cpu.toml"),
        environment_name="vsummary-pack-cpu",
    ),
    "gpu": PackageVariant(
        kind="gpu",
        environment_file=Path("scripts/package/environment.gpu.yml"),
        settings_template=Path("scripts/package/settings.gpu.toml"),
        environment_name="vsummary-pack-gpu",
    ),
}


def build_release_layout(*, repo_root: Path, pack_root: Path, kind: str) -> ReleaseLayout:
    _ = repo_root
    normalized_pack_root = pack_root.resolve(strict=False)
    build_root = normalized_pack_root / "_build" / kind
    return ReleaseLayout(
        pack_root=normalized_pack_root,
        build_root=build_root,
        runtime_root=build_root / "runtime",
        package_root=normalized_pack_root / f"vsummary-{kind}",
    )


def render_start_bat() -> str:
    return "\n".join(
        [
            "@echo off",
            "setlocal",
            "",
            'set "ROOT=%~dp0"',
            'if "%ROOT:~-1%"=="\\" set "ROOT=%ROOT:~0,-1%"',
            'cd /d "%ROOT%"',
            'if not exist "%ROOT%\\.env" copy /y "%ROOT%\\.env.example" "%ROOT%\\.env" >nul',
            'set "HF_HOME=%ROOT%\\data\\huggingface"',
            'set "HUGGINGFACE_HUB_CACHE=%ROOT%\\data\\huggingface\\hub"',
            'set "PLAYWRIGHT_BROWSERS_PATH=%ROOT%\\data\\playwright-browsers"',
            'set "PATH=%ROOT%\\runtime;%ROOT%\\runtime\\Library\\bin;%ROOT%\\runtime\\Scripts;%PATH%"',
            'set "PYTHONPATH=%ROOT%\\src"',
            "",
            "start \"\" http://127.0.0.1:4173",
            'call "%ROOT%\\runtime\\python.exe" -m uvicorn backend.api.app:app --host 127.0.0.1 --port 4173',
            "if errorlevel 1 pause",
        ]
    )
