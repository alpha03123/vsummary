"""Windows DPAPI 保护的本地 MySQL 凭据存储。"""

from __future__ import annotations

import base64
import ctypes
import os
from ctypes import wintypes
from pathlib import Path

from backend.shared.filesystem import atomic_write_text


CRYPTPROTECT_UI_FORBIDDEN = 0x1


class LocalCredentialError(RuntimeError):
    """本地数据库凭据无法安全保存或读取。"""


class _DataBlob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_byte))]


def save_local_mysql_password(path: Path, password: str) -> None:
    """使用当前 Windows 用户的 DPAPI 保存数据库密码。"""

    if not password:
        raise ValueError("MySQL password cannot be empty.")
    encrypted = _protect(password.encode("utf-8"))
    atomic_write_text(path, base64.b64encode(encrypted).decode("ascii") + "\n")


def load_local_mysql_password(path: Path) -> str:
    """读取并解密由 :func:`save_local_mysql_password` 保存的密码。"""

    if not path.is_file():
        raise LocalCredentialError("Managed MySQL credentials are missing.")
    try:
        encrypted = base64.b64decode(path.read_text(encoding="ascii").strip(), validate=True)
    except Exception as error:
        raise LocalCredentialError("Managed MySQL credentials are invalid.") from error
    try:
        return _unprotect(encrypted).decode("utf-8")
    except UnicodeDecodeError as error:
        raise LocalCredentialError("Managed MySQL credentials contain invalid text.") from error


def _protect(value: bytes) -> bytes:
    _require_windows()
    source_buffer = ctypes.create_string_buffer(value)
    source = _DataBlob(len(value), ctypes.cast(source_buffer, ctypes.POINTER(ctypes.c_byte)))
    result = _DataBlob()
    if not ctypes.windll.crypt32.CryptProtectData(
        ctypes.byref(source),
        "VSummary local MySQL password",
        None,
        None,
        None,
        CRYPTPROTECT_UI_FORBIDDEN,
        ctypes.byref(result),
    ):
        raise LocalCredentialError(f"Windows DPAPI encryption failed: {ctypes.get_last_error()}")
    try:
        return ctypes.string_at(result.pbData, result.cbData)
    finally:
        _free_dpapi_buffer(result.pbData)


def _unprotect(value: bytes) -> bytes:
    _require_windows()
    source_buffer = ctypes.create_string_buffer(value)
    source = _DataBlob(len(value), ctypes.cast(source_buffer, ctypes.POINTER(ctypes.c_byte)))
    result = _DataBlob()
    if not ctypes.windll.crypt32.CryptUnprotectData(
        ctypes.byref(source),
        None,
        None,
        None,
        None,
        CRYPTPROTECT_UI_FORBIDDEN,
        ctypes.byref(result),
    ):
        raise LocalCredentialError(f"Windows DPAPI decryption failed: {ctypes.get_last_error()}")
    try:
        return ctypes.string_at(result.pbData, result.cbData)
    finally:
        _free_dpapi_buffer(result.pbData)


def _free_dpapi_buffer(pointer: ctypes.POINTER(ctypes.c_byte)) -> None:
    if pointer:
        ctypes.windll.kernel32.LocalFree(pointer)


def _require_windows() -> None:
    if os.name != "nt":
        raise LocalCredentialError("Managed local MySQL credentials require Windows DPAPI.")
