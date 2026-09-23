"""本地 MySQL 凭据：Windows DPAPI 或 macOS 登录钥匙串。"""

from __future__ import annotations

import base64
import ctypes
import os
import sys
from ctypes import wintypes
from pathlib import Path

from backend.shared.filesystem import atomic_write_text


CRYPTPROTECT_UI_FORBIDDEN = 0x1


class LocalCredentialError(RuntimeError):
    """本地数据库凭据无法安全保存或读取。"""


class _DataBlob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_byte))]


def save_local_mysql_password(path: Path, password: str) -> None:
    """将密码保存到当前用户的平台凭据存储。"""

    if not password:
        raise ValueError("MySQL password cannot be empty.")
    if sys.platform == "darwin":
        _keychain_password(path, password)
        # This file is only a reference; the password stays in the login keychain.
        atomic_write_text(path, "VSummary MySQL login keychain credential\n")
        return
    encrypted = _protect(password.encode("utf-8"))
    atomic_write_text(path, base64.b64encode(encrypted).decode("ascii") + "\n")


def load_local_mysql_password(path: Path) -> str:
    """读取由 :func:`save_local_mysql_password` 保存的平台凭据。"""

    if not path.is_file():
        raise LocalCredentialError("Managed MySQL credentials are missing.")
    if sys.platform == "darwin":
        return _keychain_password(path)
    try:
        encrypted = base64.b64decode(path.read_text(encoding="ascii").strip(), validate=True)
    except Exception as error:
        raise LocalCredentialError("Managed MySQL credentials are invalid.") from error
    try:
        return _unprotect(encrypted).decode("utf-8")
    except UnicodeDecodeError as error:
        raise LocalCredentialError("Managed MySQL credentials contain invalid text.") from error


def _keychain_password(path: Path, password: str | None = None) -> str:
    """Access the login keychain without placing passwords in process arguments."""
    security = ctypes.CDLL("/System/Library/Frameworks/Security.framework/Security")
    core = ctypes.CDLL("/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation")
    pointer = ctypes.c_void_p
    uint = ctypes.c_uint32
    security.SecKeychainFindGenericPassword.argtypes = [
        pointer, uint, ctypes.c_char_p, uint, ctypes.c_char_p,
        ctypes.POINTER(uint), ctypes.POINTER(pointer), ctypes.POINTER(pointer),
    ]
    security.SecKeychainAddGenericPassword.argtypes = [
        pointer, uint, ctypes.c_char_p, uint, ctypes.c_char_p, uint, pointer, ctypes.POINTER(pointer),
    ]
    security.SecKeychainItemModifyAttributesAndData.argtypes = [pointer, pointer, uint, pointer]
    security.SecKeychainItemFreeContent.argtypes = [pointer, pointer]
    core.CFRelease.argtypes = [pointer]
    core.CFRelease.restype = None
    service = b"VSummary MySQL"
    account = str(path.resolve()).encode("utf-8")
    identity = (None, len(service), service, len(account), account)
    if password is not None:
        value = password.encode("utf-8")
        status = security.SecKeychainAddGenericPassword(*identity, len(value), value, None)
        if status == -25299:  # errSecDuplicateItem
            item = pointer()
            status = security.SecKeychainFindGenericPassword(*identity, None, None, ctypes.byref(item))
            _check_keychain_status(status)
            try:
                status = security.SecKeychainItemModifyAttributesAndData(item, None, len(value), value)
            finally:
                core.CFRelease(item)
        _check_keychain_status(status)
        return ""
    length, data = uint(), pointer()
    status = security.SecKeychainFindGenericPassword(*identity, ctypes.byref(length), ctypes.byref(data), None)
    _check_keychain_status(status)
    try:
        return ctypes.string_at(data, length.value).decode("utf-8")
    finally:
        security.SecKeychainItemFreeContent(None, data)


def _check_keychain_status(status: int) -> None:
    if status != 0:
        raise LocalCredentialError(f"Cannot access the VSummary MySQL password in the macOS login keychain (status {status}).")


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
