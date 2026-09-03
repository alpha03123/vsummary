"""本机媒体文件选择器。"""

from __future__ import annotations

from pathlib import Path
from threading import Lock


_PICKER_LOCK = Lock()
_FILE_TYPES = [
    ("媒体文件", "*.mp4 *.mov *.mkv *.avi *.webm *.m4v *.mp3 *.wav *.m4a *.aac *.flac *.ogg *.opus *.wma"),
    ("所有文件", "*.*"),
]


def select_local_media_paths(
    *,
    initial_directory: Path | None = None,
    allow_multiple: bool = True,
) -> list[str]:
    """打开系统文件选择框，返回用户确认的绝对媒体路径。"""
    try:
        import tkinter as tk
        from tkinter import filedialog
    except ImportError as error:
        raise RuntimeError("当前运行环境不支持本机文件选择。") from error

    with _PICKER_LOCK:
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        try:
            picker = filedialog.askopenfilenames if allow_multiple else filedialog.askopenfilename
            selected_paths = picker(
                title="选择媒体文件" if allow_multiple else "重新链接媒体文件",
                filetypes=_FILE_TYPES,
                parent=root,
                **({"initialdir": str(initial_directory)} if initial_directory is not None else {}),
            )
        finally:
            root.destroy()

    if isinstance(selected_paths, str):
        selected_paths = [selected_paths] if selected_paths else []
    return [str(Path(path).resolve()) for path in selected_paths]
