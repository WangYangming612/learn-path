"""每日任务持久化服务。"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Iterable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.daily_task import DailyTask

def serialize_daily_task(task: DailyTask) -> dict[str, Any]:
    """转换 ORM 任务为 API 响应字段。"""

    return {
        "id": task.id,
        "plan_id": task.plan_id,
        "knowledge_node_id": task.knowledge_node_id,
        "plan_title": task.plan.title if task.plan else None,
        "title": task.title,
        "description": task.description,
        "scheduled_date": task.scheduled_date,
        "start_time": task.start_time,
        "end_time": task.end_time,
        "duration_minutes": task.duration_minutes,
        "guide_content": task.guide_content,
        "status": task.status,
        "completed_at": task.completed_at,
    }


async def create_daily_tasks(
    db: AsyncSession,
    user_id: int,
    tasks: Iterable[dict[str, Any]],
    scheduled_date: date,
) -> list[DailyTask]:
    """替换用户指定日期尚未完成的任务，并保存新的排期。"""

    existing_result = await db.execute(
        select(DailyTask).where(
            DailyTask.user_id == user_id,
            DailyTask.scheduled_date == scheduled_date,
            DailyTask.status == "pending",
        )
    )
    for task in existing_result.scalars():
        await db.delete(task)

    created: list[DailyTask] = []
    for item in tasks:
        start_time = item["start_time"]
        end_time = item["end_time"]
        task = DailyTask(
            user_id=user_id,
            plan_id=item["plan_id"],
            knowledge_node_id=item.get("knowledge_node_id"),
            title=item["title"],
            description=item.get("description"),
            scheduled_date=scheduled_date,
            start_time=start_time,
            end_time=end_time,
            duration_minutes=item["duration_minutes"],
            guide_content=item.get("guide_content"),
            status="pending",
        )
        db.add(task)
        created.append(task)

    await db.commit()
    for task in created:
        await db.refresh(task, attribute_names=["plan"])
    return created


async def get_daily_tasks(
    db: AsyncSession,
    user_id: int,
    scheduled_date: date | None = None,
) -> list[DailyTask]:
    """获取用户的每日任务，可按日期筛选。"""

    stmt = (
        select(DailyTask)
        .options(selectinload(DailyTask.plan))
        .where(DailyTask.user_id == user_id)
        .order_by(DailyTask.scheduled_date.desc(), DailyTask.id.asc())
    )
    if scheduled_date:
        stmt = stmt.where(DailyTask.scheduled_date == scheduled_date)
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_tasks_by_date(
    db: AsyncSession, user_id: int, scheduled_date: date
) -> list[DailyTask]:
    """获取用户某日任务。"""

    return await get_daily_tasks(db, user_id, scheduled_date)


async def update_task_status(
    db: AsyncSession, user_id: int, task_id: int, status: str
) -> DailyTask | None:
    """更新属于当前用户的任务状态。"""

    result = await db.execute(
        select(DailyTask)
        .options(selectinload(DailyTask.plan))
        .where(DailyTask.id == task_id, DailyTask.user_id == user_id)
    )
    task = result.scalar_one_or_none()
    if task is None:
        return None

    task.status = status
    task.completed_at = datetime.now() if status == "completed" else None
    await db.commit()
    await db.refresh(task, attribute_names=["plan"])
    return task
