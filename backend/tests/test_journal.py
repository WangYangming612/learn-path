from datetime import date
from pathlib import Path
import sys
from uuid import uuid4

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core.journal_service import create_journal, get_journals
from app.core.weekly_report import generate_weekly_report
from app.db.session import get_db
from app.models.daily_task import DailyTask
from app.models.plan import Plan
from app.models.user import User
from app.schemas.journal import JournalCreateRequest


@pytest.mark.asyncio
async def test_create_and_archive_journal_for_completed_task():
    suffix = uuid4().hex[:8]
    async for db in get_db():
        user = User(
            username=f"journal-{suffix}",
            email=f"journal-{suffix}@example.com",
            hashed_password="test",
        )
        db.add(user)
        await db.flush()
        plan = Plan(user_id=user.id, title="日记测试计划", status="active", priority=1)
        db.add(plan)
        await db.flush()
        task = DailyTask(
            user_id=user.id,
            plan_id=plan.id,
            title="已完成任务",
            scheduled_date=date.today(),
            duration_minutes=30,
            status="completed",
        )
        db.add(task)
        await db.commit()

        journal = await create_journal(
            db,
            user.id,
            JournalCreateRequest(task_id=task.id, title="今日收获", content="理解了异步查询", mood="confident"),
        )
        assert journal is not None

        journals = await get_journals(db, user.id)
        assert len(journals) == 1
        assert journals[0].task_id == task.id
        assert journals[0].content == "理解了异步查询"
        break


@pytest.mark.asyncio
async def test_weekly_report_uses_local_fallback_when_llm_fails(monkeypatch):
    suffix = uuid4().hex[:8]

    def _raise_llm_error(*args, **kwargs):
        raise RuntimeError("LLM unavailable")

    monkeypatch.setattr("app.core.weekly_report.llm_client.get_chat_model", _raise_llm_error)

    async for db in get_db():
        user = User(
            username=f"report-{suffix}",
            email=f"report-{suffix}@example.com",
            hashed_password="test",
        )
        db.add(user)
        await db.flush()
        plan = Plan(user_id=user.id, title="周报测试计划", status="active", priority=1)
        db.add(plan)
        await db.flush()
        task = DailyTask(
            user_id=user.id,
            plan_id=plan.id,
            title="本周任务",
            scheduled_date=date.today(),
            duration_minutes=45,
            status="completed",
        )
        db.add(task)
        await db.commit()

        report = await generate_weekly_report(db, user.id)
        assert report["completed_task_count"] == 1
        assert report["completed_minutes"] == 45
        assert "累计投入 45 分钟" in report["summary"]
        break
