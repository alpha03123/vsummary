"""文件系统工具：原子写入与键控锁管理。

提供跨平台的文件原子写入与基于字符串键的细粒度锁管理，供视频库落盘、
JSON 制品写入等场景使用。
"""

from __future__ import annotations

import os
import threading
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4


def atomic_write_text(path: Path, content: str, *, encoding: str = "utf-8") -> None:
    """将文本原子性地写入文件。

    先把内容写入同目录下的临时文件，再通过 ``os.replace`` 原子替换到目标路径，
    确保写入过程中不会出现部分写入或损坏的文件；若目标目录不存在则自动创建。

    Args:
        path: 目标文件路径。
        content: 待写入的文本内容。
        encoding: 文件编码，默认 ``"utf-8"``。
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        temp_path.write_text(content, encoding=encoding)
        os.replace(temp_path, path)
    finally:
        if temp_path.exists():
            temp_path.unlink()


class KeyedLockManager:
    """基于字符串键的细粒度锁管理器。

    为每个 key 维护一个独立的可重入锁（``threading.RLock``），相同 key
    的操作互斥、不同 key 的操作可并行，适合按系列 ID / 视频 ID 等字符串
    维度控制并发访问的场景。

    关键不变量：每个 key 对应的 RLock 只创建一次，后续相同 key 返回同一实例。
    """

    def __init__(self) -> None:
        self._guard = threading.Lock()
        self._locks: dict[str, threading.RLock] = {}

    @contextmanager
    def hold(self, key: str):
        """获取指定 key 的锁并持有到上下文退出。

        用法::

            with manager.hold("series-123"):
                # 对 series-123 的互斥操作

        Args:
            key: 锁的字符串键；不同 key 的锁互不干扰。
        """
        lock = self._get_lock(key)
        with lock:
            yield

    def _get_lock(self, key: str) -> threading.RLock:
        """获取或创建指定 key 的可重入锁。

        全局 ``_guard`` 保证 key→lock 映射的创建是线程安全的；
        已存在的 key 直接返回已有实例。

        Args:
            key: 锁的字符串键。

        Returns:
            与该 key 绑定的 ``threading.RLock`` 实例。
        """
        with self._guard:
            lock = self._locks.get(key)
            if lock is None:
                lock = threading.RLock()
                self._locks[key] = lock
            return lock
