"""Windows 整合包内置 MySQL 的受管运行时。

本模块不依赖系统服务：MySQL 二进制由发布包携带，数据与凭据始终位于用户
数据目录。首次启动会初始化 data directory、创建仅限 loopback 的应用账号、
执行 schema migration；后续启动只使用 DPAPI 解密的应用账号连接。
"""

from __future__ import annotations

import json
import os
import secrets
import socket
import subprocess
import sys
import time
import ctypes
import msvcrt
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Final

from sqlalchemy import text

from backend.shared.filesystem import atomic_write_text
from backend.video_summary.infrastructure.persistence.database import (
    DatabaseDriverError,
    DatabaseOptions,
    create_database_engine,
)
from backend.local.persistence.local_credentials import (
    LocalCredentialError,
    load_local_mysql_password,
    save_local_mysql_password,
)
from backend.video_summary.infrastructure.persistence.migrate import upgrade_to_head


LOCAL_DATABASE_NAME: Final = "vsummary"
LOCAL_DATABASE_USER: Final = "vsummary_app"
RUNTIME_STATE_FILE: Final = "runtime.json"
CREDENTIAL_FILE: Final = "vsummary_app.dpapi"
STARTUP_TIMEOUT_SECONDS: Final = 30.0
RUNTIME_STATE_VERSION: Final = 1


class ManagedLocalMySqlError(RuntimeError):
    """受管 MySQL 不能安全初始化、启动或连接。"""


class ManagedLocalMySqlPathError(ManagedLocalMySqlError):
    """内置 MySQL 无法安全处理当前安装或数据路径。"""


@dataclass(frozen=True)
class ManagedLocalMySqlPaths:
    """本地数据库数据根目录的稳定布局。"""

    root: Path

    @property
    def data_dir(self) -> Path:
        return self.root / "mysql" / "data"

    @property
    def logs_dir(self) -> Path:
        return self.root / "mysql" / "logs"

    @property
    def run_dir(self) -> Path:
        return self.root / "mysql" / "run"

    @property
    def credential_path(self) -> Path:
        return self.root / "mysql" / CREDENTIAL_FILE

    @property
    def runtime_state_path(self) -> Path:
        return self.root / "mysql" / RUNTIME_STATE_FILE

    @property
    def error_log_path(self) -> Path:
        return self.logs_dir / "mysqld.err"

    @property
    def pid_path(self) -> Path:
        return self.run_dir / "mysqld.pid"

    @property
    def bootstrap_sql_path(self) -> Path:
        return self.run_dir / "bootstrap.sql"


