"""
数据库初始化脚本

What: 自动创建 SQLite 数据库、所有表，初始化 ChromaDB 向量库目录
Why: 开发环境一键初始化，无需手动写 SQL
How: 导入所有 ORM 模型 → 注册到 metadata → create_all 建表 → 创建目录

Usage:
    uv run python scripts/init_db.py
"""

import asyncio
import os
import sys
from pathlib import Path

# 将 backend/ 加入 sys.path，确保脚本从任意目录运行均可导入 app 模块
_BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(_BACKEND_DIR))

from app.core.config import settings          # noqa: E402
from app.db.base import Base                  # noqa: E402
from app.db.session import get_engine         # noqa: E402
import app.models                             # noqa: E402, F401  注册所有 ORM 模型


async def init_database() -> None:
    """
    创建数据库表

    What: 读取 Base.metadata 中所有已注册的 ORM 模型，在数据库中建表
    Why: SQLAlchemy create_all 根据模型定义自动生成 CREATE TABLE 语句
    How: 异步引擎下通过 run_sync 执行同步的 create_all
    """
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await engine.dispose()


def init_chromadb() -> None:
    """
    初始化 ChromaDB 向量库目录

    What: 确保 ChromaDB 持久化目录存在
    Why: ChromaDB PersistentClient 不会自动创建父目录，需手动保证
    """
    chroma_dir = Path(settings.CHROMA_PERSIST_DIR)
    if not chroma_dir.exists():
        chroma_dir.mkdir(parents=True, exist_ok=True)


def init_data_dir() -> None:
    """
    确保 SQLite 数据目录存在

    What: 从 DATABASE_URL 中提取 SQLite 文件路径，创建父目录
    Why: SQLite 不会自动创建不存在的目录，需手动创建
    """
    if "sqlite" in settings.DATABASE_URL:
        db_path = settings.DATABASE_URL.replace("sqlite+aiosqlite:///", "")
        db_dir = Path(db_path).parent
        if not db_dir.exists():
            db_dir.mkdir(parents=True, exist_ok=True)


async def main() -> None:
    """主入口函数"""
    print("Database initialization started ...")

    # 1. 确保数据目录存在
    init_data_dir()

    # 2. 创建数据库表
    await init_database()
    print("Tables created successfully.")

    # 3. 初始化 ChromaDB 目录
    init_chromadb()
    print("ChromaDB directory initialized.")

    print("Database initialization completed.")


if __name__ == "__main__":
    asyncio.run(main())
