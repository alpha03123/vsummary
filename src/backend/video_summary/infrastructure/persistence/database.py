"""MySQL 连接配置与 SQLAlchemy 会话工厂。

本模块故意拒绝 SQLite 和隐式 URL 回退：本地与云端都应使用同一 MySQL
Schema。受管本地 MySQL 的初始化/凭据管理会在独立运行时层实现；这里仅
接收已经解析好的连接配置。
"""

from __future__ import annotations

from dataclasses import dataclass
import importlib

from sqlalchemy import Engine, create_engine
from sqlalchemy.engine import URL, make_url
from sqlalchemy.orm import Session, sessionmaker


DEFAULT_POOL_RECYCLE_SECONDS = 1_800


class DatabaseDriverError(RuntimeError):
    """运行环境缺少 MySQL 驱动。"""


@dataclass(frozen=True)
class DatabaseOptions:
    """显式 MySQL 连接参数。

    `url` 必须使用 PyMySQL 驱动，以便本地整合包和云端部署采用相同的 Python
    连接行为，例如 ``mysql+pymysql://user:password@127.0.0.1:3307/vsummary``。
    """

    url: str
    pool_size: int = 5
    max_overflow: int = 5
    pool_recycle_seconds: int = DEFAULT_POOL_RECYCLE_SECONDS

    def __post_init__(self) -> None:
        parsed = _parse_mysql_url(self.url)
        if not parsed.username:
            raise ValueError("MySQL database URL must include a username.")
        if parsed.password is None:
            raise ValueError("MySQL database URL must include a password.")
        if not parsed.host:
            raise ValueError("MySQL database URL must include a host.")
        if not parsed.database:
            raise ValueError("MySQL database URL must include a database name.")
        if self.pool_size < 1:
            raise ValueError("MySQL pool_size must be at least 1.")
        if self.max_overflow < 0:
            raise ValueError("MySQL max_overflow cannot be negative.")
        if self.pool_recycle_seconds < 1:
            raise ValueError("MySQL pool_recycle_seconds must be positive.")

    @property
    def parsed_url(self) -> URL:
        """返回已验证的 SQLAlchemy URL。"""
        return _parse_mysql_url(self.url)


def create_database_engine(options: DatabaseOptions) -> Engine:
    """构造带连接健康检查的 MySQL Engine。

    调用者负责在进程启动阶段执行 Alembic migration；该函数不建表、不跑
    migration，也不尝试通过 SQLite 或目录文件静默降级。
    """

    _require_pymysql()
    return create_engine(
        options.parsed_url,
        future=True,
        pool_pre_ping=True,
        pool_size=options.pool_size,
        max_overflow=options.max_overflow,
        pool_recycle=options.pool_recycle_seconds,
    )


def create_session_factory(options: DatabaseOptions) -> sessionmaker[Session]:
    """创建不自动过期的 Session 工厂，供 Repository 显式控制事务。"""

    return sessionmaker(bind=create_database_engine(options), expire_on_commit=False, future=True)


def _parse_mysql_url(value: str) -> URL:
    if not value or not value.strip():
        raise ValueError("MySQL database URL is required.")
    try:
        parsed = make_url(value)
    except Exception as error:
        raise ValueError("Invalid MySQL database URL.") from error
    if parsed.drivername != "mysql+pymysql":
        raise ValueError("MySQL database URL must use the mysql+pymysql driver.")
    return parsed


def _require_pymysql() -> None:
    try:
        importlib.import_module("pymysql")
    except ModuleNotFoundError as error:
        raise DatabaseDriverError(
            "PyMySQL is required for managed MySQL. Update the VSummary Python environment with requirements.txt."
        ) from error
