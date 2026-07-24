"""为已有 SQLite 数据库补充 Step8 排期字段。"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from sqlalchemy import text

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.db.session import get_engine


async def _add_column_if_missing(table: str, column: str, definition: str) -> None:
    engine = get_engine()
    async with engine.begin() as connection:
        result = await connection.execute(text(f"PRAGMA table_info({table})"))
        columns = {row[1] for row in result.fetchall()}
        if column not in columns:
            await connection.execute(text(f"ALTER TABLE {table} ADD COLUMN {definition}"))


async def migrate() -> None:
    """补齐 Step8 所需的计划优先级和任务排期字段。"""

    await _add_column_if_missing("plans", "priority", "priority INTEGER NOT NULL DEFAULT 2")
    await _add_column_if_missing("daily_tasks", "start_time", "start_time TIME")
    await _add_column_if_missing("daily_tasks", "end_time", "end_time TIME")
    await _add_column_if_missing("daily_tasks", "guide_content", "guide_content TEXT")
    await get_engine().dispose()
    print("Step8 database migration completed.")


if __name__ == "__main__":
    asyncio.run(migrate())
