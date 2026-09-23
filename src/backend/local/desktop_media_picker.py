"""本机媒体文件选择器。"""

from __future__ import annotations

from pathlib import Path
import subprocess
import sys
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
    if sys.platform == "darwin":
        # AppKit/Tk cannot create windows on FastAPI's worker thread. Let a
        # separate macOS process own the native file dialog instead.
        return _select_macos_media(initial_directory, allow_multiple)
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


def _select_macos_media(initial_directory: Path | None, allow_multiple: bool) -> list[str]:
    script = '''
on run argv
    try
        set folderPath to item 1 of argv
        set multipleFiles to (item 2 of argv is "true")
        if folderPath is "" then
            set selectedFiles to choose file with prompt "选择媒体文件" multiple selections allowed multipleFiles
        else
            set selectedFiles to choose file with prompt "选择媒体文件" default location (POSIX file folderPath) multiple selections allowed multipleFiles
        end if
        if class of selectedFiles is not list then set selectedFiles to {selectedFiles}
        set paths to {}
        repeat with selectedFile in selectedFiles
            set end of paths to POSIX path of selectedFile
        end repeat
        set AppleScript's text item delimiters to linefeed
        return paths as text
    on error number -128
        return ""
    end try
end run
'''
    with _PICKER_LOCK:
        result = subprocess.run(
            ["/usr/bin/osascript", "-e", script, str(initial_directory or ""), str(allow_multiple).lower()],
            capture_output=True, text=True, check=False,
        )
    if result.returncode != 0:
        raise RuntimeError("macOS 无法打开媒体文件选择框。")
    return result.stdout.rstrip("\n").splitlines()