class ManagedLocalMySql:
    """管理 VSummary 私有 MySQL 实例的生命周期。"""

    def __init__(self, *, mysql_home: Path, data_root: Path | None = None) -> None:
        self._mysql_home = mysql_home
        self._paths = ManagedLocalMySqlPaths(data_root or _default_data_root())
        self._process: subprocess.Popen[str] | None = None
        self._owns_server = False
        self._instance_lock_handle = None

    @property
    def paths(self) -> ManagedLocalMySqlPaths:
        return self._paths

    def start_and_migrate(self, *, before_migrate: Callable[[DatabaseOptions], None] | None = None) -> DatabaseOptions:
        """确保 MySQL 运行并升级 Schema，返回应用使用的连接参数。"""

        self._require_database_driver()
        self._validate_runtime_binary()
        self._validate_mysql_paths()
        self._ensure_directories()
        self._acquire_instance_lock()
        try:
            state = self._read_runtime_state()
            database_ready = False
            if state is None:
                if self._is_initialized():
                    options = self._recover_runtime_state()
                    self._bootstrap_application_account(options)
                    database_ready = True
                else:
                    options = self._bootstrap_new_instance()
                    database_ready = True
            else:
                options = self._options_from_state(state)
                self._start_existing_instance(options)
            if not database_ready:
                self._wait_for_database(options)
            if before_migrate is not None:
                before_migrate(options)
            upgrade_to_head(options)
        except Exception as error:
            self.stop()
            raise ManagedLocalMySqlError(f"Managed MySQL startup or schema migration failed: {error}") from error
        return options

    @staticmethod
    def _require_database_driver() -> None:
        try:
            # create_database_engine performs the canonical driver check.
            create_database_engine(
                DatabaseOptions(url="mysql+pymysql://driver-check:driver-check@127.0.0.1:1/driver_check")
            ).dispose()
        except DatabaseDriverError as error:
            raise ManagedLocalMySqlError(str(error)) from error

    def stop(self) -> None:
        """使用 MySQL 协议关闭实际 server 子进程，再清理启动父进程。"""

        state = self._read_runtime_state()
        if state is not None and self._owns_server:
            try:
                options = self._options_from_state(state)
                server_pid = self._read_server_pid()
                self._shutdown_server(options)
                self._wait_for_port_to_close(options.parsed_url.port)
                self._wait_for_server_exit(server_pid)
            except ManagedLocalMySqlError:
                # Cleanup must never hide the original bootstrap/migration
                # error. A later explicit recovery command can report shutdown
                # trouble after the primary failure has been surfaced.
                pass
        if self._process is not None and self._process.poll() is None:
            self._process.terminate()
            try:
                self._process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._process.kill()
                self._process.wait(timeout=5)
        self._release_instance_lock()
        self._owns_server = False

    def _bootstrap_new_instance(self) -> DatabaseOptions:
        port = _select_loopback_port()
        password = _new_password()
        options = DatabaseOptions(
            url=f"mysql+pymysql://{LOCAL_DATABASE_USER}:{password}@127.0.0.1:{port}/{LOCAL_DATABASE_NAME}"
        )
        self._initialize_data_directory()
        save_local_mysql_password(self._paths.credential_path, password)
        self._bootstrap_application_account(options)
        return options

    def _bootstrap_application_account(self, options: DatabaseOptions) -> None:
        password = options.parsed_url.password
        port = options.parsed_url.port
        if password is None or port is None:
            raise ManagedLocalMySqlError("Managed MySQL bootstrap requires complete connection options.")
        self._write_bootstrap_sql(password)
        try:
            self._start_server(port=port, init_file=self._paths.bootstrap_sql_path)
            self._wait_for_database(options)
        finally:
            self._paths.bootstrap_sql_path.unlink(missing_ok=True)
        self._write_runtime_state(port)

    def _recover_runtime_state(self) -> DatabaseOptions:
        """为已初始化、但丢失运行元数据的本地实例重建连接状态。

        `runtime.json` 缺失意味着上一次初始化可能在创建应用账号前中断。调用方必须
        使用返回的连接参数重新执行 bootstrap SQL，并且仅在连接验证成功后写入状态。
        """

        try:
            password = load_local_mysql_password(self._paths.credential_path)
        except LocalCredentialError as error:
            raise ManagedLocalMySqlError(
                "Managed MySQL data exists but its runtime state and credentials are unavailable. Restore a backup."
            ) from error
        port = _select_loopback_port()
        return DatabaseOptions(
            url=f"mysql+pymysql://{LOCAL_DATABASE_USER}:{password}@127.0.0.1:{port}/{LOCAL_DATABASE_NAME}"
        )

    def _start_existing_instance(self, options: DatabaseOptions) -> None:
        port = options.parsed_url.port
        if port is not None and _is_loopback_port_open(port):
            return
        self._start_server(port=options.parsed_url.port or 3306, init_file=None)

    def _start_server(self, *, port: int, init_file: Path | None) -> None:
        if self._process is not None and self._process.poll() is None:
            return
        arguments = [
            f"--basedir={self._mysql_home}",
            f"--datadir={self._paths.data_dir}",
            f"--port={port}",
            "--bind-address=127.0.0.1",
            "--skip-name-resolve",
            f"--lc-messages-dir={self._mysql_home / 'share'}",
            f"--log-error={self._paths.error_log_path}",
            f"--pid-file={self._paths.pid_path}",
        ]
        if init_file is not None:
            arguments.append(f"--init-file={init_file}")
        try:
            self._process = subprocess.Popen(
                [str(self._mysqld_path()), *arguments],
                cwd=str(self._mysql_home),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                text=True,
            )
            self._owns_server = True
        except OSError as error:
            raise ManagedLocalMySqlError("Managed MySQL process could not be started.") from error

    def _wait_for_database(self, options: DatabaseOptions) -> None:
        deadline = time.monotonic() + STARTUP_TIMEOUT_SECONDS
        last_error: Exception | None = None
        while time.monotonic() < deadline:
            try:
                engine = create_database_engine(options)
                with engine.connect() as connection:
                    connection.execute(text("SELECT 1"))
                engine.dispose()
                return
            except Exception as error:
                last_error = error
                time.sleep(0.25)
        error_tail = self._read_error_log_tail()
        raise ManagedLocalMySqlError(
            f"Managed MySQL did not become healthy within {STARTUP_TIMEOUT_SECONDS:.0f} seconds. {error_tail}"
        ) from last_error

    def _shutdown_server(self, options: DatabaseOptions) -> None:
        password = options.parsed_url.password
        port = options.parsed_url.port
        if password is None or port is None:
            raise ManagedLocalMySqlError("Managed MySQL shutdown requires complete connection options.")
        environment = os.environ.copy()
        environment["MYSQL_PWD"] = password
        completed = subprocess.run(
            [
                str(self._mysqladmin_path()),
                "--protocol=TCP",
                "--host=127.0.0.1",
                f"--port={port}",
                f"--user={LOCAL_DATABASE_USER}",
                "shutdown",
            ],
            cwd=str(self._mysql_home),
            env=environment,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            text=True,
            check=False,
        )
        if completed.returncode != 0:
            raise ManagedLocalMySqlError("Managed MySQL shutdown command failed.")

    @staticmethod
    def _wait_for_port_to_close(port: int | None) -> None:
        if port is None:
            raise ManagedLocalMySqlError("Managed MySQL shutdown requires a port.")
        deadline = time.monotonic() + 15.0
        while time.monotonic() < deadline:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
                probe.settimeout(0.25)
                if probe.connect_ex(("127.0.0.1", port)) != 0:
                    return
            time.sleep(0.1)
        raise ManagedLocalMySqlError("Managed MySQL did not stop listening before the shutdown timeout.")

    def _read_server_pid(self) -> int | None:
        if not self._paths.pid_path.is_file():
            return None
        try:
            value = self._paths.pid_path.read_text(encoding="ascii").strip()
            pid = int(value)
        except (OSError, ValueError) as error:
            raise ManagedLocalMySqlError("Managed MySQL pid file is invalid.") from error
        if pid < 1:
            raise ManagedLocalMySqlError("Managed MySQL pid file contains an invalid process ID.")
        return pid

    @staticmethod
    def _wait_for_server_exit(pid: int | None) -> None:
        if pid is None:
            return
        deadline = time.monotonic() + 15.0
        while time.monotonic() < deadline:
            if not _process_is_running(pid):
                return
            time.sleep(0.1)
        raise ManagedLocalMySqlError("Managed MySQL server process did not exit before the shutdown timeout.")

    def _initialize_data_directory(self) -> None:
        completed = subprocess.run(
            [
                str(self._mysqld_path()),
                f"--basedir={self._mysql_home}",
                f"--datadir={self._paths.data_dir}",
                "--initialize-insecure",
            ],
            cwd=str(self._mysql_home),
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode != 0 or not (self._paths.data_dir / "auto.cnf").is_file():
            raise ManagedLocalMySqlError("Managed MySQL data directory initialization failed.")

    def _write_bootstrap_sql(self, password: str) -> None:
        if "'" in password:
            raise ManagedLocalMySqlError("Generated MySQL password contains unsupported quoting characters.")
        sql = "\n".join(
            [
                f"CREATE DATABASE IF NOT EXISTS {LOCAL_DATABASE_NAME} CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;",
                f"CREATE USER IF NOT EXISTS '{LOCAL_DATABASE_USER}'@'127.0.0.1' IDENTIFIED BY '{password}';",
                f"ALTER USER '{LOCAL_DATABASE_USER}'@'127.0.0.1' IDENTIFIED BY '{password}';",
                f"GRANT ALL PRIVILEGES ON {LOCAL_DATABASE_NAME}.* TO '{LOCAL_DATABASE_USER}'@'127.0.0.1';",
                f"GRANT SHUTDOWN ON *.* TO '{LOCAL_DATABASE_USER}'@'127.0.0.1';",
                "FLUSH PRIVILEGES;",
            ]
        )
        atomic_write_text(self._paths.bootstrap_sql_path, sql + "\n")

    def _options_from_state(self, state: dict[str, object]) -> DatabaseOptions:
        port = state.get("port")
        if not isinstance(port, int) or not 1 <= port <= 65535:
            raise ManagedLocalMySqlError("Managed MySQL runtime state contains an invalid port.")
        try:
            password = load_local_mysql_password(self._paths.credential_path)
        except LocalCredentialError as error:
            raise ManagedLocalMySqlError("Managed MySQL credentials cannot be read.") from error
        return DatabaseOptions(
            url=f"mysql+pymysql://{LOCAL_DATABASE_USER}:{password}@127.0.0.1:{port}/{LOCAL_DATABASE_NAME}"
        )

    def _read_runtime_state(self) -> dict[str, object] | None:
        if not self._paths.runtime_state_path.is_file():
            return None
        try:
            payload = json.loads(self._paths.runtime_state_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise ManagedLocalMySqlError("Managed MySQL runtime state is unreadable.") from error
        if not isinstance(payload, dict):
            raise ManagedLocalMySqlError("Managed MySQL runtime state must be an object.")
        return payload

    def _write_runtime_state(self, port: int) -> None:
        atomic_write_text(
            self._paths.runtime_state_path,
            json.dumps(
                {
                    "version": RUNTIME_STATE_VERSION,
                    "port": port,
                    "database": LOCAL_DATABASE_NAME,
                    "user": LOCAL_DATABASE_USER,
                },
                indent=2,
            )
            + "\n",
        )

    def _ensure_directories(self) -> None:
        for directory in (self._paths.data_dir, self._paths.logs_dir, self._paths.run_dir):
            directory.mkdir(parents=True, exist_ok=True)

    def _acquire_instance_lock(self) -> None:
        if self._instance_lock_handle is not None:
            return
        lock_path = self._paths.run_dir / "vsummary-mysql.lock"
        handle = lock_path.open("a+b")
        try:
            handle.seek(0)
            handle.write(b"0")
            handle.flush()
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError as error:
            handle.close()
            raise ManagedLocalMySqlError(
                "Another VSummary instance is already managing this local MySQL data directory."
            ) from error
        self._instance_lock_handle = handle

    def _release_instance_lock(self) -> None:
        handle = self._instance_lock_handle
        if handle is None:
            return
        try:
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        except OSError:
            pass
        finally:
            handle.close()
            self._instance_lock_handle = None

    def _is_initialized(self) -> bool:
        return (self._paths.data_dir / "auto.cnf").is_file()

    def _validate_runtime_binary(self) -> None:
        if not self._mysqld_path().is_file():
            raise ManagedLocalMySqlError(
                "Managed MySQL runtime is missing from the VSummary installation. Reinstall the full package."
            )

    def _validate_mysql_paths(self) -> None:
        mysql_paths = (self._mysql_home, self._paths.root)
        if all(str(path).isascii() for path in mysql_paths):
            return
        raise ManagedLocalMySqlPathError(
            "当前安装目录或数据目录包含中文或特殊字符，内置 MySQL 无法启动。"
            "请将完整安装包移动到纯英文路径后重新启动，例如 E:\\Apps\\VSummary。"
        )

    def _mysqld_path(self) -> Path:
        return self._mysql_home / "bin" / "mysqld.exe"

    def _mysqladmin_path(self) -> Path:
        path = self._mysql_home / "bin" / "mysqladmin.exe"
        if not path.is_file():
            raise ManagedLocalMySqlError("Managed MySQL runtime is missing mysqladmin.exe.")
        return path

    def _read_error_log_tail(self) -> str:
        if not self._paths.error_log_path.is_file():
            return "No MySQL error log was created."
        try:
            lines = self._paths.error_log_path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            return "MySQL error log could not be read."
        return " ".join(lines[-8:]) or "MySQL error log is empty."


def _default_data_root() -> Path:
    configured_root = os.environ.get("VSUMMARY_DATA")
    if configured_root:
        root = Path(configured_root).expanduser()
        if not root.is_absolute():
            raise ManagedLocalMySqlError("VSUMMARY_DATA must be an absolute path.")
        return root
    local_app_data = os.environ.get("LOCALAPPDATA")
    if not local_app_data:
        raise ManagedLocalMySqlError("LOCALAPPDATA is required for managed local MySQL.")
    return Path(local_app_data) / "VSummary"


def _select_loopback_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def _is_loopback_port_open(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.settimeout(0.25)
        return probe.connect_ex(("127.0.0.1", port)) == 0


def _new_password() -> str:
    # token_urlsafe avoids quotes and SQL metacharacters while retaining enough entropy.
    return secrets.token_urlsafe(32)


def _process_is_running(pid: int) -> bool:
    """用平台原生 API 判断 PID 是否仍为运行中的进程。"""

    if sys.platform != "win32":
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        return True

    synchronize = 0x00100000
    wait_object_0 = 0
    wait_timeout = 258
    handle = ctypes.windll.kernel32.OpenProcess(synchronize, False, pid)
    if not handle:
        return False
    try:
        result = ctypes.windll.kernel32.WaitForSingleObject(handle, 0)
        if result == wait_object_0:
            return False
        if result == wait_timeout:
            return True
        raise ManagedLocalMySqlError("Unable to determine whether managed MySQL exited.")
    finally:
        ctypes.windll.kernel32.CloseHandle(handle)
