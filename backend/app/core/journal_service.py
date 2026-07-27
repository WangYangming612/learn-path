"""学习日记持久化服务。"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.daily_task import DailyTask
from app.models.study_journal import StudyJournal
from app.schemas.journal import JournalCreateRequest


def serialize_journal(journal: StudyJournal) -> dict[str, Any]:
    """转换学习日记 ORM 为 API 响应字段。"""

    return {
        "id": journal.id,
        "task_id": journal.task_id,
        "title": journal.title,
        "content": journal.content,
        "mood": journal.mood,
        "study_duration": journal.study_duration,
        "created_at": journal.created_at,
        "updated_at": journal.updated_at,
    }


async def create_journal(
    db: AsyncSession,
    user_id: int,
    payload: JournalCreateRequest,
) -> StudyJournal | None:
    """创建学习日记；关联任务时仅允许为本人已完成的任务记录笔记。"""

    if payload.task_id is not None:
        task_result = await db.execute(
            select(DailyTask).where(
                DailyTask.id == payload.task_id,
                DailyTask.user_id == user_id,
                DailyTask.status == "completed",
            )
        )
        if task_result.scalar_one_or_none() is None:
            return None

    journal = StudyJournal(
        user_id=user_id,
        task_id=payload.task_id,
        title=payload.title,
        content=payload.content,
        mood=payload.mood,
        study_duration=payload.study_duration,
    )
    db.add(journal)
    await db.commit()
    await db.refresh(journal)
    return journal


async def get_journals(
    db: AsyncSession,
    user_id: int,
    limit: int = 50,
    offset: int = 0,
) -> list[StudyJournal]:
    """按创建时间倒序归档查询当前用户的学习日记。"""

    result = await db.execute(
        select(StudyJournal)
        .where(StudyJournal.user_id == user_id)
        .order_by(StudyJournal.created_at.desc(), StudyJournal.id.desc())
        .offset(offset)
        .limit(limit)
    )
    return list(result.scalars().all())
