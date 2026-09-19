"""VSummary MySQL schema migration 入口。

迁移由启动器或发布流程显式调用，不能在导入模块或普通 API 请求中隐式执行。
"""

from __future__ import annotations

import argparse
from pathlib import Path

from alembic import command
from alembic.config import Config

from backend.video_summary.infrastructure.persistence.database import DatabaseOptions


def build_alembic_config(options: DatabaseOptions) -> Config:
    """为当前包内迁移目录构造 Alembic 配置。"""

    migrations_dir = Path(__file__).with_name("migrations")
    config = Config()
    config.set_main_option("script_location", str(migrations_dir))
    config.set_main_option("sqlalchemy.url", options.url)
    config.attributes["database_url"] = options.url
    return config


def upgrade_to_head(options: DatabaseOptions) -> None:
    """把数据库升级到当前应用支持的最新 Schema。"""

    command.upgrade(build_alembic_config(options), "head")


def current_revision(options: DatabaseOptions) -> str | None:
    """读取当前 Alembic revision；空数据库返回 ``None``。"""

    config = build_alembic_config(options)
    script = command.current(config, verbose=False)
    return str(script) if script is not None else None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Upgrade the VSummary MySQL schema.")
    parser.add_argument("--database-url", required=True)
    args = parser.parse_args(argv)
    upgrade_to_head(DatabaseOptions(url=args.database_url))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
