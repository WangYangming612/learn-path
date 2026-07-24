"""
数据库初始化脚本

What: 创建本地开发环境所需的 SQLite 数据目录并执行 ORM 建表
Why: 当前项目未集成 Alembic，需要一个最小可用的本地初始化入口
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.db.base import Base
from app.db.session import get_engine
from app.models import *  # noqa: F401,F403 - 确保模型注册到 Base.metadata


async def init_database() -> None:
    """初始化数据库目录并创建所有 ORM 表"""

    engine = get_engine()
    db_url = str(engine.url)

    if db_url.startswith("sqlite+"):
        sqlite_path = Path("./data/sqlite")
        sqlite_path.mkdir(parents=True, exist_ok=True)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    await engine.dispose()
    print("Database initialized successfully.")


if __name__ == "__main__":
    asyncio.run(init_database())
