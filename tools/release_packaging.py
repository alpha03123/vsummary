from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Literal


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


@dataclass(frozen=True)
class ReleaseArtifact:
    name: str
    role: Literal["app", "runtime", "full"]
    url: str
    sha256: str
    size: int
    variant: str | None = None
    runtime_id: str | None = None


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


def build_runtime_id(
    *,
    kind: str,
    repo_root: Path,
    dependency_files: tuple[Path, ...],
    digest_length: int = 12,
) -> str:
    digest = hashlib.sha256()
    for dependency_file in dependency_files:
        path = repo_root / dependency_file
        if not path.is_file():
            raise FileNotFoundError(path)
        digest.update(str(dependency_file).replace("\\", "/").encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return f"runtime-{kind}-{digest.hexdigest()[:digest_length]}"


def build_release_manifest(*, version: str, assets: list[ReleaseArtifact]) -> dict[str, object]:
    manifest: dict[str, object] = {
        "schema_version": 1,
        "version": version,
        "app": {},
        "runtime": {},
        "full": {},
    }
    runtime_assets: dict[str, object] = {}
    full_assets: dict[str, object] = {}

    for asset in assets:
        payload = {
            "name": asset.name,
            "url": asset.url,
            "sha256": asset.sha256,
            "size": asset.size,
        }
        if asset.role == "app":
            manifest["app"] = {"version": version, **payload}
            continue
        if not asset.variant:
            raise ValueError(f"{asset.role} artifact requires variant: {asset.name}")
        if asset.role == "runtime":
            if not asset.runtime_id:
                raise ValueError(f"runtime artifact requires runtime_id: {asset.name}")
            runtime_assets[asset.variant] = {"id": asset.runtime_id, **payload}
            continue
        if asset.role == "full":
            full_assets[asset.variant] = payload
            continue
        raise ValueError(f"unsupported artifact role: {asset.role}")

    manifest["runtime"] = runtime_assets
    manifest["full"] = full_assets
    return manifest


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
            'set "PATH=%ROOT%\\runtime;%ROOT%\\runtime\\Library\\bin;%ROOT%\\runtime\\Scripts;%PATH%"',
            'set "PYTHONPATH=%ROOT%\\src"',
            "",
            "start \"\" http://127.0.0.1:4173",
            'call "%ROOT%\\runtime\\python.exe" -m backend.api.http.server --host 127.0.0.1 --port 4173',
            "if errorlevel 1 pause",
        ]
    )
